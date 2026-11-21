from datetime import date
from decimal import Decimal
import json
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import get_db
from app.core.security import AuthenticatedActor, assert_scope, require_permission
from app.modules.personal.lft_2026 import calcular_finiquito_lft_2026

router = APIRouter(prefix="/api/v1/personal", tags=["Administración de Personal (Fase 2)"])

EXPEDIENTE_16_ESTADOS = {
    "BORRADOR",
    "PREALTA",
    "DOCUMENTOS_PENDIENTES",
    "DOCUMENTOS_CARGADOS",
    "DOCUMENTOS_OBSERVADOS",
    "DOCUMENTOS_VALIDADOS",
    "CONTRATO_GENERADO",
    "CONTRATO_FIRMADO",
    "CAPACITACION_PENDIENTE",
    "CAPACITACION_COMPLETA",
    "LISTO_PARA_TRABAJAR",
    "LISTO_MERQRY",
    "LISTO_PRENOMINA",
    "ACTIVO",
    "BAJA",
    "ARCHIVADO",
}


class CrearContratoIn(BaseModel):
    relacion_laboral_id: str
    tipo_contrato: str = Field(..., pattern="^(TEMPORADA|INDETERMINADO|OBRA_DETERMINADA|CAPACITACION_INICIAL)$")
    salario_diario: float = Field(..., gt=0)
    fecha_inicio: date
    fecha_fin: Optional[date] = None
    incluye_renuncia_anticipada: bool = False


class TransicionContratoIn(BaseModel):
    nuevo_estatus: str = Field(..., pattern="^(VALIDADO|FIRMADO|TERMINADO|CANCELADO)$")
    hash_documento: Optional[str] = None


class CrearResponsivaIn(BaseModel):
    relacion_laboral_id: str
    tipo_responsiva: str = Field(..., pattern="^(UNIFORME|EPP|HERRAMIENTA|EQUIPO|VEHICULO|FONDO)$")
    es_critico_operacion: bool = False
    descripcion_items: List[Dict[str, Any]] = Field(..., min_length=1)
    descuento_autorizado_explicitamente: bool = False


class CrearBeneficiarioIn(BaseModel):
    relacion_laboral_id: str
    nombre_completo: str = Field(..., min_length=3, max_length=150)
    parentesco: str = Field(..., min_length=2, max_length=50)
    porcentaje_asignado: float = Field(..., gt=0, le=100)
    telefono_contacto: Optional[str] = None


class UpdateReadyIn(BaseModel):
    nivel_accion: str = Field(..., pattern="^(VALIDACION_RAPIDA|VALIDACION_CRITICA|EXCEPCION_TEMPORAL)$")
    requisito_omitido: str = Field(..., min_length=2, max_length=80)
    motivo: str = Field(..., min_length=5)
    responsable_usuario_id: str
    fecha_limite: Optional[date] = None


class AvanzarExpedienteIn(BaseModel):
    nuevo_estatus: str
    capacitacion_impartida: Optional[bool] = None
    capacitacion_validada: Optional[bool] = None
    alta_interna_completa: Optional[bool] = None
    alta_imss_confirmada: Optional[bool] = None


class CalcularFiniquitoIn(BaseModel):
    relacion_laboral_id: str
    fecha_baja: date
    motivo_baja: str = Field(
        ...,
        pattern="^(RENUNCIA_VOLUNTARIA|TERMINO_TEMPORADA|DESPIDO_JUSTIFICADO|DESPIDO_INJUSTIFICADO|MUTUO_ACUERDO)$",
    )
    salario_diario: float = Field(..., gt=0)
    dias_salarios_pendientes: float = Field(default=0, ge=0)
    deducciones_autorizadas: float = Field(default=0, ge=0)
    aplicar_baja_expediente: bool = False


def _uuid(raw: str, label: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=f"{label} inválido o no encontrado.") from exc


@router.post("/contratos", status_code=status.HTTP_201_CREATED)
async def crear_contrato_borrador(
    data: CrearContratoIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.expediente.gestionar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    if data.incluye_renuncia_anticipada:
        raise HTTPException(
            status_code=422,
            detail="RENUNCIA_ANTICIPADA_PROHIBIDA: Prohibido generar contratos con renuncia anticipada pre-firmada.",
        )
    rlid = _uuid(data.relacion_laboral_id, "Relación laboral")
    rel = (
        await db.execute(
            text("SELECT empresa_id, sucursal_id, unidad_operativa_id FROM relaciones_laborales WHERE id = CAST(:id AS uuid)"),
            {"id": rlid},
        )
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relación laboral no encontrada.")
    assert_scope(actor, "rh.expediente.gestionar", empresa_id=rel.empresa_id, min_level=2)

    row = (
        await db.execute(
            text(
                """
                INSERT INTO contratos_laborales (
                    relacion_laboral_id, empresa_id, tipo_contrato, salario_diario,
                    fecha_inicio, fecha_fin, estatus, incluye_renuncia_anticipada
                ) VALUES (
                    CAST(:rlid AS uuid), :emp, :tipo, :sal, :fi, :ff, 'BORRADOR', FALSE
                )
                RETURNING id::text AS id, relacion_laboral_id::text AS relacion_laboral_id,
                          tipo_contrato, salario_diario, estatus
                """
            ),
            {
                "rlid": rlid,
                "emp": rel.empresa_id,
                "tipo": data.tipo_contrato,
                "sal": data.salario_diario,
                "fi": data.fecha_inicio,
                "ff": data.fecha_fin,
            },
        )
    ).first()
    await db.execute(
        text(
            "UPDATE expedientes_personal SET estatus = 'CONTRATO_GENERADO', actualizado_en = NOW() WHERE relacion_laboral_id = CAST(:rlid AS uuid)"
        ),
        {"rlid": rlid},
    )
    await db.commit()
    return dict(row._mapping)


@router.patch("/contratos/{contrato_id}/transicion")
async def transicionar_contrato(
    contrato_id: str,
    data: TransicionContratoIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.expediente.gestionar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    """Maquina estricta BORRADOR -> VALIDADO -> FIRMADO (prohibido saltar VALIDADO)."""
    cid = _uuid(contrato_id, "Contrato")
    c = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, relacion_laboral_id::text AS relacion_laboral_id,
                       empresa_id, estatus
                FROM contratos_laborales
                WHERE id = CAST(:cid AS uuid)
                FOR UPDATE
                """
            ),
            {"cid": cid},
        )
    ).first()
    if not c:
        raise HTTPException(status_code=404, detail="Contrato no encontrado.")
    assert_scope(actor, "rh.expediente.gestionar", empresa_id=c.empresa_id, min_level=2)

    valid_transitions = {
        "BORRADOR": {"VALIDADO", "CANCELADO"},
        "VALIDADO": {"FIRMADO", "CANCELADO"},
        "FIRMADO": {"TERMINADO"},
    }
    if data.nuevo_estatus not in valid_transitions.get(c.estatus, set()):
        raise HTTPException(
            status_code=409,
            detail=f"TRANSICION_CONTRATO_INVALIDA: No se puede pasar de {c.estatus} a {data.nuevo_estatus}.",
        )

    if data.nuevo_estatus == "VALIDADO":
        await db.execute(
            text(
                """
                UPDATE contratos_laborales
                   SET estatus = 'VALIDADO', validado_por_usuario_id = CAST(:uid AS uuid), validado_en = NOW()
                 WHERE id = CAST(:cid AS uuid)
                """
            ),
            {"uid": actor.usuario_id, "cid": cid},
        )
    elif data.nuevo_estatus == "FIRMADO":
        await db.execute(
            text(
                """
                UPDATE contratos_laborales
                   SET estatus = 'FIRMADO', firmado_en = NOW(), hash_documento = COALESCE(:h, hash_documento)
                 WHERE id = CAST(:cid AS uuid)
                """
            ),
            {"h": data.hash_documento, "cid": cid},
        )
        await db.execute(
            text(
                """
                UPDATE expedientes_personal
                   SET estatus = 'CONTRATO_FIRMADO', actualizado_en = NOW()
                 WHERE relacion_laboral_id = CAST(:rlid AS uuid)
                """
            ),
            {"rlid": c.relacion_laboral_id},
        )
    else:
        await db.execute(
            text("UPDATE contratos_laborales SET estatus = :est WHERE id = CAST(:cid AS uuid)"),
            {"est": data.nuevo_estatus, "cid": cid},
        )

    await db.commit()
    return {"contrato_id": cid, "estatus": data.nuevo_estatus}


@router.post("/responsivas", status_code=status.HTTP_201_CREATED)
async def registrar_responsiva(
    data: CrearResponsivaIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.expediente.gestionar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    rlid = _uuid(data.relacion_laboral_id, "Relación laboral")
    rel = (
        await db.execute(
            text("SELECT empresa_id FROM relaciones_laborales WHERE id = CAST(:id AS uuid)"),
            {"id": rlid},
        )
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relación laboral no encontrada.")
    assert_scope(actor, "rh.expediente.gestionar", empresa_id=rel.empresa_id, min_level=2)

    row = (
        await db.execute(
            text(
                """
                INSERT INTO responsivas_personal (
                    relacion_laboral_id, empresa_id, tipo_responsiva, es_critico_operacion,
                    descripcion_items, descuento_autorizado_explicitamente, entregado_por_usuario_id
                ) VALUES (
                    CAST(:rlid AS uuid), :emp, :tipo, :crit,
                    CAST(:items AS jsonb), :desc, CAST(:uid AS uuid)
                )
                RETURNING id::text AS id, tipo_responsiva, es_critico_operacion,
                          descuento_autorizado_explicitamente
                """
            ),
            {
                "rlid": rlid,
                "emp": rel.empresa_id,
                "tipo": data.tipo_responsiva,
                "crit": data.es_critico_operacion,
                "items": json.dumps(data.descripcion_items),
                "desc": data.descuento_autorizado_explicitamente,
                "uid": actor.usuario_id,
            },
        )
    ).first()

    if data.tipo_responsiva == "EPP" and data.es_critico_operacion:
        await db.execute(
            text(
                """
                UPDATE expedientes_personal
                   SET epp_critico_entregado = TRUE, actualizado_en = NOW()
                 WHERE relacion_laboral_id = CAST(:rlid AS uuid)
                """
            ),
            {"rlid": rlid},
        )

    await db.commit()
    return dict(row._mapping)


@router.post("/beneficiarios", status_code=status.HTTP_201_CREATED)
async def registrar_beneficiario_art501(
    data: CrearBeneficiarioIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.expediente.gestionar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    rlid = _uuid(data.relacion_laboral_id, "Relación laboral")
    rel = (
        await db.execute(
            text("SELECT empresa_id FROM relaciones_laborales WHERE id = CAST(:id AS uuid)"),
            {"id": rlid},
        )
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relación laboral no encontrada.")
    assert_scope(actor, "rh.expediente.gestionar", empresa_id=rel.empresa_id, min_level=2)

    acumulado = (
        await db.execute(
            text("SELECT COALESCE(SUM(porcentaje_asignado), 0) FROM beneficiarios_art501 WHERE relacion_laboral_id = CAST(:id AS uuid)"),
            {"id": rlid},
        )
    ).scalar()
    if Decimal(str(acumulado)) + Decimal(str(data.porcentaje_asignado)) > Decimal("100.00"):
        raise HTTPException(
            status_code=422,
            detail=f"La suma de porcentajes de beneficiarios Art. 501 excede 100% (actual: {acumulado}%).",
        )

    row = (
        await db.execute(
            text(
                """
                INSERT INTO beneficiarios_art501 (
                    relacion_laboral_id, empresa_id, nombre_completo, parentesco,
                    porcentaje_asignado, telefono_contacto
                ) VALUES (
                    CAST(:rlid AS uuid), :emp, :nom, :par, :pct, :tel
                )
                RETURNING id::text AS id, nombre_completo, parentesco, porcentaje_asignado
                """
            ),
            {
                "rlid": rlid,
                "emp": rel.empresa_id,
                "nom": data.nombre_completo.strip(),
                "par": data.parentesco.strip(),
                "pct": data.porcentaje_asignado,
                "tel": data.telefono_contacto,
            },
        )
    ).first()
    await db.commit()
    return dict(row._mapping)


@router.post("/expedientes/{expediente_id}/update-ready", status_code=status.HTTP_201_CREATED)
async def registrar_update_ready(
    expediente_id: str,
    data: UpdateReadyIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.update_ready.autorizar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    eid = _uuid(expediente_id, "Expediente")
    resp_uid = _uuid(data.responsable_usuario_id, "Responsable")
    exp = (
        await db.execute(
            text("SELECT id::text AS id, empresa_id FROM expedientes_personal WHERE id = CAST(:id AS uuid)"),
            {"id": eid},
        )
    ).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")

    min_lvl = 3 if data.nivel_accion in ("VALIDACION_CRITICA", "EXCEPCION_TEMPORAL") else 2
    assert_scope(actor, "rh.update_ready.autorizar", empresa_id=exp.empresa_id, min_level=min_lvl)

    if data.nivel_accion == "EXCEPCION_TEMPORAL" and data.fecha_limite is None:
        raise HTTPException(status_code=400, detail="EXCEPCION_TEMPORAL exige fecha_limite obligatoria.")

    row = (
        await db.execute(
            text(
                """
                INSERT INTO update_ready_excepciones (
                    expediente_id, empresa_id, nivel_accion, requisito_omitido,
                    motivo, responsable_usuario_id, autorizado_por_usuario_id,
                    fecha_limite, estatus
                ) VALUES (
                    CAST(:eid AS uuid), :emp, :niv, :req,
                    :mot, CAST(:resp AS uuid), CAST(:aut AS uuid),
                    :flim, 'VIGENTE'
                )
                RETURNING id::text AS id, nivel_accion, requisito_omitido, fecha_limite, estatus
                """
            ),
            {
                "eid": eid,
                "emp": exp.empresa_id,
                "niv": data.nivel_accion,
                "req": data.requisito_omitido.strip().upper(),
                "mot": data.motivo.strip(),
                "resp": resp_uid,
                "aut": actor.usuario_id,
                "flim": data.fecha_limite,
            },
        )
    ).first()
    await registrar_auditoria(
        db,
        actor,
        modulo="personal",
        accion=f"UPDATE_READY_{data.nivel_accion}",
        tipo_entidad="EXPEDIENTE",
        id_entidad=eid,
        empresa_id=exp.empresa_id,
        datos_despues=dict(row._mapping),
    )
    await db.commit()
    return dict(row._mapping)


@router.patch("/update-ready/{excepcion_id}/resolver")
async def resolver_excepcion_update_ready(
    excepcion_id: str,
    actor: AuthenticatedActor = Depends(require_permission("rh.update_ready.autorizar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    xid = _uuid(excepcion_id, "Excepción UPDATE_READY")
    exc = (
        await db.execute(
            text("SELECT id::text AS id, expediente_id::text AS expediente_id, empresa_id FROM update_ready_excepciones WHERE id = CAST(:id AS uuid)"),
            {"id": xid},
        )
    ).first()
    if not exc:
        raise HTTPException(status_code=404, detail="Excepción no encontrada.")
    assert_scope(actor, "rh.update_ready.autorizar", empresa_id=exc.empresa_id, min_level=2)

    await db.execute(
        text(
            "UPDATE update_ready_excepciones SET estatus = 'RESUELTA', resuelta_en = NOW() WHERE id = CAST(:id AS uuid)"
        ),
        {"id": xid},
    )
    # Recalcular si quedan excepciones vencidas en el expediente
    vencidas = (
        await db.execute(
            text(
                """
                SELECT COUNT(*) FROM update_ready_excepciones
                WHERE expediente_id = CAST(:eid AS uuid)
                  AND nivel_accion = 'EXCEPCION_TEMPORAL'
                  AND estatus IN ('VIGENTE', 'VENCIDA_BLOQUEADA')
                  AND fecha_limite < CURRENT_DATE
                """
            ),
            {"eid": exc.expediente_id},
        )
    ).scalar()
    if vencidas == 0:
        await db.execute(
            text("UPDATE expedientes_personal SET bloqueado_por_excepcion_vencida = FALSE WHERE id = CAST(:eid AS uuid)"),
            {"eid": exc.expediente_id},
        )
    await db.commit()
    return {"excepcion_id": xid, "estatus": "RESUELTA"}


@router.patch("/expedientes/{expediente_id}/avanzar")
async def avanzar_expediente_16_estados(
    expediente_id: str,
    data: AvanzarExpedienteIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.expediente.gestionar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    """
    Gobierno de los 16 estados del expediente:
    - capacitacion_impartida != capacitacion_validada
    - alta_interna_completa != alta_imss_confirmada
    - LISTO_PARA_TRABAJAR != LISTO_MERQRY != LISTO_PRENOMINA
    - Excepcion temporal vencida sin resolver -> BLOQUEO AUTOMATICO (409)
    - Circuito ESPECIAL_CONTABILIDAD nunca pasa a LISTO_MERQRY (solo IMSS_MERQRY -> Merqry)
    """
    eid = _uuid(expediente_id, "Expediente")
    target = data.nuevo_estatus.strip().upper()
    if target not in EXPEDIENTE_16_ESTADOS:
        raise HTTPException(status_code=400, detail=f"Estado '{target}' fuera de los 16 estados válidos.")

    exp = (
        await db.execute(
            text(
                """
                SELECT e.id::text AS id, e.relacion_laboral_id::text AS relacion_laboral_id,
                       e.empresa_id, e.estatus, e.capacitacion_impartida, e.capacitacion_validada,
                       e.alta_interna_completa, e.alta_imss_confirmada, e.epp_critico_entregado,
                       rl.circuito_pago
                FROM expedientes_personal e
                JOIN relaciones_laborales rl ON rl.id = e.relacion_laboral_id
                WHERE e.id = CAST(:id AS uuid)
                FOR UPDATE OF e
                """
            ),
            {"id": eid},
        )
    ).first()
    if not exp:
        raise HTTPException(status_code=404, detail="Expediente no encontrado.")
    assert_scope(actor, "rh.expediente.gestionar", empresa_id=exp.empresa_id, min_level=2)

    cap_imp = exp.capacitacion_impartida if data.capacitacion_impartida is None else data.capacitacion_impartida
    cap_val = exp.capacitacion_validada if data.capacitacion_validada is None else data.capacitacion_validada
    alta_int = exp.alta_interna_completa if data.alta_interna_completa is None else data.alta_interna_completa
    alta_imss = exp.alta_imss_confirmada if data.alta_imss_confirmada is None else data.alta_imss_confirmada

    if cap_val and not cap_imp:
        raise HTTPException(
            status_code=422,
            detail="CAPACITACION_NO_IMPARTIDA: No se puede validar capacitación antes de impartirla.",
        )

    # 1) Verificar excepciones temporales vencidas -> bloqueo automatico
    vencidas = (
        await db.execute(
            text(
                """
                UPDATE update_ready_excepciones
                   SET estatus = 'VENCIDA_BLOQUEADA'
                 WHERE expediente_id = CAST(:eid AS uuid)
                   AND nivel_accion = 'EXCEPCION_TEMPORAL'
                   AND estatus IN ('VIGENTE', 'VENCIDA_BLOQUEADA')
                   AND fecha_limite < CURRENT_DATE
                RETURNING id::text AS id, requisito_omitido, fecha_limite::text AS fecha_limite
                """
            ),
            {"eid": eid},
        )
    ).all()
    if vencidas and target in ("LISTO_PARA_TRABAJAR", "LISTO_MERQRY", "LISTO_PRENOMINA", "ACTIVO"):
        await db.execute(
            text(
                "UPDATE expedientes_personal SET bloqueado_por_excepcion_vencida = TRUE, actualizado_en = NOW() WHERE id = CAST(:eid AS uuid)"
            ),
            {"eid": eid},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "EXCEPCION_TEMPORAL_VENCIDA_BLOQUEO",
                "message": "Expediente bloqueado automáticamente por excepción temporal vencida sin resolver.",
                "excepciones_vencidas": [dict(v._mapping) for v in vencidas],
            },
        )

    # 2) Invariantes para LISTO_PARA_TRABAJAR
    if target == "LISTO_PARA_TRABAJAR":
        contrato_firmado = (
            await db.execute(
                text(
                    "SELECT 1 FROM contratos_laborales WHERE relacion_laboral_id = CAST(:rlid AS uuid) AND estatus = 'FIRMADO' LIMIT 1"
                ),
                {"rlid": exp.relacion_laboral_id},
            )
        ).first()
        if not contrato_firmado:
            raise HTTPException(status_code=409, detail="REQUIERE_CONTRATO_FIRMADO para LISTO_PARA_TRABAJAR.")
        if not cap_val:
            raise HTTPException(
                status_code=409,
                detail="REQUIERE_CAPACITACION_VALIDADA (impartida != validada) para LISTO_PARA_TRABAJAR.",
            )
        if not exp.epp_critico_entregado:
            excepcion_epp = (
                await db.execute(
                    text(
                        """
                        SELECT 1 FROM update_ready_excepciones
                        WHERE expediente_id = CAST(:eid AS uuid)
                          AND nivel_accion = 'EXCEPCION_TEMPORAL'
                          AND requisito_omitido = 'EPP_CRITICO'
                          AND estatus = 'VIGENTE'
                          AND fecha_limite >= CURRENT_DATE
                        LIMIT 1
                        """
                    ),
                    {"eid": eid},
                )
            ).first()
            if not excepcion_epp:
                raise HTTPException(
                    status_code=409,
                    detail="BLOQUEO_EPP_CRITICO: Requiere responsiva de EPP crítico o excepción temporal UPDATE_READY vigente.",
                )

    # 3) Invariantes para LISTO_MERQRY (solo IMSS_MERQRY + alta_imss_confirmada)
    if target == "LISTO_MERQRY":
        if exp.circuito_pago != "IMSS_MERQRY":
            raise HTTPException(
                status_code=409,
                detail="SEPARACION_CIRCUITOS: Personal ESPECIAL_CONTABILIDAD nunca se envía a LISTO_MERQRY; avance a LISTO_PRENOMINA.",
            )
        if not alta_imss:
            raise HTTPException(
                status_code=409,
                detail="ALTA_INTERNA_NO_ES_ALTA_IMSS: Requiere alta_imss_confirmada = TRUE para LISTO_MERQRY.",
            )

    await db.execute(
        text(
            """
            UPDATE expedientes_personal
               SET estatus = :est,
                   capacitacion_impartida = :ci,
                   capacitacion_validada = :cv,
                   alta_interna_completa = :ai,
                   alta_imss_confirmada = :aimss,
                   actualizado_en = NOW()
             WHERE id = CAST(:eid AS uuid)
            """
        ),
        {
            "est": target,
            "ci": cap_imp,
            "cv": cap_val,
            "ai": alta_int,
            "aimss": alta_imss,
            "eid": eid,
        },
    )
    if target == "ACTIVO":
        await db.execute(
            text("UPDATE relaciones_laborales SET estatus = 'ACTIVO', actualizado_en = NOW() WHERE id = CAST(:rlid AS uuid)"),
            {"rlid": exp.relacion_laboral_id},
        )
    await registrar_auditoria(
        db,
        actor,
        modulo="personal",
        accion="AVANZAR_EXPEDIENTE",
        tipo_entidad="EXPEDIENTE",
        id_entidad=eid,
        empresa_id=exp.empresa_id,
        datos_antes={"estatus": exp.estatus},
        datos_despues={"estatus": target},
    )
    await db.commit()
    return {
        "expediente_id": eid,
        "estatus": target,
        "circuito_pago": exp.circuito_pago,
        "capacitacion_validada": cap_val,
        "alta_imss_confirmada": alta_imss,
    }


@router.post("/finiquitos", status_code=status.HTTP_201_CREATED)
async def calcular_y_registrar_finiquito(
    data: CalcularFiniquitoIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.finiquitos.calcular", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    rlid = _uuid(data.relacion_laboral_id, "Relación laboral")
    rel = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, circuito_pago, fecha_ingreso
                FROM relaciones_laborales
                WHERE id = CAST(:id AS uuid)
                """
            ),
            {"id": rlid},
        )
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="Relación laboral no encontrada.")
    assert_scope(actor, "rh.finiquitos.calcular", empresa_id=rel.empresa_id, min_level=3)

    try:
        calc = calcular_finiquito_lft_2026(
            fecha_ingreso=rel.fecha_ingreso,
            fecha_baja=data.fecha_baja,
            salario_diario=Decimal(str(data.salario_diario)),
            motivo_baja=data.motivo_baja,
            dias_salarios_pendientes=Decimal(str(data.dias_salarios_pendientes)),
            deducciones_autorizadas=Decimal(str(data.deducciones_autorizadas)),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    row = (
        await db.execute(
            text(
                """
                INSERT INTO bajas_finiquitos_lft (
                    relacion_laboral_id, empresa_id, circuito_pago, fecha_ingreso, fecha_baja,
                    motivo_baja, salario_diario, dias_trabajados_anio, aguinaldo_proporcional,
                    vacaciones_proporcionales, prima_vacacional, salarios_pendientes,
                    prima_antiguedad, indemnizacion_constitucional, deducciones_autorizadas,
                    total_neto_finiquito, desglose_json, calculado_por_usuario_id
                ) VALUES (
                    CAST(:rlid AS uuid), :emp, :circ, :fi, :fb,
                    :mot, :sal, :dta, :agui, :vac, :pvac, :spen,
                    :pant, :indem, :ded, :tot, CAST(:desg AS jsonb), CAST(:uid AS uuid)
                )
                RETURNING id::text AS id, circuito_pago, aguinaldo_proporcional,
                          vacaciones_proporcionales, prima_vacacional, prima_antiguedad,
                          indemnizacion_constitucional, total_neto_finiquito, estatus
                """
            ),
            {
                "rlid": rlid,
                "emp": rel.empresa_id,
                "circ": rel.circuito_pago,
                "fi": rel.fecha_ingreso,
                "fb": data.fecha_baja,
                "mot": data.motivo_baja,
                "sal": data.salario_diario,
                "dta": calc["dias_trabajados_anio"],
                "agui": calc["aguinaldo_proporcional"],
                "vac": calc["vacaciones_proporcionales"],
                "pvac": calc["prima_vacacional"],
                "spen": calc["salarios_pendientes"],
                "pant": calc["prima_antiguedad"],
                "indem": calc["indemnizacion_constitucional"],
                "ded": calc["deducciones_autorizadas"],
                "tot": calc["total_neto_finiquito"],
                "desg": json.dumps(calc, default=str),
                "uid": actor.usuario_id,
            },
        )
    ).first()

    if data.aplicar_baja_expediente:
        await db.execute(
            text(
                "UPDATE relaciones_laborales SET estatus = 'BAJA', fecha_baja = :fb, actualizado_en = NOW() WHERE id = CAST(:rlid AS uuid)"
            ),
            {"fb": data.fecha_baja, "rlid": rlid},
        )
        await db.execute(
            text(
                "UPDATE expedientes_personal SET estatus = 'BAJA', actualizado_en = NOW() WHERE relacion_laboral_id = CAST(:rlid AS uuid)"
            ),
            {"rlid": rlid},
        )

    await db.commit()
    return dict(row._mapping)
