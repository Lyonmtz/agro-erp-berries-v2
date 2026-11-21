from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import get_db
from app.core.security import AuthenticatedActor, assert_scope, require_permission
from app.modules.sync_offline.service import run_idempotent_command

router = APIRouter(prefix="/api/v1/cosecha", tags=["Cosecha, Culturales y Cierres (Fase 3B)"])


class AutorizacionOperativaIn(BaseModel):
    empresa_id: int
    sucursal_id: int
    unidad_operativa_id: int
    fecha: date
    tipo_operacion: str = Field(..., pattern="^(COSECHA_VIVO|COSECHA_RETROACTIVA|COSECHA_DOMINGO|LABORES_CULTURALES)$")
    motivo: str = Field(..., min_length=4)


class CapturaCosechaIn(BaseModel):
    client_command_id: Optional[str] = None
    fecha: date
    lote_id: int
    persona_id: str
    relacion_laboral_id: str
    modo_captura: str = Field(default="VIVO", pattern="^(VIVO|RETROACTIVA)$")
    autorizacion_id: Optional[str] = None
    codigo_trazabilidad_caja: str = Field(..., min_length=3, max_length=80)
    cajas_exportacion: float = Field(default=0, ge=0)
    cajas_nacional: float = Field(default=0, ge=0)
    cajas_merma_rezaga: float = Field(default=0, ge=0)
    nip_confirmado: bool = False


class CierreOperativoIn(BaseModel):
    client_command_id: Optional[str] = None
    empresa_id: int
    sucursal_id: Optional[int] = None
    unidad_operativa_id: Optional[int] = None
    fecha: date
    alcance_cierre: str = Field(..., pattern="^(UNIDAD|GLOBAL)$")


class RevisarOficinaIn(BaseModel):
    empresa_id: int
    captura_ids: List[str] = Field(..., min_length=1)
    nuevo_estatus: str = Field(..., pattern="^(EN_REVISION|AUTORIZADA)$")


class CulturalDiarioIn(BaseModel):
    client_command_id: Optional[str] = None
    fecha: date
    lote_id: int
    persona_id: str
    relacion_laboral_id: str
    labor_codigo: str = Field(..., min_length=2, max_length=30)
    unidad_medida: str = Field(..., pattern="^(SURCO|METRO_LINEAL|PLANTA|MACETA|HORA|JORNAL|CAJA)$")
    meta_diaria: Optional[float] = Field(default=None, ge=0)
    cantidad_realizada: float = Field(..., gt=0)
    minutos_trabajados: int = Field(..., gt=0)
    minutos_pausa: int = Field(default=0, ge=0)
    observaciones: Optional[str] = None


class MovilidadPersonaIn(BaseModel):
    persona_id: str
    relacion_laboral_id: str
    fecha: date
    unidad_origen_id: int
    lote_origen_id: Optional[int] = None
    unidad_destino_id: int
    lote_destino_id: Optional[int] = None
    motivo: str = Field(..., min_length=4)


class AvanzarMovilidadIn(BaseModel):
    nuevo_estatus: str = Field(..., pattern="^(SALIDA|TRASLADO_AUTORIZADO|NUEVA_ASIGNACION|CANCELADO)$")


class TrasladoCajasIn(BaseModel):
    fecha: date
    lote_origen_id: int
    folio_remision: str = Field(..., min_length=3, max_length=60)
    cantidad_cajas: float = Field(..., gt=0)
    calidad_fruta: str = Field(default="EXPORTACION", pattern="^(EXPORTACION|NACIONAL|PROCESO_REZAGA)$")
    destino_empaque: str = Field(..., min_length=2, max_length=100)
    vehiculo_clave: Optional[str] = None


class AvanzarTrasladoCajasIn(BaseModel):
    nuevo_estatus: str = Field(..., pattern="^(TRASLADO|RECEPCION_EMPAQUE|EMPACADO|DESPACHO)$")


def _uuid(raw: str, label: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=f"{label} inválido o no encontrado.") from exc


@router.post("/autorizaciones", status_code=status.HTTP_201_CREATED)
async def crear_autorizacion_operativa(
    data: AutorizacionOperativaIn,
    actor: AuthenticatedActor = Depends(require_permission("campo.cosecha.cerrar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(
        actor,
        "campo.cosecha.cerrar",
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        min_level=2,
    )
    row = (
        await db.execute(
            text(
                """
                INSERT INTO campo_autorizaciones_operativas (
                    empresa_id, sucursal_id, unidad_operativa_id, fecha,
                    tipo_operacion, motivo, autorizado_por_usuario_id
                ) VALUES (
                    :emp, :suc, :uo, :f, :tipo, :mot, CAST(:uid AS uuid)
                )
                RETURNING id::text AS id, fecha, tipo_operacion, vigente
                """
            ),
            {
                "emp": data.empresa_id,
                "suc": data.sucursal_id,
                "uo": data.unidad_operativa_id,
                "f": data.fecha,
                "tipo": data.tipo_operacion,
                "mot": data.motivo.strip(),
                "uid": actor.usuario_id,
            },
        )
    ).first()
    await db.commit()
    return dict(row._mapping)


@router.post("/capturas", status_code=status.HTTP_201_CREATED)
async def registrar_captura_cosecha_offline(
    data: CapturaCosechaIn,
    actor: AuthenticatedActor = Depends(require_permission("campo.cosecha.registrar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    """
    Captura de cosecha tablet offline-first endurecida:
    - Idempotente + fencing durable via client_command_id.
    - Bloquea si el lote tiene PHI activo (403) o si el periodo ya fue cerrado por unidad o global (409).
    - Serializa concurrencia contra cierre con pg_advisory_xact_lock(CIERRE_CAMPO:emp:fecha).
    - Alerta merma > 7% sin auto-descontar ni bloquear pago.
    """
    total_cajas = Decimal(str(data.cajas_exportacion)) + Decimal(str(data.cajas_nacional)) + Decimal(str(data.cajas_merma_rezaga))
    if total_cajas <= 0:
        raise HTTPException(status_code=400, detail="Debe registrar al menos una caja (> 0).")

    lote = (
        await db.execute(
            text(
                """
                SELECT l.id, l.empresa_id, uo.sucursal_id, l.unidad_operativa_id,
                       l.cultivo_id, l.estatus_fitosanitario, c.permite_cosecha_domingo
                FROM lotes_produccion l
                JOIN unidades_operativas uo ON uo.id = l.unidad_operativa_id
                JOIN cultivos c ON c.id = l.cultivo_id
                WHERE l.id = :lid AND l.activo = TRUE
                """
            ),
            {"lid": data.lote_id},
        )
    ).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote activo no encontrado.")

    assert_scope(
        actor,
        "campo.cosecha.registrar",
        empresa_id=lote.empresa_id,
        sucursal_id=lote.sucursal_id,
        unidad_operativa_id=lote.unidad_operativa_id,
        min_level=1,
    )

    if lote.estatus_fitosanitario != "LIBRE_CORTE":
        raise HTTPException(status_code=403, detail="BLOQUEO_FITOSANITARIO: Lote en intervalo de seguridad (PHI).")

    pid = _uuid(data.persona_id, "Persona")
    rlid = _uuid(data.relacion_laboral_id, "Relación laboral")
    aut_id = _uuid(data.autorizacion_id, "Autorización") if data.autorizacion_id else None

    es_domingo = data.fecha.weekday() == 6
    if data.modo_captura == "RETROACTIVA" and not aut_id:
        raise HTTPException(
            status_code=409,
            detail="REQUIERE_AUTORIZACION: La captura RETROACTIVA requiere autorizacion_id vigente.",
        )
    if es_domingo and not lote.permite_cosecha_domingo and not aut_id:
        raise HTTPException(
            status_code=403,
            detail="DOMINGO_NO_AUTORIZADO: Este cultivo requiere autorización operativa explícita para cosecha en domingo.",
        )

    rel = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, persona_id::text AS persona_id, empresa_id, circuito_pago, estatus
                FROM relaciones_laborales
                WHERE id = CAST(:rlid AS uuid)
                """
            ),
            {"rlid": rlid},
        )
    ).first()
    if not rel or rel.persona_id != pid or rel.empresa_id != lote.empresa_id:
        raise HTTPException(status_code=400, detail="Relación laboral no corresponde a persona/empresa.")

    async def _exec() -> Dict[str, Any]:
        # Lock transaccional compartido con el flujo de cierre para evitar captura simultanea a cierre
        lock_key = f"CIERRE_CAMPO:{lote.empresa_id}:{data.fecha.isoformat()}"
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": lock_key})

        closed = (
            await db.execute(
                text(
                    """
                    SELECT id::text AS id, alcance_cierre
                    FROM campo_cierres_operativos
                    WHERE empresa_id = :emp
                      AND fecha = :f
                      AND estatus <> 'REABIERTO'
                      AND (alcance_cierre = 'GLOBAL' OR unidad_operativa_id = :uo)
                    LIMIT 1
                    """
                ),
                {"emp": lote.empresa_id, "f": data.fecha, "uo": lote.unidad_operativa_id},
            )
        ).first()
        if closed:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "PERIOD_CLOSED_FOR_CAPTURE",
                    "alcance_cierre": closed.alcance_cierre,
                    "message": f"Captura bloqueada: ya existe cierre ({closed.alcance_cierre}) para {data.fecha}.",
                },
            )

        pct_merma = (
            (Decimal(str(data.cajas_merma_rezaga)) / total_cajas) * Decimal("100")
        ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        alerta_7 = pct_merma > Decimal("7.00")

        try:
            row = (
                await db.execute(
                    text(
                        """
                        INSERT INTO campo_capturas_cosecha (
                            empresa_id, sucursal_id, unidad_operativa_id, fecha, es_domingo,
                            lote_id, cultivo_id, persona_id, relacion_laboral_id, circuito_pago,
                            modo_captura, autorizacion_id, codigo_trazabilidad_caja,
                            cajas_exportacion, cajas_nacional, cajas_merma_rezaga,
                            porcentaje_merma, alerta_merma_7pct, nip_confirmado,
                            estatus_flujo, capturado_por_usuario_id
                        ) VALUES (
                            :emp, :suc, :uo, :f, :dom,
                            :lid, :cid, CAST(:pid AS uuid), CAST(:rlid AS uuid), :circ,
                            :modo, CAST(:aut AS uuid), :qr,
                            :cexp, :cnac, :cmer,
                            :pm, :al7, :nip,
                            'CAPTURADA', CAST(:uid AS uuid)
                        )
                        RETURNING id::text AS id, fecha, es_domingo, circuito_pago,
                                  cajas_exportacion, cajas_nacional, cajas_merma_rezaga,
                                  porcentaje_merma, alerta_merma_7pct, estatus_flujo
                        """
                    ),
                    {
                        "emp": lote.empresa_id,
                        "suc": lote.sucursal_id,
                        "uo": lote.unidad_operativa_id,
                        "f": data.fecha,
                        "dom": es_domingo,
                        "lid": data.lote_id,
                        "cid": lote.cultivo_id,
                        "pid": pid,
                        "rlid": rlid,
                        "circ": rel.circuito_pago,
                        "modo": data.modo_captura,
                        "aut": aut_id,
                        "qr": data.codigo_trazabilidad_caja.strip(),
                        "cexp": data.cajas_exportacion,
                        "cnac": data.cajas_nacional,
                        "cmer": data.cajas_merma_rezaga,
                        "pm": pct_merma,
                        "al7": alerta_7,
                        "nip": data.nip_confirmado,
                        "uid": actor.usuario_id,
                    },
                )
            ).first()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail="codigo_trazabilidad_caja ya capturado.") from exc

        return dict(row._mapping)

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type="CAPTURE_HARVEST",
        payload=data.model_dump(),
        actor=actor,
        empresa_id=lote.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack


@router.post("/cierres", status_code=status.HTTP_201_CREATED)
async def ejecutar_cierre_operativo(
    data: CierreOperativoIn,
    actor: AuthenticatedActor = Depends(require_permission("campo.cosecha.cerrar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    """
    Cierre tecnico diario por UNIDAD o GLOBAL:
    - Cierre GLOBAL exige nivel >= 3 y alcance a nivel empresa (unidad_operativa_id IS NULL).
    - Serializa concurrencia con pg_advisory_xact_lock(CIERRE_CAMPO:emp:fecha):
      * Dos cierres globales -> 409 GLOBAL_CLOSE_ALREADY_EXISTS
      * Cierre unidad tras cierre global -> 409 ALREADY_CLOSED_BY_GLOBAL
      * Cierre global tras cierre unidad -> cierra el resto del dia a nivel empresa
    - NUNCA marca como PAGABLE (es_pagable = FALSE).
    """
    if data.alcance_cierre == "GLOBAL":
        if data.unidad_operativa_id is not None:
            raise HTTPException(status_code=400, detail="Cierre GLOBAL requiere unidad_operativa_id = null.")
        assert_scope(actor, "campo.cosecha.cerrar", empresa_id=data.empresa_id, min_level=3)
    else:
        if data.unidad_operativa_id is None:
            raise HTTPException(status_code=400, detail="Cierre UNIDAD requiere unidad_operativa_id.")
        assert_scope(
            actor,
            "campo.cosecha.cerrar",
            empresa_id=data.empresa_id,
            sucursal_id=data.sucursal_id,
            unidad_operativa_id=data.unidad_operativa_id,
            min_level=2,
        )

    async def _exec() -> Dict[str, Any]:
        lock_key = f"CIERRE_CAMPO:{data.empresa_id}:{data.fecha.isoformat()}"
        await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": lock_key})

        existing_global = (
            await db.execute(
                text(
                    """
                    SELECT id::text AS id FROM campo_cierres_operativos
                    WHERE empresa_id = :emp AND fecha = :f
                      AND alcance_cierre = 'GLOBAL' AND estatus <> 'REABIERTO'
                    LIMIT 1
                    """
                ),
                {"emp": data.empresa_id, "f": data.fecha},
            )
        ).first()
        if existing_global:
            code = "GLOBAL_CLOSE_ALREADY_EXISTS" if data.alcance_cierre == "GLOBAL" else "ALREADY_CLOSED_BY_GLOBAL"
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"code": code, "cierre_global_id": existing_global.id},
            )

        if data.alcance_cierre == "UNIDAD":
            existing_uo = (
                await db.execute(
                    text(
                        """
                        SELECT id::text AS id FROM campo_cierres_operativos
                        WHERE empresa_id = :emp AND unidad_operativa_id = :uo
                          AND fecha = :f AND alcance_cierre = 'UNIDAD' AND estatus <> 'REABIERTO'
                        LIMIT 1
                        """
                    ),
                    {"emp": data.empresa_id, "uo": data.unidad_operativa_id, "f": data.fecha},
                )
            ).first()
            if existing_uo:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={"code": "UNIT_CLOSE_ALREADY_EXISTS", "cierre_unidad_id": existing_uo.id},
                )

        # Calcular totales de capturas aun abiertas en el alcance
        if data.alcance_cierre == "GLOBAL":
            where_cap = "empresa_id = :emp AND fecha = :f AND estatus_flujo = 'CAPTURADA'"
            params_cap = {"emp": data.empresa_id, "f": data.fecha}
        else:
            where_cap = "empresa_id = :emp AND unidad_operativa_id = :uo AND fecha = :f AND estatus_flujo = 'CAPTURADA'"
            params_cap = {"emp": data.empresa_id, "uo": data.unidad_operativa_id, "f": data.fecha}

        tot = (
            await db.execute(
                text(
                    f"""
                    SELECT
                        COUNT(*) AS cnt,
                        COALESCE(SUM(cajas_exportacion), 0) AS cexp,
                        COALESCE(SUM(cajas_nacional), 0) AS cnac,
                        COALESCE(SUM(cajas_merma_rezaga), 0) AS cmer
                    FROM campo_capturas_cosecha
                    WHERE {where_cap}
                    """
                ),
                params_cap,
            )
        ).first()

        cierre = (
            await db.execute(
                text(
                    """
                    INSERT INTO campo_cierres_operativos (
                        empresa_id, sucursal_id, unidad_operativa_id, fecha, alcance_cierre,
                        estatus, total_capturas, total_cajas_exportacion, total_cajas_nacional,
                        total_cajas_merma, es_pagable, cerrado_por_usuario_id
                    ) VALUES (
                        :emp, :suc, :uo, :f, :alc,
                        'CIERRE_TECNICO', :cnt, :cexp, :cnac,
                        :cmer, FALSE, CAST(:uid AS uuid)
                    )
                    RETURNING id::text AS id, empresa_id, unidad_operativa_id, fecha,
                              alcance_cierre, estatus, total_capturas,
                              total_cajas_exportacion, es_pagable
                    """
                ),
                {
                    "emp": data.empresa_id,
                    "suc": data.sucursal_id,
                    "uo": data.unidad_operativa_id,
                    "f": data.fecha,
                    "alc": data.alcance_cierre,
                    "cnt": int(tot.cnt),
                    "cexp": tot.cexp,
                    "cnac": tot.cnac,
                    "cmer": tot.cmer,
                    "uid": actor.usuario_id,
                },
            )
        ).first()

        await db.execute(
            text(
                f"""
                UPDATE campo_capturas_cosecha
                   SET estatus_flujo = 'CIERRE_TECNICO',
                       cierre_operativo_id = CAST(:cid AS uuid)
                 WHERE {where_cap}
                """
            ),
            {**params_cap, "cid": cierre.id},
        )
        await registrar_auditoria(
            db,
            actor,
            modulo="cosecha_tablet",
            accion=f"CIERRE_{data.alcance_cierre}",
            tipo_entidad="CIERRE_OPERATIVO",
            id_entidad=cierre.id,
            empresa_id=data.empresa_id,
            unidad_operativa_id=data.unidad_operativa_id,
            datos_despues=dict(cierre._mapping),
        )
        return dict(cierre._mapping)

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type=f"CLOSE_{data.alcance_cierre}",
        payload=data.model_dump(),
        actor=actor,
        empresa_id=data.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack


@router.post("/capturas/revisar-oficina")
async def revisar_oficina_capturas(
    data: RevisarOficinaIn,
    actor: AuthenticatedActor = Depends(require_permission("campo.cosecha.revisar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """Maquina de estados: CIERRE_TECNICO -> EN_REVISION -> AUTORIZADA (solo oficina L3+)."""
    assert_scope(actor, "campo.cosecha.revisar", empresa_id=data.empresa_id, min_level=3)
    uuids = [_uuid(x, "Captura") for x in data.captura_ids]
    allowed_prev = ("CIERRE_TECNICO",) if data.nuevo_estatus == "EN_REVISION" else ("CIERRE_TECNICO", "EN_REVISION")

    updated = 0
    for cid in uuids:
        res = await db.execute(
            text(
                """
                UPDATE campo_capturas_cosecha
                   SET estatus_flujo = :nest,
                       revisado_por_usuario_id = CAST(:uid AS uuid),
                       revisado_en = NOW()
                 WHERE id = CAST(:cid AS uuid)
                   AND empresa_id = :emp
                   AND estatus_flujo = ANY(:prev)
                """
            ),
            {
                "nest": data.nuevo_estatus,
                "uid": actor.usuario_id,
                "cid": cid,
                "emp": data.empresa_id,
                "prev": list(allowed_prev),
            },
        )
        updated += res.rowcount or 0

    if updated != len(uuids):
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Solo {updated} de {len(uuids)} capturas estaban en estado elegible {allowed_prev}.",
        )
    await db.commit()
    return {"actualizadas": updated, "nuevo_estatus": data.nuevo_estatus}


@router.post("/culturales", status_code=status.HTTP_201_CREATED)
async def capturar_labor_cultural_individual(
    data: CulturalDiarioIn,
    actor: AuthenticatedActor = Depends(require_permission("campo.culturales.capturar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    lote = (
        await db.execute(
            text(
                """
                SELECT l.id, l.empresa_id, uo.sucursal_id, l.unidad_operativa_id
                FROM lotes_produccion l
                JOIN unidades_operativas uo ON uo.id = l.unidad_operativa_id
                WHERE l.id = :lid AND l.activo = TRUE
                """
            ),
            {"lid": data.lote_id},
        )
    ).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote activo no encontrado.")

    assert_scope(
        actor,
        "campo.culturales.capturar",
        empresa_id=lote.empresa_id,
        sucursal_id=lote.sucursal_id,
        unidad_operativa_id=lote.unidad_operativa_id,
        min_level=1,
    )
    pid = _uuid(data.persona_id, "Persona")
    rlid = _uuid(data.relacion_laboral_id, "Relación laboral")

    async def _exec() -> Dict[str, Any]:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO campo_culturales_diarios (
                        empresa_id, sucursal_id, unidad_operativa_id, fecha, lote_id,
                        persona_id, relacion_laboral_id, labor_codigo, unidad_medida,
                        meta_diaria, cantidad_realizada, minutos_trabajados, minutos_pausa,
                        observaciones, capturado_por_usuario_id
                    ) VALUES (
                        :emp, :suc, :uo, :f, :lid,
                        CAST(:pid AS uuid), CAST(:rlid AS uuid), :lab, :um,
                        :meta, :cant, :mins, :pausa,
                        :obs, CAST(:uid AS uuid)
                    )
                    RETURNING id::text AS id, fecha, labor_codigo, unidad_medida,
                              cantidad_realizada, minutos_trabajados, formula_pago_aplicable, estatus_revision
                    """
                ),
                {
                    "emp": lote.empresa_id,
                    "suc": lote.sucursal_id,
                    "uo": lote.unidad_operativa_id,
                    "f": data.fecha,
                    "lid": data.lote_id,
                    "pid": pid,
                    "rlid": rlid,
                    "lab": data.labor_codigo.strip().upper(),
                    "um": data.unidad_medida,
                    "meta": data.meta_diaria,
                    "cant": data.cantidad_realizada,
                    "mins": data.minutos_trabajados,
                    "pausa": data.minutos_pausa,
                    "obs": data.observaciones,
                    "uid": actor.usuario_id,
                },
            )
        ).first()
        return dict(row._mapping)

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type="CAPTURE_CULTURAL_DAILY",
        payload=data.model_dump(),
        actor=actor,
        empresa_id=lote.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack


@router.post("/movilidad-personas", status_code=status.HTTP_201_CREATED)
async def registrar_movilidad_persona(
    data: MovilidadPersonaIn,
    actor: AuthenticatedActor = Depends(require_permission("campo.movilidad.gestionar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    """Flujo exclusivo de movilidad de personas (separado del traslado de cajas)."""
    uo_orig = (
        await db.execute(
            text("SELECT empresa_id, sucursal_id FROM unidades_operativas WHERE id = :id"),
            {"id": data.unidad_origen_id},
        )
    ).first()
    if not uo_orig:
        raise HTTPException(status_code=404, detail="Unidad origen no encontrada.")
    assert_scope(
        actor,
        "campo.movilidad.gestionar",
        empresa_id=uo_orig.empresa_id,
        sucursal_id=uo_orig.sucursal_id,
        unidad_operativa_id=data.unidad_origen_id,
        min_level=1,
    )
    pid = _uuid(data.persona_id, "Persona")
    rlid = _uuid(data.relacion_laboral_id, "Relación laboral")

    row = (
        await db.execute(
            text(
                """
                INSERT INTO campo_movilidad_personas (
                    empresa_id, persona_id, relacion_laboral_id, fecha,
                    unidad_origen_id, lote_origen_id, unidad_destino_id, lote_destino_id,
                    estatus_movilidad, motivo, autorizado_por_usuario_id
                ) VALUES (
                    :emp, CAST(:pid AS uuid), CAST(:rlid AS uuid), :f,
                    :uoo, :lo, :uod, :ld,
                    'ENTREGA', :mot, CAST(:uid AS uuid)
                )
                RETURNING id::text AS id, estatus_movilidad, unidad_origen_id, unidad_destino_id
                """
            ),
            {
                "emp": uo_orig.empresa_id,
                "pid": pid,
                "rlid": rlid,
                "f": data.fecha,
                "uoo": data.unidad_origen_id,
                "lo": data.lote_origen_id,
                "uod": data.unidad_destino_id,
                "ld": data.lote_destino_id,
                "mot": data.motivo.strip(),
                "uid": actor.usuario_id,
            },
        )
    ).first()
    await db.commit()
    return dict(row._mapping)


@router.patch("/movilidad-personas/{mov_id}/avanzar")
async def avanzar_movilidad_persona(
    mov_id: str,
    data: AvanzarMovilidadIn,
    actor: AuthenticatedActor = Depends(require_permission("campo.movilidad.gestionar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    mid = _uuid(mov_id, "Movilidad")
    m = (
        await db.execute(
            text("SELECT empresa_id, estatus_movilidad FROM campo_movilidad_personas WHERE id = CAST(:id AS uuid)"),
            {"id": mid},
        )
    ).first()
    if not m:
        raise HTTPException(status_code=404, detail="Registro de movilidad no encontrado.")

    transitions = {
        "ENTREGA": {"SALIDA", "CANCELADO"},
        "SALIDA": {"TRASLADO_AUTORIZADO", "CANCELADO"},
        "TRASLADO_AUTORIZADO": {"NUEVA_ASIGNACION", "CANCELADO"},
    }
    if data.nuevo_estatus not in transitions.get(m.estatus_movilidad, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Transición de movilidad inválida: {m.estatus_movilidad} -> {data.nuevo_estatus}.",
        )
    await db.execute(
        text(
            "UPDATE campo_movilidad_personas SET estatus_movilidad = :est, actualizado_en = NOW() WHERE id = CAST(:id AS uuid)"
        ),
        {"est": data.nuevo_estatus, "id": mid},
    )
    await db.commit()
    return {"id": mid, "estatus_movilidad": data.nuevo_estatus}


@router.post("/traslados-cajas", status_code=status.HTTP_201_CREATED)
async def registrar_traslado_cajas(
    data: TrasladoCajasIn,
    actor: AuthenticatedActor = Depends(require_permission("campo.movilidad.gestionar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    """Flujo independiente de traslado de cajas a empaque (NO altera ubicacion/asignacion de personas)."""
    lote = (
        await db.execute(
            text(
                """
                SELECT l.id, l.empresa_id, uo.sucursal_id, l.unidad_operativa_id, l.cultivo_id
                FROM lotes_produccion l
                JOIN unidades_operativas uo ON uo.id = l.unidad_operativa_id
                WHERE l.id = :lid
                """
            ),
            {"lid": data.lote_origen_id},
        )
    ).first()
    if not lote:
        raise HTTPException(status_code=404, detail="Lote origen no encontrado.")
    assert_scope(
        actor,
        "campo.movilidad.gestionar",
        empresa_id=lote.empresa_id,
        sucursal_id=lote.sucursal_id,
        unidad_operativa_id=lote.unidad_operativa_id,
        min_level=1,
    )
    row = (
        await db.execute(
            text(
                """
                INSERT INTO campo_traslados_cajas (
                    empresa_id, sucursal_id, unidad_operativa_id, fecha, lote_origen_id,
                    cultivo_id, folio_remision, cantidad_cajas, calidad_fruta,
                    destino_empaque, vehiculo_clave, estatus_traslado, registrado_por_usuario_id
                ) VALUES (
                    :emp, :suc, :uo, :f, :lid,
                    :cid, :fol, :cant, :cal,
                    :dest, :veh, 'RECOLECCION_PARCIAL', CAST(:uid AS uuid)
                )
                RETURNING id::text AS id, folio_remision, cantidad_cajas, estatus_traslado
                """
            ),
            {
                "emp": lote.empresa_id,
                "suc": lote.sucursal_id,
                "uo": lote.unidad_operativa_id,
                "f": data.fecha,
                "lid": data.lote_origen_id,
                "cid": lote.cultivo_id,
                "fol": data.folio_remision.strip().upper(),
                "cant": data.cantidad_cajas,
                "cal": data.calidad_fruta,
                "dest": data.destino_empaque.strip(),
                "veh": data.vehiculo_clave,
                "uid": actor.usuario_id,
            },
        )
    ).first()
    await db.commit()
    return dict(row._mapping)


@router.patch("/traslados-cajas/{traslado_id}/avanzar")
async def avanzar_traslado_cajas(
    traslado_id: str,
    data: AvanzarTrasladoCajasIn,
    actor: AuthenticatedActor = Depends(require_permission("campo.movilidad.gestionar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    tid = _uuid(traslado_id, "Traslado de cajas")
    t = (
        await db.execute(
            text("SELECT estatus_traslado FROM campo_traslados_cajas WHERE id = CAST(:id AS uuid)"),
            {"id": tid},
        )
    ).first()
    if not t:
        raise HTTPException(status_code=404, detail="Traslado de cajas no encontrado.")
    transitions = {
        "RECOLECCION_PARCIAL": {"TRASLADO"},
        "TRASLADO": {"RECEPCION_EMPAQUE"},
        "RECEPCION_EMPAQUE": {"EMPACADO"},
        "EMPACADO": {"DESPACHO"},
    }
    if data.nuevo_estatus not in transitions.get(t.estatus_traslado, set()):
        raise HTTPException(
            status_code=409,
            detail=f"Transición inválida en traslado de cajas: {t.estatus_traslado} -> {data.nuevo_estatus}.",
        )
    await db.execute(
        text(
            "UPDATE campo_traslados_cajas SET estatus_traslado = :est, actualizado_en = NOW() WHERE id = CAST(:id AS uuid)"
        ),
        {"est": data.nuevo_estatus, "id": tid},
    )
    await db.commit()
    return {"id": tid, "estatus_traslado": data.nuevo_estatus}


@router.get("/cuadro-honor")
async def cuadro_de_honor(
    empresa_id: int = Query(...),
    fecha_inicio: date = Query(...),
    fecha_fin: date = Query(...),
    actor: AuthenticatedActor = Depends(require_permission("campo.elegibilidad.leer")),
    db: AsyncSession = Depends(get_db),
):
    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT
                    p.id::text AS persona_id,
                    p.nombre || ' ' || p.apellido_paterno AS trabajador,
                    SUM(c.cajas_exportacion + c.cajas_nacional) AS cajas_validas,
                    SUM(c.cajas_merma_rezaga) AS cajas_merma,
                    ROUND(
                        CASE WHEN SUM(c.cajas_exportacion + c.cajas_nacional + c.cajas_merma_rezaga) > 0
                             THEN (SUM(c.cajas_exportacion) / SUM(c.cajas_exportacion + c.cajas_nacional + c.cajas_merma_rezaga)) * 100
                             ELSE 0 END, 2
                    ) AS pct_exportacion
                FROM campo_capturas_cosecha c
                JOIN personas p ON p.id = c.persona_id
                WHERE c.empresa_id = :emp AND c.fecha BETWEEN :fi AND :ff
                GROUP BY p.id, p.nombre, p.apellido_paterno
                ORDER BY cajas_validas DESC, pct_exportacion DESC
                LIMIT 20
                """
            ),
            {"emp": empresa_id, "fi": fecha_inicio, "ff": fecha_fin},
        )
    ]
    return {"empresa_id": empresa_id, "fecha_inicio": fecha_inicio, "fecha_fin": fecha_fin, "ranking": rows}


@router.get("/mi-consulta/{persona_id}")
async def mi_consulta_trabajador(
    persona_id: str,
    fecha_inicio: date = Query(...),
    fecha_fin: date = Query(...),
    actor: AuthenticatedActor = Depends(require_permission("campo.elegibilidad.leer")),
    db: AsyncSession = Depends(get_db),
):
    pid = _uuid(persona_id, "Persona")
    cosecha = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT fecha, es_domingo, cajas_exportacion, cajas_nacional,
                       cajas_merma_rezaga, porcentaje_merma, alerta_merma_7pct, estatus_flujo
                FROM campo_capturas_cosecha
                WHERE persona_id = CAST(:pid AS uuid) AND fecha BETWEEN :fi AND :ff
                ORDER BY fecha, creado_en
                """
            ),
            {"pid": pid, "fi": fecha_inicio, "ff": fecha_fin},
        )
    ]
    culturales = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                """
                SELECT fecha, labor_codigo, unidad_medida, cantidad_realizada,
                       minutos_trabajados, estatus_revision
                FROM campo_culturales_diarios
                WHERE persona_id = CAST(:pid AS uuid) AND fecha BETWEEN :fi AND :ff
                ORDER BY fecha, creado_en
                """
            ),
            {"pid": pid, "fi": fecha_inicio, "ff": fecha_fin},
        )
    ]
    return {"persona_id": pid, "cosecha": cosecha, "culturales": culturales}
