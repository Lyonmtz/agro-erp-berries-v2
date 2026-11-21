from datetime import date
import json
from typing import Any, Dict, List, Optional
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import get_db
from app.core.security import AuthenticatedActor, assert_scope, require_permission

router = APIRouter(prefix="/api/v1/reclutamiento", tags=["Reclutamiento (Fase 2)"])


class CrearPlazaIn(BaseModel):
    empresa_id: int
    sucursal_id: int
    unidad_operativa_id: Optional[int] = None
    puesto_id: int
    codigo_plaza: str = Field(..., min_length=3, max_length=50)
    headcount_autorizado: int = Field(..., gt=0)


class CrearPerfilVersionIn(BaseModel):
    empresa_id: int
    puesto_id: int
    version_numero: int = Field(..., ge=1)
    titulo_perfil: str = Field(..., min_length=3, max_length=150)
    objetivo: str = Field(..., min_length=5)
    requisitos_json: List[str] = Field(default_factory=list)
    competencias_json: List[str] = Field(default_factory=list)


class SolicitarCoberturaIn(BaseModel):
    plaza_autorizada_id: int
    perfil_version_id: int
    cantidad_solicitada: int = Field(..., gt=0)
    tipo_cobertura: str = Field(..., pattern="^(NUEVA_PLAZA|REEMPLAZO|TEMPORADA)$")
    justificacion: str = Field(..., min_length=5)


class DecidirCoberturaIn(BaseModel):
    decision: str = Field(..., pattern="^(APROBADA|RECHAZADA)$")
    comentarios: Optional[str] = None


class CrearVacanteIn(BaseModel):
    solicitud_cobertura_id: str
    codigo_vacante: str = Field(..., min_length=3, max_length=50)
    canal_tipo: str = Field(default="COSECHA", pattern="^(COSECHA|GENERAL)$")


class PublicarVacanteIn(BaseModel):
    canal: str = Field(..., pattern="^(PORTAL_PUBLICO|WHATSAPP|FERIA_EMPLEO|REFERIDO|BOLSA_LOCAL|INTERNO)$")
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None


class PostularVacanteIn(BaseModel):
    curp: str = Field(..., min_length=18, max_length=18)
    nombre: str = Field(..., min_length=2, max_length=100)
    apellido_paterno: str = Field(..., min_length=2, max_length=100)
    apellido_materno: Optional[str] = None
    telefono: str = Field(..., min_length=7, max_length=25)


class EvaluarRankingIn(BaseModel):
    score_evaluacion: float = Field(..., ge=0, le=100)
    score_entrevista: float = Field(..., ge=0, le=100)
    score_experiencia: float = Field(..., ge=0, le=100)


class DictaminarIn(BaseModel):
    decision: str = Field(..., pattern="^(APROBADO_INGRESO|APROBADO_REINGRESO|RECHAZADO|LISTA_NEGRA)$")
    justificacion: str = Field(..., min_length=5)
    traspasar_a_personal: bool = False
    numero_empleado: Optional[str] = None
    circuito_pago: str = Field(default="IMSS_MERQRY", pattern="^(IMSS_MERQRY|ESPECIAL_CONTABILIDAD)$")
    fecha_ingreso: Optional[date] = None


def _uuid(raw: str, label: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=f"{label} inválido o no encontrado.") from exc


@router.post("/plazas", status_code=status.HTTP_201_CREATED)
async def crear_plaza_autorizada(
    data: CrearPlazaIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.plazas.gestionar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(
        actor,
        "rh.plazas.gestionar",
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        min_level=3,
    )
    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO plazas_autorizadas (
                        empresa_id, sucursal_id, unidad_operativa_id, puesto_id,
                        codigo_plaza, headcount_autorizado, autorizado_por_usuario_id
                    ) VALUES (
                        :emp, :suc, :uo, :pid, :cod, :hc, CAST(:uid AS uuid)
                    )
                    RETURNING id, empresa_id, sucursal_id, unidad_operativa_id, puesto_id,
                              codigo_plaza, headcount_autorizado, headcount_ocupado, estatus
                    """
                ),
                {
                    "emp": data.empresa_id,
                    "suc": data.sucursal_id,
                    "uo": data.unidad_operativa_id,
                    "pid": data.puesto_id,
                    "cod": data.codigo_plaza.strip().upper(),
                    "hc": data.headcount_autorizado,
                    "uid": actor.usuario_id,
                },
            )
        ).first()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="codigo_plaza duplicado o FK inválida.") from exc

    await registrar_auditoria(
        db,
        actor,
        modulo="reclutamiento",
        accion="CREAR_PLAZA_AUTORIZADA",
        tipo_entidad="PLAZA",
        id_entidad=str(row.id),
        empresa_id=data.empresa_id,
        datos_despues=dict(row._mapping),
    )
    await db.commit()
    return dict(row._mapping)


@router.post("/perfiles", status_code=status.HTTP_201_CREATED)
async def crear_perfil_version(
    data: CrearPerfilVersionIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.plazas.gestionar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(actor, "rh.plazas.gestionar", empresa_id=data.empresa_id, min_level=3)
    try:
        row = (
            await db.execute(
                text(
                    """
                    INSERT INTO perfiles_puesto_versiones (
                        empresa_id, puesto_id, version_numero, titulo_perfil, objetivo,
                        requisitos_json, competencias_json, vigente, aprobado_por_usuario_id
                    ) VALUES (
                        :emp, :pid, :ver, :tit, :obj,
                        CAST(:req AS jsonb), CAST(:comp AS jsonb), TRUE, CAST(:uid AS uuid)
                    )
                    RETURNING id, empresa_id, puesto_id, version_numero, titulo_perfil, vigente
                    """
                ),
                {
                    "emp": data.empresa_id,
                    "pid": data.puesto_id,
                    "ver": data.version_numero,
                    "tit": data.titulo_perfil.strip(),
                    "obj": data.objetivo.strip(),
                    "req": json.dumps(data.requisitos_json),
                    "comp": json.dumps(data.competencias_json),
                    "uid": actor.usuario_id,
                },
            )
        ).first()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Versión de perfil ya existente para ese puesto.") from exc

    await db.commit()
    return dict(row._mapping)


@router.post("/coberturas", status_code=status.HTTP_201_CREATED)
async def solicitar_cobertura(
    data: SolicitarCoberturaIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.cobertura.solicitar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    """Regla estructural: la cobertura NO crea estructura; requiere plaza autorizada activa y cupo disponible."""
    plaza = (
        await db.execute(
            text(
                """
                SELECT id, empresa_id, sucursal_id, unidad_operativa_id, puesto_id,
                       headcount_autorizado, headcount_ocupado, estatus
                FROM plazas_autorizadas
                WHERE id = :pid
                """
            ),
            {"pid": data.plaza_autorizada_id},
        )
    ).first()
    if not plaza or plaza.estatus != "ACTIVA":
        raise HTTPException(
            status_code=409,
            detail="COBERTURA_SIN_PLAZA_ACTIVA: La cobertura requiere una plaza autorizada activa.",
        )

    assert_scope(
        actor,
        "rh.cobertura.solicitar",
        empresa_id=plaza.empresa_id,
        sucursal_id=plaza.sucursal_id,
        unidad_operativa_id=plaza.unidad_operativa_id,
        min_level=2,
    )

    disponibles = int(plaza.headcount_autorizado) - int(plaza.headcount_ocupado)
    if data.cantidad_solicitada > disponibles:
        raise HTTPException(
            status_code=409,
            detail=(
                f"CUPO_PLAZA_EXCEDIDO: Solicitadas {data.cantidad_solicitada} > "
                f"posiciones disponibles {disponibles}."
            ),
        )

    row = (
        await db.execute(
            text(
                """
                INSERT INTO solicitudes_cobertura (
                    plaza_autorizada_id, perfil_version_id, empresa_id, sucursal_id,
                    unidad_operativa_id, cantidad_solicitada, tipo_cobertura,
                    justificacion, estatus, solicitado_por_usuario_id
                ) VALUES (
                    :plaza, :perf, :emp, :suc, :uo, :cant, :tipo, :just, 'PENDIENTE', CAST(:uid AS uuid)
                )
                RETURNING id::text AS id, plaza_autorizada_id, perfil_version_id,
                          empresa_id, cantidad_solicitada, tipo_cobertura, estatus
                """
            ),
            {
                "plaza": plaza.id,
                "perf": data.perfil_version_id,
                "emp": plaza.empresa_id,
                "suc": plaza.sucursal_id,
                "uo": plaza.unidad_operativa_id,
                "cant": data.cantidad_solicitada,
                "tipo": data.tipo_cobertura,
                "just": data.justificacion.strip(),
                "uid": actor.usuario_id,
            },
        )
    ).first()

    await registrar_auditoria(
        db,
        actor,
        modulo="reclutamiento",
        accion="SOLICITAR_COBERTURA",
        tipo_entidad="COBERTURA",
        id_entidad=row.id,
        empresa_id=plaza.empresa_id,
        datos_despues=dict(row._mapping),
    )
    await db.commit()
    return dict(row._mapping)


@router.post("/coberturas/{cobertura_id}/decidir")
async def decidir_cobertura(
    cobertura_id: str,
    data: DecidirCoberturaIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.cobertura.aprobar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    cid = _uuid(cobertura_id, "Solicitud de cobertura")
    cob = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, sucursal_id, unidad_operativa_id, estatus
                FROM solicitudes_cobertura
                WHERE id = CAST(:cid AS uuid)
                FOR UPDATE
                """
            ),
            {"cid": cid},
        )
    ).first()
    if not cob:
        raise HTTPException(status_code=404, detail="Solicitud de cobertura no encontrada.")

    assert_scope(
        actor,
        "rh.cobertura.aprobar",
        empresa_id=cob.empresa_id,
        sucursal_id=cob.sucursal_id,
        unidad_operativa_id=cob.unidad_operativa_id,
        min_level=3,
    )
    if cob.estatus != "PENDIENTE":
        raise HTTPException(status_code=409, detail=f"La solicitud ya fue decidida ({cob.estatus}).")

    await db.execute(
        text(
            """
            INSERT INTO aprobaciones_cobertura (
                solicitud_cobertura_id, nivel_autorizacion, decision, comentarios, aprobado_por_usuario_id
            ) VALUES (
                CAST(:cid AS uuid), :niv, :dec, :com, CAST(:uid AS uuid)
            )
            """
        ),
        {
            "cid": cid,
            "niv": actor.max_nivel_autorizacion,
            "dec": data.decision,
            "com": data.comentarios,
            "uid": actor.usuario_id,
        },
    )
    await db.execute(
        text(
            "UPDATE solicitudes_cobertura SET estatus = :dec, actualizado_en = NOW() WHERE id = CAST(:cid AS uuid)"
        ),
        {"dec": data.decision, "cid": cid},
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="reclutamiento",
        accion=f"COBERTURA_{data.decision}",
        tipo_entidad="COBERTURA",
        id_entidad=cid,
        empresa_id=cob.empresa_id,
        datos_despues={"decision": data.decision, "comentarios": data.comentarios},
    )
    await db.commit()
    return {"solicitud_cobertura_id": cid, "estatus": data.decision}


@router.post("/vacantes", status_code=status.HTTP_201_CREATED)
async def crear_vacante(
    data: CrearVacanteIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.vacantes.gestionar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    """Regla estructural: una vacante nace UNICAMENTE de una solicitud de cobertura APROBADA."""
    cid = _uuid(data.solicitud_cobertura_id, "Solicitud de cobertura")
    cob = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, plaza_autorizada_id, perfil_version_id,
                       empresa_id, sucursal_id, unidad_operativa_id, cantidad_solicitada, estatus
                FROM solicitudes_cobertura
                WHERE id = CAST(:cid AS uuid)
                """
            ),
            {"cid": cid},
        )
    ).first()
    if not cob:
        raise HTTPException(status_code=404, detail="Solicitud de cobertura no encontrada.")

    assert_scope(
        actor,
        "rh.vacantes.gestionar",
        empresa_id=cob.empresa_id,
        sucursal_id=cob.sucursal_id,
        unidad_operativa_id=cob.unidad_operativa_id,
        min_level=2,
    )
    if cob.estatus != "APROBADA":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "COBERTURA_NO_APROBADA",
                "message": f"Una vacante solo puede nacer de una cobertura APROBADA (actual: {cob.estatus}).",
            },
        )

    try:
        vac = (
            await db.execute(
                text(
                    """
                    INSERT INTO vacantes (
                        solicitud_cobertura_id, plaza_autorizada_id, perfil_version_id,
                        empresa_id, sucursal_id, unidad_operativa_id, codigo_vacante,
                        canal_tipo, cantidad_posiciones, estatus, creado_por_usuario_id
                    ) VALUES (
                        CAST(:cid AS uuid), :plaza, :perf, :emp, :suc, :uo, :cod,
                        :canal, :cant, 'ABIERTA', CAST(:uid AS uuid)
                    )
                    RETURNING id::text AS id, codigo_vacante, canal_tipo, cantidad_posiciones, estatus
                    """
                ),
                {
                    "cid": cid,
                    "plaza": cob.plaza_autorizada_id,
                    "perf": cob.perfil_version_id,
                    "emp": cob.empresa_id,
                    "suc": cob.sucursal_id,
                    "uo": cob.unidad_operativa_id,
                    "cod": data.codigo_vacante.strip().upper(),
                    "canal": data.canal_tipo,
                    "cant": cob.cantidad_solicitada,
                    "uid": actor.usuario_id,
                },
            )
        ).first()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe vacante para esa cobertura o código duplicado.") from exc

    await db.commit()
    return dict(vac._mapping)


@router.post("/vacantes/{vacante_id}/publicar", status_code=status.HTTP_201_CREATED)
async def publicar_vacante(
    vacante_id: str,
    data: PublicarVacanteIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.vacantes.gestionar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    vid = _uuid(vacante_id, "Vacante")
    vac = (
        await db.execute(
            text("SELECT empresa_id, sucursal_id, unidad_operativa_id FROM vacantes WHERE id = CAST(:vid AS uuid)"),
            {"vid": vid},
        )
    ).first()
    if not vac:
        raise HTTPException(status_code=404, detail="Vacante no encontrada.")
    assert_scope(actor, "rh.vacantes.gestionar", empresa_id=vac.empresa_id, min_level=2)

    row = (
        await db.execute(
            text(
                """
                INSERT INTO publicaciones_vacante (vacante_id, canal, fecha_inicio, fecha_fin, creado_por_usuario_id)
                VALUES (CAST(:vid AS uuid), :canal, COALESCE(:fi, CURRENT_DATE), :ff, CAST(:uid AS uuid))
                RETURNING id::text AS id, vacante_id::text AS vacante_id, canal, activa
                """
            ),
            {
                "vid": vid,
                "canal": data.canal,
                "fi": data.fecha_inicio,
                "ff": data.fecha_fin,
                "uid": actor.usuario_id,
            },
        )
    ).first()
    await db.commit()
    return dict(row._mapping)


@router.post("/vacantes/{vacante_id}/postular", status_code=status.HTTP_201_CREATED)
async def postular_a_vacante(
    vacante_id: str,
    data: PostularVacanteIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.vacantes.gestionar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    vid = _uuid(vacante_id, "Vacante")
    vac = (
        await db.execute(
            text("SELECT empresa_id, estatus FROM vacantes WHERE id = CAST(:vid AS uuid)"),
            {"vid": vid},
        )
    ).first()
    if not vac or vac.estatus != "ABIERTA":
        raise HTTPException(status_code=404, detail="Vacante no encontrada o cerrada.")
    assert_scope(actor, "rh.vacantes.gestionar", empresa_id=vac.empresa_id, min_level=2)

    curp = data.curp.strip().upper()
    prev = (
        await db.execute(
            text(
                """
                SELECT p.id::text AS persona_id, rl.estatus AS rel_estatus, rl.numero_empleado
                FROM personas p
                LEFT JOIN relaciones_laborales rl ON rl.persona_id = p.id
                WHERE p.curp = :c
                ORDER BY rl.creado_en DESC NULLS LAST
                LIMIT 1
                """
            ),
            {"c": curp},
        )
    ).first()

    if prev and prev.rel_estatus == "ACTIVO":
        categoria = "INTERNO"
        alerta = {"tipo": "CANDIDATO_INTERNO_ACTIVO", "numero_empleado": prev.numero_empleado}
    elif prev:
        categoria = "REINGRESO"
        alerta = {"tipo": "REINGRESO_DETECTADO_CURP", "persona_id": prev.persona_id}
    else:
        categoria = "EXTERNO"
        alerta = {}

    row = (
        await db.execute(
            text(
                """
                INSERT INTO postulaciones_rh (
                    vacante_id, empresa_id, curp, nombre, apellido_paterno,
                    apellido_materno, telefono, categoria_candidato, alerta_reingreso
                ) VALUES (
                    CAST(:vid AS uuid), :emp, :curp, :nom, :ap, :am, :tel, :cat, CAST(:al AS jsonb)
                )
                RETURNING id::text AS id, curp, categoria_candidato, alerta_reingreso, estatus
                """
            ),
            {
                "vid": vid,
                "emp": vac.empresa_id,
                "curp": curp,
                "nom": data.nombre.strip(),
                "ap": data.apellido_paterno.strip(),
                "am": data.apellido_materno.strip() if data.apellido_materno else None,
                "tel": data.telefono.strip(),
                "cat": categoria,
                "al": json.dumps(alerta),
            },
        )
    ).first()
    await db.commit()
    return dict(row._mapping)


@router.patch("/postulaciones/{postulacion_id}/evaluar")
async def evaluar_postulacion_ranking(
    postulacion_id: str,
    data: EvaluarRankingIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.vacantes.gestionar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    pid = _uuid(postulacion_id, "Postulación")
    post = (
        await db.execute(
            text("SELECT empresa_id FROM postulaciones_rh WHERE id = CAST(:pid AS uuid)"),
            {"pid": pid},
        )
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="Postulación no encontrada.")
    assert_scope(actor, "rh.vacantes.gestionar", empresa_id=post.empresa_id, min_level=2)

    row = (
        await db.execute(
            text(
                """
                UPDATE postulaciones_rh
                   SET score_evaluacion = :ev,
                       score_entrevista = :en,
                       score_experiencia = :ex,
                       estatus = 'EVALUADO'
                 WHERE id = CAST(:pid AS uuid)
                RETURNING id::text AS id, score_evaluacion, score_entrevista,
                          score_experiencia, ranking_ponderado_60_25_15, estatus
                """
            ),
            {
                "ev": data.score_evaluacion,
                "en": data.score_entrevista,
                "ex": data.score_experiencia,
                "pid": pid,
            },
        )
    ).first()
    await db.commit()
    return dict(row._mapping)


@router.post("/postulaciones/{postulacion_id}/dictaminar", status_code=status.HTTP_201_CREATED)
async def dictaminar_y_traspasar(
    postulacion_id: str,
    data: DictaminarIn,
    actor: AuthenticatedActor = Depends(require_permission("rh.vacantes.gestionar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    pid = _uuid(postulacion_id, "Postulación")
    post = (
        await db.execute(
            text(
                """
                SELECT po.id::text AS id, po.empresa_id, po.curp, po.nombre,
                       po.apellido_paterno, po.apellido_materno, po.telefono,
                       v.sucursal_id, v.unidad_operativa_id, pl.puesto_id, pl.id AS plaza_id
                FROM postulaciones_rh po
                JOIN vacantes v ON v.id = po.vacante_id
                JOIN plazas_autorizadas pl ON pl.id = v.plaza_autorizada_id
                WHERE po.id = CAST(:pid AS uuid)
                """
            ),
            {"pid": pid},
        )
    ).first()
    if not post:
        raise HTTPException(status_code=404, detail="Postulación no encontrada.")

    assert_scope(actor, "rh.vacantes.gestionar", empresa_id=post.empresa_id, min_level=3)

    rel_id = None
    exp_id = None

    if data.traspasar_a_personal and data.decision in ("APROBADO_INGRESO", "APROBADO_REINGRESO"):
        if not data.numero_empleado:
            raise HTTPException(status_code=400, detail="numero_empleado requerido para traspaso a Personal.")

        persona_id = (
            await db.execute(
                text("SELECT id::text FROM personas WHERE curp = :c"),
                {"c": post.curp},
            )
        ).scalar()
        if not persona_id:
            qr = f"QR-PER-{uuid.uuid4().hex[:10].upper()}"
            persona_id = (
                await db.execute(
                    text(
                        """
                        INSERT INTO personas (
                            curp, nombre, apellido_paterno, apellido_materno, telefono, clave_interna_qr
                        ) VALUES (:c, :n, :ap, :am, :tel, :qr)
                        RETURNING id::text
                        """
                    ),
                    {
                        "c": post.curp,
                        "n": post.nombre,
                        "ap": post.apellido_paterno,
                        "am": post.apellido_materno,
                        "tel": post.telefono,
                        "qr": qr,
                    },
                )
            ).scalar()

        rel_id = (
            await db.execute(
                text(
                    """
                    INSERT INTO relaciones_laborales (
                        persona_id, empresa_id, sucursal_id, unidad_operativa_id,
                        numero_empleado, circuito_pago, puesto_nominal_id, fecha_ingreso, estatus
                    ) VALUES (
                        CAST(:pid AS uuid), :emp, :suc, :uo,
                        :num, :circ, :puesto, COALESCE(:fi, CURRENT_DATE), 'PREALTA'
                    )
                    RETURNING id::text
                    """
                ),
                {
                    "pid": persona_id,
                    "emp": post.empresa_id,
                    "suc": post.sucursal_id,
                    "uo": post.unidad_operativa_id,
                    "num": data.numero_empleado.strip().upper(),
                    "circ": data.circuito_pago,
                    "puesto": post.puesto_id,
                    "fi": data.fecha_ingreso,
                },
            )
        ).scalar()

        exp_id = (
            await db.execute(
                text(
                    """
                    INSERT INTO expedientes_personal (
                        relacion_laboral_id, persona_id, empresa_id, sucursal_id, unidad_operativa_id, estatus
                    ) VALUES (
                        CAST(:rlid AS uuid), CAST(:pid AS uuid), :emp, :suc, :uo, 'PREALTA'
                    )
                    RETURNING id::text
                    """
                ),
                {
                    "rlid": rel_id,
                    "pid": persona_id,
                    "emp": post.empresa_id,
                    "suc": post.sucursal_id,
                    "uo": post.unidad_operativa_id,
                },
            )
        ).scalar()

        await db.execute(
            text(
                "UPDATE plazas_autorizadas SET headcount_ocupado = headcount_ocupado + 1 WHERE id = :plid"
            ),
            {"plid": post.plaza_id},
        )

    dictamen = (
        await db.execute(
            text(
                """
                INSERT INTO dictamenes_ingreso_reingreso (
                    postulacion_id, empresa_id, decision, justificacion,
                    dictaminado_por_usuario_id, traspasado_a_relacion_id
                ) VALUES (
                    CAST(:pid AS uuid), :emp, :dec, :just, CAST(:uid AS uuid), CAST(:rlid AS uuid)
                )
                RETURNING id::text AS id, decision, traspasado_a_relacion_id::text AS traspasado_a_relacion_id
                """
            ),
            {
                "pid": pid,
                "emp": post.empresa_id,
                "dec": data.decision,
                "just": data.justificacion.strip(),
                "uid": actor.usuario_id,
                "rlid": rel_id,
            },
        )
    ).first()

    new_post_status = "TRASPASADO_PERSONAL" if rel_id else ("RECHAZADO" if data.decision in ("RECHAZADO", "LISTA_NEGRA") else "DICTAMINADO")
    await db.execute(
        text("UPDATE postulaciones_rh SET estatus = :est WHERE id = CAST(:pid AS uuid)"),
        {"est": new_post_status, "pid": pid},
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="reclutamiento",
        accion="DICTAMINAR_INGRESO",
        tipo_entidad="DICTAMEN",
        id_entidad=dictamen.id,
        empresa_id=post.empresa_id,
        datos_despues={"decision": data.decision, "relacion_laboral_id": rel_id, "expediente_id": exp_id},
    )
    await db.commit()
    return {
        **dict(dictamen._mapping),
        "expediente_id": exp_id,
        "estatus_postulacion": new_post_status,
    }
