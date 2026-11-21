from datetime import date, datetime, timedelta, timezone
import hashlib
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
from app.modules.sync_offline.service import run_idempotent_command

router = APIRouter(prefix="/api/v1/trasplante", tags=["Trasplante Multi-Camión (Fase 3A)"])

ALLOWED_PLANT_UNITS = {
    "PLANTS",
    "CANES",
    "GRADE_A",
    "SINGLES",
    "CHAROLA",
    "MACETA",
    "RAIZ_DESNUDA",
    "CEPELLON",
}


# ---------------------------------------------------------------------------
# Schemas Pydantic
# ---------------------------------------------------------------------------
class ProgramarLlegadaIn(BaseModel):
    empresa_id: int
    sucursal_id: int
    unidad_operativa_id: int
    orden_compra_ref: str = Field(..., min_length=2, max_length=60)
    numero_camion_plan: int = Field(..., ge=1)
    proveedor: str = Field(..., min_length=2, max_length=120)
    variedad_id: Optional[int] = None
    unidad_planta: str
    cantidad_documental: int = Field(..., gt=0)
    bins_esperados: Optional[int] = Field(default=None, gt=0)
    cajas_plasticas_retornables_esperadas: Optional[int] = Field(default=None, ge=0)
    fecha_arribo_estimada: date
    fuente_documental: Optional[str] = None


class EditarProgramacionIn(BaseModel):
    cantidad_documental: Optional[int] = Field(default=None, gt=0)
    bins_esperados: Optional[int] = Field(default=None, gt=0)
    fecha_arribo_estimada: Optional[date] = None
    fuente_documental: Optional[str] = None


class DeclareTruckIn(BaseModel):
    client_command_id: Optional[str] = None
    empresa_id: int
    sucursal_id: int
    unidad_operativa_id: int
    programacion_id: Optional[str] = None
    codigo_camion: str = Field(..., min_length=2, max_length=50)
    guia_remision: Optional[str] = None
    placas_transporte: Optional[str] = None
    chofer_nombre: Optional[str] = None
    proveedor: str = Field(..., min_length=2, max_length=120)
    variedad_id: Optional[int] = None
    cajas_plasticas_recibidas: int = Field(default=0, ge=0)


class BinReceiveIn(BaseModel):
    client_command_id: Optional[str] = None
    bin_code: str = Field(..., min_length=1, max_length=40)
    unidad_planta: str
    cantidad_recibida: int = Field(..., gt=0)


class BinReleaseIn(BaseModel):
    client_command_id: Optional[str] = None
    cantidad: int = Field(..., gt=0)


class BinFinalizeItem(BaseModel):
    bin_id: str
    cantidad_aceptada: int = Field(..., ge=0)
    cantidad_rechazada: int = Field(..., ge=0)
    motivo_rechazo: Optional[str] = None


class FinalizeReceiptIn(BaseModel):
    client_command_id: Optional[str] = None
    bins: List[BinFinalizeItem] = Field(..., min_length=1)
    cajas_plasticas_devueltas: Optional[int] = Field(default=None, ge=0)
    notas_cierre: Optional[str] = None


class CrearAsignacionIn(BaseModel):
    client_command_id: Optional[str] = None
    fecha: date
    camion_lote_id: str
    bin_id: str
    lote_id: int
    tunel_numero: int = Field(..., ge=1)
    equipo_lado: str = Field(..., pattern="^(NORTE|SUR)$")
    linea_inicio: int = Field(..., ge=1)
    linea_fin: int = Field(..., ge=1)
    funcion_codigo: str = Field(..., pattern="^(SUPPLY|MOVE|TRANSPLANT|CLIPS|BARRER)$")
    participantes_persona_ids: List[str] = Field(..., min_length=1)
    cross_batch_continuation_of: Optional[str] = None


class CambiarEstadoAsignacionIn(BaseModel):
    client_command_id: Optional[str] = None
    accion: str = Field(..., pattern="^(START|PAUSE|RESUME|CHANGE_FUNCTION|FINISH|CANCEL)$")
    nueva_funcion_codigo: Optional[str] = Field(
        default=None, pattern="^(SUPPLY|MOVE|TRANSPLANT|CLIPS|BARRER)$"
    )
    motivo_cambio: Optional[str] = None


class RegistrarProduccionIn(BaseModel):
    client_command_id: Optional[str] = None
    linea_inicio: int = Field(..., ge=1)
    linea_fin: int = Field(..., ge=1)
    unidad_planta: str
    cantidad_trasplantada: int = Field(..., gt=0)


class SolicitarReviewTokenIn(BaseModel):
    persona_id: str
    camion_lote_id: str
    fecha: date


class ClosePersonDayIn(BaseModel):
    client_command_id: Optional[str] = None
    persona_id: str
    camion_lote_id: str
    fecha: date
    review_token: str


# ---------------------------------------------------------------------------
# Helpers internos (ledger derivado, locks, validaciones)
# ---------------------------------------------------------------------------
def _parse_uuid(raw: str, label: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail=f"{label} inválido o no encontrado.") from exc


async def _get_bin_derived_stock(db: AsyncSession, bin_id: str) -> Dict[str, Any]:
    """Unica fuente de verdad: stock derivado estrictamente desde trasplante_bins + trasplante_bins_ledger."""
    row = (
        await db.execute(
            text(
                """
                SELECT
                    b.id::text AS bin_id,
                    b.camion_lote_id::text AS camion_lote_id,
                    b.empresa_id,
                    b.unidad_operativa_id,
                    b.bin_code,
                    b.unidad_planta,
                    b.cantidad_recibida,
                    b.cantidad_aceptada,
                    b.cantidad_rechazada,
                    COALESCE(SUM(CASE WHEN l.tipo_evento = 'BIN_RELEASE' THEN l.cantidad ELSE 0 END), 0) AS liberado,
                    COALESCE(SUM(CASE WHEN l.tipo_evento = 'TRANSPLANT_CONSUME' THEN l.cantidad ELSE 0 END), 0) AS consumido,
                    COALESCE(SUM(CASE WHEN l.tipo_evento = 'BIN_REJECT_FINAL' THEN l.cantidad ELSE 0 END), 0) AS rechazado_ledger
                FROM trasplante_bins b
                LEFT JOIN trasplante_bins_ledger l ON l.bin_id = b.id
                WHERE b.id = CAST(:bid AS uuid)
                GROUP BY b.id
                """
            ),
            {"bid": bin_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Bin no encontrado.")
    disponible = int(row.liberado) - int(row.consumido)
    return {
        "bin_id": row.bin_id,
        "camion_lote_id": row.camion_lote_id,
        "empresa_id": row.empresa_id,
        "unidad_operativa_id": row.unidad_operativa_id,
        "bin_code": row.bin_code,
        "unidad_planta": row.unidad_planta,
        "cantidad_recibida": int(row.cantidad_recibida),
        "cantidad_aceptada": row.cantidad_aceptada,
        "cantidad_rechazada": row.cantidad_rechazada,
        "liberado": int(row.liberado),
        "consumido": int(row.consumido),
        "disponible": disponible,
    }


async def _check_transplant_range_overlap(
    db: AsyncSession,
    *,
    empresa_id: int,
    lote_id: int,
    tunel_numero: int,
    equipo_lado: str,
    linea_inicio: int,
    linea_fin: int,
    exclude_asig_id: Optional[str] = None,
    continuation_source_id: Optional[str] = None,
) -> None:
    """
    Impide solapamiento fisico de rangos [linea_inicio, linea_fin] para funcion TRANSPLANT
    sobre (empresa_id, lote_id, tunel_numero, equipo_lado), usando advisory lock transaccional.
    """
    lock_key = f"TR_RANGE:{empresa_id}:{lote_id}:{tunel_numero}:{equipo_lado}"
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": lock_key})

    clauses = [
        "empresa_id = :emp",
        "lote_id = :lote",
        "tunel_numero = :tun",
        "equipo_lado = :lado",
        "funcion_codigo = 'TRANSPLANT'",
        "estatus IN ('ASSIGNED', 'RUNNING', 'PAUSED', 'FINISHED')",
        "linea_inicio <= :lfin",
        "linea_fin >= :lini",
    ]
    params: Dict[str, Any] = {
        "emp": empresa_id,
        "lote": lote_id,
        "tun": tunel_numero,
        "lado": equipo_lado,
        "lini": linea_inicio,
        "lfin": linea_fin,
    }
    if exclude_asig_id:
        clauses.append("id <> CAST(:exid AS uuid)")
        params["exid"] = exclude_asig_id
    if continuation_source_id:
        clauses.append("id <> CAST(:contid AS uuid)")
        params["contid"] = continuation_source_id

    conflict = (
        await db.execute(
            text(
                f"""
                SELECT id::text AS id, linea_inicio, linea_fin, estatus
                FROM trasplante_asignaciones
                WHERE {' AND '.join(clauses)}
                LIMIT 1
                """
            ),
            params,
        )
    ).first()
    if conflict:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "LINE_RANGE_OVERLAP",
                "message": (
                    f"Solapamiento físico en túnel {tunel_numero} lado {equipo_lado}: "
                    f"rango solicitado [{linea_inicio}-{linea_fin}] choca con [{conflict.linea_inicio}-{conflict.linea_fin}]."
                ),
            },
        )


async def _compute_person_day_snapshot(
    db: AsyncSession, persona_id: str, camion_lote_id: str, fecha: date
) -> Dict[str, Any]:
    asigs = (
        await db.execute(
            text(
                """
                SELECT
                    a.id::text AS id,
                    a.estatus,
                    a.funcion_codigo,
                    a.lote_id,
                    a.tunel_numero,
                    a.equipo_lado,
                    a.linea_inicio,
                    a.linea_fin,
                    a.actualizado_en::text AS actualizado_en
                FROM trasplante_asignaciones a
                JOIN trasplante_asignacion_participantes ap ON ap.asignacion_id = a.id
                WHERE ap.persona_id = CAST(:pid AS uuid)
                  AND a.camion_lote_id = CAST(:cid AS uuid)
                  AND a.fecha = :f
                ORDER BY a.id
                """
            ),
            {"pid": persona_id, "cid": camion_lote_id, "f": fecha},
        )
    ).all()

    asig_list = [dict(r._mapping) for r in asigs]

    mins_row = (
        await db.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(COALESCE(st.minutos_activos, 0)), 0) AS total_minutos,
                    COUNT(*) FILTER (WHERE st.fin_en IS NULL) AS segmentos_abiertos
                FROM trasplante_segmentos_tiempo st
                JOIN trasplante_asignaciones a ON a.id = st.asignacion_id
                JOIN trasplante_asignacion_participantes ap ON ap.asignacion_id = a.id
                WHERE ap.persona_id = CAST(:pid AS uuid)
                  AND a.camion_lote_id = CAST(:cid AS uuid)
                  AND a.fecha = :f
                """
            ),
            {"pid": persona_id, "cid": camion_lote_id, "f": fecha},
        )
    ).first()

    prod_row = (
        await db.execute(
            text(
                """
                SELECT COALESCE(SUM(pl.cantidad_trasplantada), 0) AS total_plantas
                FROM trasplante_produccion_lineas pl
                JOIN trasplante_asignaciones a ON a.id = pl.asignacion_id
                JOIN trasplante_asignacion_participantes ap ON ap.asignacion_id = a.id
                WHERE ap.persona_id = CAST(:pid AS uuid)
                  AND a.camion_lote_id = CAST(:cid AS uuid)
                  AND a.fecha = :f
                """
            ),
            {"pid": persona_id, "cid": camion_lote_id, "f": fecha},
        )
    ).first()

    canonical = json.dumps(
        {
            "persona_id": persona_id,
            "camion_lote_id": camion_lote_id,
            "fecha": fecha.isoformat(),
            "asignaciones": asig_list,
            "total_plantas": int(prod_row.total_plantas),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    snap_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return {
        "snapshot_sha256": snap_hash,
        "asignaciones": asig_list,
        "total_minutos": float(mins_row.total_minutos),
        "segmentos_abiertos": int(mins_row.segmentos_abiertos),
        "total_plantas": int(prod_row.total_plantas),
    }


# ---------------------------------------------------------------------------
# 1. PROGRAMACION PREVIA DE LLEGADAS (DOCUMENTAL — SIN STOCK)
# ---------------------------------------------------------------------------
@router.post("/programacion", status_code=status.HTTP_201_CREATED)
async def crear_programacion_llegada(
    data: ProgramarLlegadaIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.programar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(
        actor,
        "trasplante.programar",
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        min_level=3,
    )
    unit = data.unidad_planta.strip().upper()
    if unit not in ALLOWED_PLANT_UNITS:
        raise HTTPException(status_code=400, detail=f"unidad_planta '{unit}' no permitida.")

    row = (
        await db.execute(
            text(
                """
                INSERT INTO trasplante_programacion_llegadas (
                    empresa_id, sucursal_id, unidad_operativa_id, orden_compra_ref,
                    numero_camion_plan, proveedor, variedad_id, unidad_planta,
                    cantidad_documental, bins_esperados, cajas_plasticas_retornables_esperadas,
                    fecha_arribo_estimada, fuente_documental, creado_por_usuario_id
                ) VALUES (
                    :emp, :suc, :uo, :oc, :num, :prov, :var, :unit,
                    :cant, :bins, :cajas, :fecha, :fuente, CAST(:uid AS uuid)
                )
                RETURNING id::text AS id, empresa_id, unidad_operativa_id, orden_compra_ref,
                          numero_camion_plan, unidad_planta, cantidad_documental,
                          plan_version, mapping_invalidado, estatus
                """
            ),
            {
                "emp": data.empresa_id,
                "suc": data.sucursal_id,
                "uo": data.unidad_operativa_id,
                "oc": data.orden_compra_ref.strip(),
                "num": data.numero_camion_plan,
                "prov": data.proveedor.strip(),
                "var": data.variedad_id,
                "unit": unit,
                "cant": data.cantidad_documental,
                "bins": data.bins_esperados,
                "cajas": data.cajas_plasticas_retornables_esperadas,
                "fecha": data.fecha_arribo_estimada,
                "fuente": data.fuente_documental,
                "uid": actor.usuario_id,
            },
        )
    ).first()

    await registrar_auditoria(
        db,
        actor,
        modulo="trasplante_recepcion",
        accion="PROGRAMAR_LLEGADA_DOCUMENTAL",
        tipo_entidad="TRASPLANTE_PLAN",
        id_entidad=row.id,
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        datos_despues=dict(row._mapping),
    )
    await db.commit()
    return {**dict(row._mapping), "promovido_a_stock": False}


@router.patch("/programacion/{plan_id}")
async def editar_programacion_llegada(
    plan_id: str,
    data: EditarProgramacionIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.programar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """Editar el plan incrementa plan_version e invalida el mapeo previo a lotes de recepcion."""
    pid = _parse_uuid(plan_id, "Programación")
    plan = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, sucursal_id, unidad_operativa_id, plan_version
                FROM trasplante_programacion_llegadas
                WHERE id = CAST(:pid AS uuid)
                """
            ),
            {"pid": pid},
        )
    ).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Programación no encontrada.")

    assert_scope(
        actor,
        "trasplante.programar",
        empresa_id=plan.empresa_id,
        sucursal_id=plan.sucursal_id,
        unidad_operativa_id=plan.unidad_operativa_id,
        min_level=3,
    )

    sets = ["plan_version = plan_version + 1", "mapping_invalidado = TRUE", "actualizado_en = NOW()"]
    params: Dict[str, Any] = {"pid": pid}
    if data.cantidad_documental is not None:
        sets.append("cantidad_documental = :cant")
        params["cant"] = data.cantidad_documental
    if data.bins_esperados is not None:
        sets.append("bins_esperados = :bins")
        params["bins"] = data.bins_esperados
    if data.fecha_arribo_estimada is not None:
        sets.append("fecha_arribo_estimada = :f")
        params["f"] = data.fecha_arribo_estimada
    if data.fuente_documental is not None:
        sets.append("fuente_documental = :fuente")
        params["fuente"] = data.fuente_documental

    updated = (
        await db.execute(
            text(
                f"""
                UPDATE trasplante_programacion_llegadas
                   SET {', '.join(sets)}
                 WHERE id = CAST(:pid AS uuid)
                RETURNING id::text AS id, plan_version, mapping_invalidado, cantidad_documental
                """
            ),
            params,
        )
    ).first()
    await db.commit()
    return dict(updated._mapping)


# ---------------------------------------------------------------------------
# 2. RECEPCION DOCUMENTAL-FISICA POR CAMION/BIN (DOCUMENTARY_TRUCK_FINAL_V1)
# ---------------------------------------------------------------------------
@router.post("/camiones/declare", status_code=status.HTTP_201_CREATED)
async def declare_truck(
    data: DeclareTruckIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.recepcionar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    assert_scope(
        actor,
        "trasplante.recepcionar",
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        min_level=1,
    )

    async def _exec() -> Dict[str, Any]:
        prog_uuid = _parse_uuid(data.programacion_id, "Programación") if data.programacion_id else None
        prog_ver = None
        if prog_uuid:
            prog = (
                await db.execute(
                    text("SELECT plan_version FROM trasplante_programacion_llegadas WHERE id = CAST(:pid AS uuid)"),
                    {"pid": prog_uuid},
                )
            ).first()
            if not prog:
                raise HTTPException(status_code=404, detail="Programación referenciada no existe.")
            prog_ver = int(prog.plan_version)
            await db.execute(
                text(
                    """
                    UPDATE trasplante_programacion_llegadas
                       SET estatus = 'ARRIBADO', mapping_invalidado = FALSE, actualizado_en = NOW()
                     WHERE id = CAST(:pid AS uuid)
                    """
                ),
                {"pid": prog_uuid},
            )

        try:
            row = (
                await db.execute(
                    text(
                        """
                        INSERT INTO trasplante_camiones_lotes (
                            empresa_id, sucursal_id, unidad_operativa_id,
                            programacion_id, programacion_version_snapshot,
                            codigo_camion, guia_remision, placas_transporte, chofer_nombre,
                            proveedor, variedad_id, cajas_plasticas_recibidas,
                            estatus, verified, declarado_por_usuario_id
                        ) VALUES (
                            :emp, :suc, :uo,
                            CAST(:pid AS uuid), :pver,
                            :cod, :guia, :placas, :chofer,
                            :prov, :var, :cajas,
                            'DECLARED', FALSE, CAST(:uid AS uuid)
                        )
                        RETURNING id::text AS id, empresa_id, unidad_operativa_id,
                                  codigo_camion, estatus, verified, cajas_plasticas_recibidas
                        """
                    ),
                    {
                        "emp": data.empresa_id,
                        "suc": data.sucursal_id,
                        "uo": data.unidad_operativa_id,
                        "pid": prog_uuid,
                        "pver": prog_ver,
                        "cod": data.codigo_camion.strip().upper(),
                        "guia": data.guia_remision,
                        "placas": data.placas_transporte,
                        "chofer": data.chofer_nombre,
                        "prov": data.proveedor.strip(),
                        "var": data.variedad_id,
                        "cajas": data.cajas_plasticas_recibidas,
                        "uid": actor.usuario_id,
                    },
                )
            ).first()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail="codigo_camion ya declarado en la empresa.") from exc

        await registrar_auditoria(
            db,
            actor,
            modulo="trasplante_recepcion",
            accion="DECLARE_TRUCK",
            tipo_entidad="TRASPLANTE_CAMION",
            id_entidad=row.id,
            empresa_id=data.empresa_id,
            sucursal_id=data.sucursal_id,
            unidad_operativa_id=data.unidad_operativa_id,
            datos_despues=dict(row._mapping),
        )
        return dict(row._mapping)

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type="DECLARE_TRUCK",
        payload=data.model_dump(),
        actor=actor,
        empresa_id=data.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack


@router.post("/camiones/{camion_id}/bins/receive", status_code=status.HTTP_201_CREATED)
async def bin_receive(
    camion_id: str,
    data: BinReceiveIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.recepcionar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    """
    BIN_RECEIVE: registra conteo fisico del bin manteniendo cantidad_rechazada = NULL
    hasta FINALIZE_RECEIPT (cero auto-merma). No libera stock hasta BIN_RELEASE.
    """
    cid = _parse_uuid(camion_id, "Camión")
    camion = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, sucursal_id, unidad_operativa_id, estatus
                FROM trasplante_camiones_lotes
                WHERE id = CAST(:cid AS uuid)
                """
            ),
            {"cid": cid},
        )
    ).first()
    if not camion:
        raise HTTPException(status_code=404, detail="Camión no encontrado.")

    assert_scope(
        actor,
        "trasplante.recepcionar",
        empresa_id=camion.empresa_id,
        sucursal_id=camion.sucursal_id,
        unidad_operativa_id=camion.unidad_operativa_id,
        min_level=1,
    )
    if camion.estatus == "FINALIZED":
        raise HTTPException(status_code=409, detail="El camión ya está FINALIZED; no admite nuevos bins.")

    unit = data.unidad_planta.strip().upper()
    if unit not in ALLOWED_PLANT_UNITS:
        raise HTTPException(status_code=400, detail=f"unidad_planta '{unit}' no permitida.")

    async def _exec() -> Dict[str, Any]:
        try:
            b = (
                await db.execute(
                    text(
                        """
                        INSERT INTO trasplante_bins (
                            camion_lote_id, empresa_id, unidad_operativa_id,
                            bin_code, unidad_planta, cantidad_recibida,
                            cantidad_aceptada, cantidad_rechazada, recibido_por_usuario_id
                        ) VALUES (
                            CAST(:cid AS uuid), :emp, :uo,
                            :bcode, :unit, :cant,
                            NULL, NULL, CAST(:uid AS uuid)
                        )
                        RETURNING id::text AS id, camion_lote_id::text AS camion_lote_id,
                                  bin_code, unidad_planta, cantidad_recibida,
                                  cantidad_aceptada, cantidad_rechazada
                        """
                    ),
                    {
                        "cid": cid,
                        "emp": camion.empresa_id,
                        "uo": camion.unidad_operativa_id,
                        "bcode": data.bin_code.strip().upper(),
                        "unit": unit,
                        "cant": data.cantidad_recibida,
                        "uid": actor.usuario_id,
                    },
                )
            ).first()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail="bin_code ya recibido en este camión.") from exc

        await db.execute(
            text(
                """
                INSERT INTO trasplante_bins_ledger (
                    bin_id, camion_lote_id, empresa_id, unidad_operativa_id,
                    unidad_planta, tipo_evento, cantidad, actor_usuario_id
                ) VALUES (
                    CAST(:bid AS uuid), CAST(:cid AS uuid), :emp, :uo,
                    :unit, 'BIN_RECEIVE', :cant, CAST(:uid AS uuid)
                )
                """
            ),
            {
                "bid": b.id,
                "cid": cid,
                "emp": camion.empresa_id,
                "uo": camion.unidad_operativa_id,
                "unit": unit,
                "cant": data.cantidad_recibida,
                "uid": actor.usuario_id,
            },
        )
        if camion.estatus == "DECLARED":
            await db.execute(
                text(
                    "UPDATE trasplante_camiones_lotes SET estatus = 'RECEIVING' WHERE id = CAST(:cid AS uuid)"
                ),
                {"cid": cid},
            )
        return {**dict(b._mapping), "stock_disponible": 0}

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type="BIN_RECEIVE",
        payload={"camion_id": cid, **data.model_dump()},
        actor=actor,
        empresa_id=camion.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack


@router.post("/bins/{bin_id}/release")
async def bin_release(
    bin_id: str,
    data: BinReleaseIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.recepcionar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    """BIN_RELEASE: libera explicitamente plantas del bin hacia stock disponible (ledger derivado)."""
    bid = _parse_uuid(bin_id, "Bin")
    b = (
        await db.execute(
            text(
                """
                SELECT b.id::text AS id, b.camion_lote_id::text AS camion_lote_id,
                       b.empresa_id, c.sucursal_id, b.unidad_operativa_id,
                       b.unidad_planta, b.cantidad_recibida, c.estatus AS camion_estatus
                FROM trasplante_bins b
                JOIN trasplante_camiones_lotes c ON c.id = b.camion_lote_id
                WHERE b.id = CAST(:bid AS uuid)
                FOR UPDATE OF b
                """
            ),
            {"bid": bid},
        )
    ).first()
    if not b:
        raise HTTPException(status_code=404, detail="Bin no encontrado.")

    assert_scope(
        actor,
        "trasplante.recepcionar",
        empresa_id=b.empresa_id,
        sucursal_id=b.sucursal_id,
        unidad_operativa_id=b.unidad_operativa_id,
        min_level=1,
    )
    if b.camion_estatus == "FINALIZED":
        raise HTTPException(status_code=409, detail="Camión FINALIZED; no se puede liberar más stock.")

    async def _exec() -> Dict[str, Any]:
        stock = await _get_bin_derived_stock(db, bid)
        if stock["liberado"] + data.cantidad > stock["cantidad_recibida"]:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Liberación excede recibido del bin: ya liberado {stock['liberado']} + "
                    f"{data.cantidad} > recibido {stock['cantidad_recibida']}."
                ),
            )

        await db.execute(
            text(
                """
                INSERT INTO trasplante_bins_ledger (
                    bin_id, camion_lote_id, empresa_id, unidad_operativa_id,
                    unidad_planta, tipo_evento, cantidad, actor_usuario_id
                ) VALUES (
                    CAST(:bid AS uuid), CAST(:cid AS uuid), :emp, :uo,
                    :unit, 'BIN_RELEASE', :cant, CAST(:uid AS uuid)
                )
                """
            ),
            {
                "bid": bid,
                "cid": b.camion_lote_id,
                "emp": b.empresa_id,
                "uo": b.unidad_operativa_id,
                "unit": b.unidad_planta,
                "cant": data.cantidad,
                "uid": actor.usuario_id,
            },
        )
        return await _get_bin_derived_stock(db, bid)

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type="BIN_RELEASE",
        payload={"bin_id": bid, **data.model_dump()},
        actor=actor,
        empresa_id=b.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack


@router.get("/bins/{bin_id}/stock")
async def obtener_stock_bin(
    bin_id: str,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.operar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    bid = _parse_uuid(bin_id, "Bin")
    stock = await _get_bin_derived_stock(db, bid)
    return stock


@router.post("/camiones/{camion_id}/finish")
async def finish_truck(
    camion_id: str,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.finalizar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    cid = _parse_uuid(camion_id, "Camión")
    camion = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, sucursal_id, unidad_operativa_id, estatus
                FROM trasplante_camiones_lotes
                WHERE id = CAST(:cid AS uuid)
                """
            ),
            {"cid": cid},
        )
    ).first()
    if not camion:
        raise HTTPException(status_code=404, detail="Camión no encontrado.")

    assert_scope(
        actor,
        "trasplante.finalizar",
        empresa_id=camion.empresa_id,
        sucursal_id=camion.sucursal_id,
        unidad_operativa_id=camion.unidad_operativa_id,
        min_level=3,
    )
    if camion.estatus == "FINALIZED":
        raise HTTPException(status_code=409, detail="El camión ya fue FINALIZED.")

    await db.execute(
        text(
            """
            UPDATE trasplante_camiones_lotes
               SET estatus = 'FINISHED_OPERATIONAL', finalizado_operativo_en = NOW()
             WHERE id = CAST(:cid AS uuid)
            """
        ),
        {"cid": cid},
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="trasplante_recepcion",
        accion="FINISH_TRUCK",
        tipo_entidad="TRASPLANTE_CAMION",
        id_entidad=cid,
        empresa_id=camion.empresa_id,
        sucursal_id=camion.sucursal_id,
        unidad_operativa_id=camion.unidad_operativa_id,
    )
    await db.commit()
    return {"camion_id": cid, "estatus": "FINISHED_OPERATIONAL", "verified": False}


@router.post("/camiones/{camion_id}/finalize-receipt")
async def finalize_receipt(
    camion_id: str,
    data: FinalizeReceiptIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.finalizar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """
    FINALIZE_RECEIPT (DOCUMENTARY_TRUCK_FINAL_V1):
    Conciliacion total inmutable por bin: exige accepted + rejected == received
    para todos los bins del camion; solo aqui cantidad_rechazada deja de ser NULL.
    """
    cid = _parse_uuid(camion_id, "Camión")
    camion = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, sucursal_id, unidad_operativa_id, estatus
                FROM trasplante_camiones_lotes
                WHERE id = CAST(:cid AS uuid)
                FOR UPDATE
                """
            ),
            {"cid": cid},
        )
    ).first()
    if not camion:
        raise HTTPException(status_code=404, detail="Camión no encontrado.")

    assert_scope(
        actor,
        "trasplante.finalizar",
        empresa_id=camion.empresa_id,
        sucursal_id=camion.sucursal_id,
        unidad_operativa_id=camion.unidad_operativa_id,
        min_level=3,
    )
    if camion.estatus == "FINALIZED":
        raise HTTPException(status_code=409, detail="Recepción del camión ya fue finalizada (inmutable).")

    async def _exec() -> Dict[str, Any]:
        db_bins = (
            await db.execute(
                text(
                    """
                    SELECT id::text AS id, bin_code, unidad_planta, cantidad_recibida
                    FROM trasplante_bins
                    WHERE camion_lote_id = CAST(:cid AS uuid)
                    FOR UPDATE
                    """
                ),
                {"cid": cid},
            )
        ).all()
        if not db_bins:
            raise HTTPException(status_code=400, detail="No hay bins recibidos para finalizar este camión.")

        bin_map = {b.id: b for b in db_bins}
        provided_ids = {_parse_uuid(item.bin_id, "Bin") for item in data.bins}
        if provided_ids != set(bin_map.keys()):
            raise HTTPException(
                status_code=400,
                detail="Debe conciliar la totalidad exacta de los bins recibidos del camión.",
            )

        resumen_bins = []
        for item in data.bins:
            bid = _parse_uuid(item.bin_id, "Bin")
            b = bin_map[bid]
            if item.cantidad_aceptada + item.cantidad_rechazada != int(b.cantidad_recibida):
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"Descuadre en bin {b.bin_code}: accepted ({item.cantidad_aceptada}) + "
                        f"rejected ({item.cantidad_rechazada}) != received ({b.cantidad_recibida})."
                    ),
                )
            stock = await _get_bin_derived_stock(db, bid)
            if item.cantidad_aceptada < stock["consumido"]:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Bin {b.bin_code}: accepted ({item.cantidad_aceptada}) menor que ya consumido ({stock['consumido']})."
                    ),
                )
            await db.execute(
                text(
                    """
                    UPDATE trasplante_bins
                       SET cantidad_aceptada = :acc,
                           cantidad_rechazada = :rej,
                           motivo_rechazo = :mot
                     WHERE id = CAST(:bid AS uuid)
                    """
                ),
                {
                    "acc": item.cantidad_aceptada,
                    "rej": item.cantidad_rechazada,
                    "mot": item.motivo_rechazo,
                    "bid": bid,
                },
            )
            if item.cantidad_rechazada > 0:
                await db.execute(
                    text(
                        """
                        INSERT INTO trasplante_bins_ledger (
                            bin_id, camion_lote_id, empresa_id, unidad_operativa_id,
                            unidad_planta, tipo_evento, cantidad, actor_usuario_id
                        ) VALUES (
                            CAST(:bid AS uuid), CAST(:cid AS uuid), :emp, :uo,
                            :unit, 'BIN_REJECT_FINAL', :rej, CAST(:uid AS uuid)
                        )
                        """
                    ),
                    {
                        "bid": bid,
                        "cid": cid,
                        "emp": camion.empresa_id,
                        "uo": camion.unidad_operativa_id,
                        "unit": b.unidad_planta,
                        "rej": item.cantidad_rechazada,
                        "uid": actor.usuario_id,
                    },
                )
            resumen_bins.append(
                {
                    "bin_id": bid,
                    "bin_code": b.bin_code,
                    "received": int(b.cantidad_recibida),
                    "accepted": item.cantidad_aceptada,
                    "rejected": item.cantidad_rechazada,
                }
            )

        await db.execute(
            text(
                """
                UPDATE trasplante_camiones_lotes
                   SET estatus = 'FINALIZED',
                       verified = TRUE,
                       cajas_plasticas_devueltas = COALESCE(:cajas_dev, cajas_plasticas_devueltas),
                       finalizado_recibo_por_usuario_id = CAST(:uid AS uuid),
                       finalizado_recibo_en = NOW(),
                       notas_cierre = :notas
                 WHERE id = CAST(:cid AS uuid)
                """
            ),
            {
                "cajas_dev": data.cajas_plasticas_devueltas,
                "uid": actor.usuario_id,
                "notas": data.notas_cierre,
                "cid": cid,
            },
        )
        await registrar_auditoria(
            db,
            actor,
            modulo="trasplante_recepcion",
            accion="FINALIZE_RECEIPT",
            tipo_entidad="TRASPLANTE_CAMION",
            id_entidad=cid,
            empresa_id=camion.empresa_id,
            sucursal_id=camion.sucursal_id,
            unidad_operativa_id=camion.unidad_operativa_id,
            datos_despues={"bins": resumen_bins},
        )
        return {"camion_id": cid, "estatus": "FINALIZED", "verified": True, "bins": resumen_bins}

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type="FINALIZE_RECEIPT",
        payload={"camion_id": cid, **data.model_dump()},
        actor=actor,
        empresa_id=camion.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack


# ---------------------------------------------------------------------------
# 3. COORDINADOR MULTI-CAMION (SHARED-TRUCKS), EQUIPOS NORTE/SUR Y PRODUCCION
# ---------------------------------------------------------------------------
@router.post("/asignaciones", status_code=status.HTTP_201_CREATED)
async def crear_asignacion_trasplante(
    data: CrearAsignacionIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.operar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    if data.linea_fin < data.linea_inicio:
        raise HTTPException(status_code=400, detail="linea_fin debe ser >= linea_inicio.")

    cid = _parse_uuid(data.camion_lote_id, "Camión")
    bid = _parse_uuid(data.bin_id, "Bin")
    cont_id = (
        _parse_uuid(data.cross_batch_continuation_of, "Asignación origen")
        if data.cross_batch_continuation_of
        else None
    )

    camion = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, sucursal_id, unidad_operativa_id, estatus
                FROM trasplante_camiones_lotes
                WHERE id = CAST(:cid AS uuid)
                """
            ),
            {"cid": cid},
        )
    ).first()
    if not camion:
        raise HTTPException(status_code=404, detail="Camión no encontrado.")

    assert_scope(
        actor,
        "trasplante.operar",
        empresa_id=camion.empresa_id,
        sucursal_id=camion.sucursal_id,
        unidad_operativa_id=camion.unidad_operativa_id,
        min_level=1,
    )

    async def _exec() -> Dict[str, Any]:
        # Verificar que el bin pertenece al camion y (si es TRANSPLANT) tiene stock liberado disponible
        stock = await _get_bin_derived_stock(db, bid)
        if stock["camion_lote_id"] != cid:
            raise HTTPException(status_code=400, detail="El bin no pertenece al camión indicado.")
        if data.funcion_codigo == "TRANSPLANT" and stock["disponible"] <= 0:
            raise HTTPException(
                status_code=409,
                detail="BIN_SIN_STOCK_LIBERADO: Debe ejecutar BIN_RELEASE antes de asignar trasplante.",
            )

        # Validar continuacion entre camiones (crossBatchContinuationOf)
        if cont_id:
            src = (
                await db.execute(
                    text(
                        """
                        SELECT id::text AS id, estatus, lote_id, tunel_numero, equipo_lado,
                               linea_inicio, linea_fin, funcion_codigo
                        FROM trasplante_asignaciones
                        WHERE id = CAST(:sid AS uuid)
                        """
                    ),
                    {"sid": cont_id},
                )
            ).first()
            if not src:
                raise HTTPException(status_code=404, detail="Asignación origen no encontrada.")
            if src.estatus != "FINISHED":
                raise HTTPException(
                    status_code=409,
                    detail="CROSS_BATCH_SOURCE_NOT_FINISHED: La asignación origen debe estar FINISHED.",
                )
            if (
                src.lote_id != data.lote_id
                or src.tunel_numero != data.tunel_numero
                or src.equipo_lado != data.equipo_lado
            ):
                raise HTTPException(
                    status_code=400,
                    detail="La continuación debe corresponder al mismo lote, túnel y lado.",
                )
            # Debe ser un subrango dentro o inmediatamente contiguo pendiente y sin pisar lineas ya producidas del origen
            prod_max = (
                await db.execute(
                    text(
                        """
                        SELECT COALESCE(MAX(linea_fin), 0)
                        FROM trasplante_produccion_lineas
                        WHERE asignacion_id = CAST(:sid AS uuid)
                        """
                    ),
                    {"sid": cont_id},
                )
            ).scalar()
            if prod_max and data.linea_inicio <= int(prod_max):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"CROSS_BATCH_OVERLAP_COMPLETED: El origen ya completó hasta línea {prod_max}; "
                        f"la continuación debe iniciar después."
                    ),
                )

        # 1) Validar cero doble reserva simultanea de personas (sin revelar trabajo del otro lote!)
        participantes = sorted({_parse_uuid(p, "Persona") for p in data.participantes_persona_ids})
        for pid in participantes:
            await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"TR_PER:{pid}"})
            busy = (
                await db.execute(
                    text(
                        """
                        SELECT 1
                        FROM trasplante_asignacion_participantes ap
                        JOIN trasplante_asignaciones a ON a.id = ap.asignacion_id
                        WHERE ap.persona_id = CAST(:pid AS uuid)
                          AND ap.activo = TRUE
                          AND a.estatus IN ('ASSIGNED', 'RUNNING', 'PAUSED')
                        LIMIT 1
                        """
                    ),
                    {"pid": pid},
                )
            ).first()
            if busy:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "PERSON_ALREADY_ASSIGNED",
                        "persona_id": pid,
                        "message": "La persona ya cuenta con una asignación activa en otro frente.",
                    },
                )

        # 2) Validar cero solapamiento fisico de rango de lineas para TRANSPLANT
        if data.funcion_codigo == "TRANSPLANT":
            await _check_transplant_range_overlap(
                db,
                empresa_id=camion.empresa_id,
                lote_id=data.lote_id,
                tunel_numero=data.tunel_numero,
                equipo_lado=data.equipo_lado,
                linea_inicio=data.linea_inicio,
                linea_fin=data.linea_fin,
                continuation_source_id=cont_id,
            )

        asig = (
            await db.execute(
                text(
                    """
                    INSERT INTO trasplante_asignaciones (
                        empresa_id, sucursal_id, unidad_operativa_id, fecha,
                        camion_lote_id, bin_id, lote_id, tunel_numero, equipo_lado,
                        linea_inicio, linea_fin, funcion_codigo, estatus,
                        cross_batch_continuation_of, supervisor_usuario_id
                    ) VALUES (
                        :emp, :suc, :uo, :f,
                        CAST(:cid AS uuid), CAST(:bid AS uuid), :lote, :tun, :lado,
                        :lini, :lfin, :func, 'RUNNING',
                        CAST(:cont AS uuid), CAST(:sup AS uuid)
                    )
                    RETURNING id::text AS id, camion_lote_id::text AS camion_lote_id,
                              bin_id::text AS bin_id, lote_id, tunel_numero, equipo_lado,
                              linea_inicio, linea_fin, funcion_codigo, estatus,
                              cross_batch_continuation_of::text AS cross_batch_continuation_of
                    """
                ),
                {
                    "emp": camion.empresa_id,
                    "suc": camion.sucursal_id,
                    "uo": camion.unidad_operativa_id,
                    "f": data.fecha,
                    "cid": cid,
                    "bid": bid,
                    "lote": data.lote_id,
                    "tun": data.tunel_numero,
                    "lado": data.equipo_lado,
                    "lini": data.linea_inicio,
                    "lfin": data.linea_fin,
                    "func": data.funcion_codigo,
                    "cont": cont_id,
                    "sup": actor.usuario_id,
                },
            )
        ).first()

        for pid in participantes:
            await db.execute(
                text(
                    """
                    INSERT INTO trasplante_asignacion_participantes (asignacion_id, persona_id, activo)
                    VALUES (CAST(:aid AS uuid), CAST(:pid AS uuid), TRUE)
                    """
                ),
                {"aid": asig.id, "pid": pid},
            )

        await db.execute(
            text(
                """
                INSERT INTO trasplante_segmentos_tiempo (
                    asignacion_id, funcion_codigo, participantes_persona_ids, motivo_cambio
                ) VALUES (
                    CAST(:aid AS uuid), :func, CAST(:parts AS jsonb), 'INICIO_ASIGNACION'
                )
                """
            ),
            {"aid": asig.id, "func": data.funcion_codigo, "parts": json.dumps(participantes)},
        )

        return {**dict(asig._mapping), "participantes_persona_ids": participantes}

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type="CREATE_ASSIGNMENT",
        payload=data.model_dump(),
        actor=actor,
        empresa_id=camion.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack


@router.patch("/asignaciones/{asig_id}/estado")
async def cambiar_estado_asignacion(
    asig_id: str,
    data: CambiarEstadoAsignacionIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.operar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    aid = _parse_uuid(asig_id, "Asignación")
    asig = (
        await db.execute(
            text(
                """
                SELECT id::text AS id, empresa_id, sucursal_id, unidad_operativa_id,
                       lote_id, tunel_numero, equipo_lado, linea_inicio, linea_fin,
                       funcion_codigo, estatus
                FROM trasplante_asignaciones
                WHERE id = CAST(:aid AS uuid)
                FOR UPDATE
                """
            ),
            {"aid": aid},
        )
    ).first()
    if not asig:
        raise HTTPException(status_code=404, detail="Asignación no encontrada.")

    assert_scope(
        actor,
        "trasplante.operar",
        empresa_id=asig.empresa_id,
        sucursal_id=asig.sucursal_id,
        unidad_operativa_id=asig.unidad_operativa_id,
        min_level=1,
    )

    if asig.estatus in ("FINISHED", "CANCELLED"):
        raise HTTPException(status_code=409, detail=f"La asignación ya está en estado terminal '{asig.estatus}'.")

    async def _exec() -> Dict[str, Any]:
        parts = [
            r.persona_id
            for r in (
                await db.execute(
                    text(
                        """
                        SELECT persona_id::text AS persona_id
                        FROM trasplante_asignacion_participantes
                        WHERE asignacion_id = CAST(:aid AS uuid) AND activo = TRUE
                        ORDER BY persona_id
                        """
                    ),
                    {"aid": aid},
                )
            ).all()
        ]

        new_status = asig.estatus
        new_func = asig.funcion_codigo

        if data.accion == "PAUSE":
            new_status = "PAUSED"
            await db.execute(
                text(
                    """
                    UPDATE trasplante_segmentos_tiempo
                       SET fin_en = NOW(), motivo_cambio = COALESCE(:mot, 'PAUSA')
                     WHERE asignacion_id = CAST(:aid AS uuid) AND fin_en IS NULL
                    """
                ),
                {"aid": aid, "mot": data.motivo_cambio},
            )
        elif data.accion in ("START", "RESUME"):
            new_status = "RUNNING"
            await db.execute(
                text(
                    """
                    INSERT INTO trasplante_segmentos_tiempo (
                        asignacion_id, funcion_codigo, participantes_persona_ids, motivo_cambio
                    ) VALUES (
                        CAST(:aid AS uuid), :func, CAST(:parts AS jsonb), COALESCE(:mot, 'REANUDACION')
                    )
                    """
                ),
                {"aid": aid, "func": asig.funcion_codigo, "parts": json.dumps(parts), "mot": data.motivo_cambio},
            )
        elif data.accion == "CHANGE_FUNCTION":
            if not data.nueva_funcion_codigo:
                raise HTTPException(status_code=400, detail="nueva_funcion_codigo requerida para CHANGE_FUNCTION.")
            new_func = data.nueva_funcion_codigo
            # REGLA CRITICA SHARED-TRUCKS: una labor auxiliar (CLIPS/BARRER) no puede apropiarse
            # de un rango ocupado por TRANSPLANT via CHANGE_FUNCTION!
            if new_func == "TRANSPLANT" and asig.funcion_codigo != "TRANSPLANT":
                await _check_transplant_range_overlap(
                    db,
                    empresa_id=asig.empresa_id,
                    lote_id=asig.lote_id,
                    tunel_numero=asig.tunel_numero,
                    equipo_lado=asig.equipo_lado,
                    linea_inicio=asig.linea_inicio,
                    linea_fin=asig.linea_fin,
                    exclude_asig_id=aid,
                )
            await db.execute(
                text(
                    """
                    UPDATE trasplante_segmentos_tiempo
                       SET fin_en = NOW(), motivo_cambio = COALESCE(:mot, 'CAMBIO_FUNCION')
                     WHERE asignacion_id = CAST(:aid AS uuid) AND fin_en IS NULL
                    """
                ),
                {"aid": aid, "mot": data.motivo_cambio},
            )
            if asig.estatus == "RUNNING":
                await db.execute(
                    text(
                        """
                        INSERT INTO trasplante_segmentos_tiempo (
                            asignacion_id, funcion_codigo, participantes_persona_ids, motivo_cambio
                        ) VALUES (
                            CAST(:aid AS uuid), :func, CAST(:parts AS jsonb), COALESCE(:mot, 'CAMBIO_FUNCION')
                        )
                        """
                    ),
                    {"aid": aid, "func": new_func, "parts": json.dumps(parts), "mot": data.motivo_cambio},
                )
        elif data.accion in ("FINISH", "CANCEL"):
            new_status = "FINISHED" if data.accion == "FINISH" else "CANCELLED"
            await db.execute(
                text(
                    """
                    UPDATE trasplante_segmentos_tiempo
                       SET fin_en = NOW(), motivo_cambio = COALESCE(:mot, :acc)
                     WHERE asignacion_id = CAST(:aid AS uuid) AND fin_en IS NULL
                    """
                ),
                {"aid": aid, "mot": data.motivo_cambio, "acc": data.accion},
            )

        await db.execute(
            text(
                """
                UPDATE trasplante_asignaciones
                   SET estatus = :est, funcion_codigo = :func, actualizado_en = NOW()
                 WHERE id = CAST(:aid AS uuid)
                """
            ),
            {"est": new_status, "func": new_func, "aid": aid},
        )
        return {"asignacion_id": aid, "estatus": new_status, "funcion_codigo": new_func}

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type=f"ASSIGNMENT_{data.accion}",
        payload={"asig_id": aid, **data.model_dump()},
        actor=actor,
        empresa_id=asig.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack


@router.post("/asignaciones/{asig_id}/produccion", status_code=status.HTTP_201_CREATED)
async def registrar_produccion_trasplante(
    asig_id: str,
    data: RegistrarProduccionIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.operar", min_level=1)),
    db: AsyncSession = Depends(get_db),
):
    """
    Registra plantas trasplantadas consumiendo del ledger derivado del bin exacto
    con unidad exacta, sin multiplicar la produccion compartida por el numero de integrantes.
    """
    aid = _parse_uuid(asig_id, "Asignación")
    asig = (
        await db.execute(
            text(
                """
                SELECT a.id::text AS id, a.empresa_id, a.sucursal_id, a.unidad_operativa_id,
                       a.camion_lote_id::text AS camion_lote_id, a.bin_id::text AS bin_id,
                       a.lote_id, a.tunel_numero, a.equipo_lado, a.linea_inicio, a.linea_fin,
                       a.funcion_codigo, a.estatus
                FROM trasplante_asignaciones a
                WHERE a.id = CAST(:aid AS uuid)
                """
            ),
            {"aid": aid},
        )
    ).first()
    if not asig:
        raise HTTPException(status_code=404, detail="Asignación no encontrada.")

    assert_scope(
        actor,
        "trasplante.operar",
        empresa_id=asig.empresa_id,
        sucursal_id=asig.sucursal_id,
        unidad_operativa_id=asig.unidad_operativa_id,
        min_level=1,
    )
    if asig.funcion_codigo != "TRANSPLANT":
        raise HTTPException(status_code=400, detail="Solo asignaciones TRANSPLANT consumen stock de planta.")
    if asig.estatus not in ("RUNNING", "PAUSED"):
        raise HTTPException(status_code=409, detail="La asignación debe estar activa para registrar producción.")
    if data.linea_inicio < asig.linea_inicio or data.linea_fin > asig.linea_fin or data.linea_fin < data.linea_inicio:
        raise HTTPException(status_code=400, detail="El subrango de líneas excede el asignado.")

    async def _exec() -> Dict[str, Any]:
        # Bloquear el bin para lectura consistente del ledger derivado
        await db.execute(
            text("SELECT id FROM trasplante_bins WHERE id = CAST(:bid AS uuid) FOR UPDATE"),
            {"bid": asig.bin_id},
        )
        stock = await _get_bin_derived_stock(db, asig.bin_id)
        unit = data.unidad_planta.strip().upper()
        if unit != stock["unidad_planta"]:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"UNIT_MISMATCH: El bin tiene unidad '{stock['unidad_planta']}', "
                    f"no se permite conversión implícita desde '{unit}'."
                ),
            )
        if data.cantidad_trasplantada > stock["disponible"]:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"INSUFFICIENT_BIN_STOCK: Disponible {stock['disponible']} < "
                    f"solicitado {data.cantidad_trasplantada}."
                ),
            )

        p_count = (
            await db.execute(
                text(
                    """
                    SELECT COUNT(*) FROM trasplante_asignacion_participantes
                    WHERE asignacion_id = CAST(:aid AS uuid) AND activo = TRUE
                    """
                ),
                {"aid": aid},
            )
        ).scalar()

        prod = (
            await db.execute(
                text(
                    """
                    INSERT INTO trasplante_produccion_lineas (
                        asignacion_id, camion_lote_id, bin_id, lote_id, tunel_numero,
                        equipo_lado, linea_inicio, linea_fin, unidad_planta,
                        cantidad_trasplantada, participantes_count, registrado_por_usuario_id
                    ) VALUES (
                        CAST(:aid AS uuid), CAST(:cid AS uuid), CAST(:bid AS uuid), :lote, :tun,
                        :lado, :lini, :lfin, :unit,
                        :cant, :pcnt, CAST(:uid AS uuid)
                    )
                    RETURNING id::text AS id, cantidad_trasplantada, participantes_count, unidad_planta
                    """
                ),
                {
                    "aid": aid,
                    "cid": asig.camion_lote_id,
                    "bid": asig.bin_id,
                    "lote": asig.lote_id,
                    "tun": asig.tunel_numero,
                    "lado": asig.equipo_lado,
                    "lini": data.linea_inicio,
                    "lfin": data.linea_fin,
                    "unit": unit,
                    "cant": data.cantidad_trasplantada,
                    "pcnt": int(p_count),
                    "uid": actor.usuario_id,
                },
            )
        ).first()

        await db.execute(
            text(
                """
                INSERT INTO trasplante_bins_ledger (
                    bin_id, camion_lote_id, empresa_id, unidad_operativa_id,
                    unidad_planta, tipo_evento, cantidad, referencia_id, actor_usuario_id
                ) VALUES (
                    CAST(:bid AS uuid), CAST(:cid AS uuid), :emp, :uo,
                    :unit, 'TRANSPLANT_CONSUME', :cant, :ref, CAST(:uid AS uuid)
                )
                """
            ),
            {
                "bid": asig.bin_id,
                "cid": asig.camion_lote_id,
                "emp": asig.empresa_id,
                "uo": asig.unidad_operativa_id,
                "unit": unit,
                "cant": data.cantidad_trasplantada,
                "ref": prod.id,
                "uid": actor.usuario_id,
            },
        )
        new_stock = await _get_bin_derived_stock(db, asig.bin_id)
        return {
            **dict(prod._mapping),
            "stock_restante_bin": new_stock["disponible"],
        }

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type="REGISTER_TRANSPLANT_PRODUCTION",
        payload={"asig_id": aid, **data.model_dump()},
        actor=actor,
        empresa_id=asig.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack


# ---------------------------------------------------------------------------
# 4. CIERRE INDIVIDUAL PERSONA-DIA (CLOSE_PERSON_DAY)
# ---------------------------------------------------------------------------
@router.post("/cierre-persona-dia/review-token")
async def generar_review_token_persona_dia(
    data: SolicitarReviewTokenIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.cerrar_persona_dia", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    pid = _parse_uuid(data.persona_id, "Persona")
    cid = _parse_uuid(data.camion_lote_id, "Camión")
    camion = (
        await db.execute(
            text(
                "SELECT empresa_id, sucursal_id, unidad_operativa_id FROM trasplante_camiones_lotes WHERE id = CAST(:cid AS uuid)"
            ),
            {"cid": cid},
        )
    ).first()
    if not camion:
        raise HTTPException(status_code=404, detail="Camión no encontrado.")

    assert_scope(
        actor,
        "trasplante.cerrar_persona_dia",
        empresa_id=camion.empresa_id,
        sucursal_id=camion.sucursal_id,
        unidad_operativa_id=camion.unidad_operativa_id,
        min_level=2,
    )

    snap = await _compute_person_day_snapshot(db, pid, cid, data.fecha)
    expira = datetime.now(timezone.utc) + timedelta(minutes=15)

    tok = (
        await db.execute(
            text(
                """
                INSERT INTO trasplante_review_tokens (
                    actor_usuario_id, persona_id, camion_lote_id, fecha, snapshot_sha256, expira_en
                ) VALUES (
                    CAST(:uid AS uuid), CAST(:pid AS uuid), CAST(:cid AS uuid), :f, :sha, :exp
                )
                RETURNING token::text AS token, snapshot_sha256, expira_en
                """
            ),
            {
                "uid": actor.usuario_id,
                "pid": pid,
                "cid": cid,
                "f": data.fecha,
                "sha": snap["snapshot_sha256"],
                "exp": expira,
            },
        )
    ).first()
    await db.commit()
    return {
        "review_token": tok.token,
        "snapshot_sha256": tok.snapshot_sha256,
        "expira_en": tok.expira_en,
        "resumen": {
            "total_asignaciones": len(snap["asignaciones"]),
            "total_minutos": snap["total_minutos"],
            "segmentos_abiertos": snap["segmentos_abiertos"],
            "total_plantas_equipo": snap["total_plantas"],
        },
    }


@router.post("/cierre-persona-dia/close")
async def close_person_day(
    data: ClosePersonDayIn,
    actor: AuthenticatedActor = Depends(require_permission("trasplante.cerrar_persona_dia", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    """
    CLOSE_PERSON_DAY:
    - Exige review_token fresco atado al actor y al snapshot actual (STALE_REVIEW_TOKEN si hubo cambios).
    - Bloquea si hay asignaciones abiertas o temporizadores corriendo (OPEN_ASSIGNMENTS_EXIST).
    - Bloquea con PERSON_DAY_SCOPE_INCOMPLETE si la persona tiene asignaciones ese dia fuera del alcance del supervisor.
    - Certifica exclusivamente (persona, camion_lote, fecha) con es_pagable = FALSE.
    """
    pid = _parse_uuid(data.persona_id, "Persona")
    cid = _parse_uuid(data.camion_lote_id, "Camión")
    tid = _parse_uuid(data.review_token, "review_token")

    camion = (
        await db.execute(
            text(
                "SELECT empresa_id, sucursal_id, unidad_operativa_id FROM trasplante_camiones_lotes WHERE id = CAST(:cid AS uuid)"
            ),
            {"cid": cid},
        )
    ).first()
    if not camion:
        raise HTTPException(status_code=404, detail="Camión no encontrado.")

    assert_scope(
        actor,
        "trasplante.cerrar_persona_dia",
        empresa_id=camion.empresa_id,
        sucursal_id=camion.sucursal_id,
        unidad_operativa_id=camion.unidad_operativa_id,
        min_level=2,
    )

    async def _exec() -> Dict[str, Any]:
        tok = (
            await db.execute(
                text(
                    """
                    SELECT token::text AS token, actor_usuario_id::text AS actor_usuario_id,
                           persona_id::text AS persona_id, camion_lote_id::text AS camion_lote_id,
                           fecha, snapshot_sha256, usado, expira_en
                    FROM trasplante_review_tokens
                    WHERE token = CAST(:tid AS uuid)
                    FOR UPDATE
                    """
                ),
                {"tid": tid},
            )
        ).first()
        if not tok:
            raise HTTPException(status_code=404, detail="review_token no encontrado.")
        if (
            tok.actor_usuario_id != actor.usuario_id
            or tok.persona_id != pid
            or tok.camion_lote_id != cid
            or tok.fecha != data.fecha
        ):
            raise HTTPException(status_code=403, detail="review_token no corresponde a este actor/lote/persona.")
        if tok.usado or tok.expira_en < datetime.now(timezone.utc):
            raise HTTPException(status_code=409, detail={"code": "STALE_REVIEW_TOKEN", "message": "Token usado o vencido."})

        # Verificar alcance completo del dia para la persona (si trabajo en otra unidad fuera del alcance del supervisor)
        other_units = (
            await db.execute(
                text(
                    """
                    SELECT DISTINCT a.empresa_id, a.sucursal_id, a.unidad_operativa_id
                    FROM trasplante_asignaciones a
                    JOIN trasplante_asignacion_participantes ap ON ap.asignacion_id = a.id
                    WHERE ap.persona_id = CAST(:pid AS uuid)
                      AND a.fecha = :f
                      AND a.estatus <> 'CANCELLED'
                    """
                ),
                {"pid": pid, "f": data.fecha},
            )
        ).all()
        for ou in other_units:
            if not actor.has_scoped_permission(
                "trasplante.cerrar_persona_dia",
                empresa_id=ou.empresa_id,
                sucursal_id=ou.sucursal_id,
                unidad_operativa_id=ou.unidad_operativa_id,
                min_level=2,
            ):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "PERSON_DAY_SCOPE_INCOMPLETE",
                        "message": "La persona registra actividad fuera del alcance del supervisor; derivar a Gerencia.",
                    },
                )

        snap = await _compute_person_day_snapshot(db, pid, cid, data.fecha)
        if snap["snapshot_sha256"] != tok.snapshot_sha256:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "STALE_REVIEW_TOKEN",
                    "message": "El estado de las asignaciones cambió después de la revisión; genere un nuevo review_token.",
                },
            )

        open_asigs = [a for a in snap["asignaciones"] if a["estatus"] in ("ASSIGNED", "RUNNING", "PAUSED")]
        if open_asigs or snap["segmentos_abiertos"] > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "OPEN_ASSIGNMENTS_EXIST",
                    "message": "No se puede cerrar persona-día con asignaciones o temporizadores abiertos.",
                },
            )

        try:
            cierre = (
                await db.execute(
                    text(
                        """
                        INSERT INTO trasplante_cierres_persona_dia (
                            empresa_id, unidad_operativa_id, persona_id, camion_lote_id, fecha,
                            review_token_id, total_asignaciones_cerradas, total_minutos_participacion,
                            total_plantas_equipo, es_pagable, cerrado_por_usuario_id
                        ) VALUES (
                            :emp, :uo, CAST(:pid AS uuid), CAST(:cid AS uuid), :f,
                            CAST(:tid AS uuid), :tot_a, :tot_m,
                            :tot_p, FALSE, CAST(:uid AS uuid)
                        )
                        RETURNING id::text AS id, persona_id::text AS persona_id,
                                  camion_lote_id::text AS camion_lote_id, fecha,
                                  total_asignaciones_cerradas, total_minutos_participacion,
                                  total_plantas_equipo, es_pagable, cerrado_en
                        """
                    ),
                    {
                        "emp": camion.empresa_id,
                        "uo": camion.unidad_operativa_id,
                        "pid": pid,
                        "cid": cid,
                        "f": data.fecha,
                        "tid": tid,
                        "tot_a": len([a for a in snap["asignaciones"] if a["estatus"] == "FINISHED"]),
                        "tot_m": snap["total_minutos"],
                        "tot_p": snap["total_plantas"],
                        "uid": actor.usuario_id,
                    },
                )
            ).first()
        except IntegrityError as exc:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Persona-día ya fue cerrada para este camión y fecha.") from exc

        await db.execute(
            text("UPDATE trasplante_review_tokens SET usado = TRUE WHERE token = CAST(:tid AS uuid)"),
            {"tid": tid},
        )
        await registrar_auditoria(
            db,
            actor,
            modulo="trasplante_recepcion",
            accion="CLOSE_PERSON_DAY",
            tipo_entidad="TRASPLANTE_CIERRE_PERSONA_DIA",
            id_entidad=cierre.id,
            empresa_id=camion.empresa_id,
            sucursal_id=camion.sucursal_id,
            unidad_operativa_id=camion.unidad_operativa_id,
            datos_despues=dict(cierre._mapping),
        )
        return dict(cierre._mapping)

    _, ack = await run_idempotent_command(
        db,
        client_command_id=data.client_command_id,
        command_type="CLOSE_PERSON_DAY",
        payload=data.model_dump(),
        actor=actor,
        empresa_id=camion.empresa_id,
        executor=_exec,
    )
    await db.commit()
    return ack
