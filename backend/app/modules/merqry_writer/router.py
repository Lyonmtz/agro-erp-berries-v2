"""Router RBAC de merqry_writer (APAGADO por defecto via MERQRY_WRITE_ENABLED=false)."""

import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.security import AuthenticatedActor, assert_scope, require_permission
from app.modules.merqry_writer.firewall import (
    ALLOWED_CIRCUIT,
    BLACKLISTED_MERQRY_MOVS_LOWER,
    EMPRESA_CLAVE_TO_MERQRY,
    FROZEN_READONLY_SCHEMAS,
    WHITELISTED_MOVS_BY_MODULE,
    CircuitFirewallError,
    MerqryPrevalidationError,
    MerqryWriteGateError,
    enforce_circuit_and_mov_firewall,
    prevalidate_payload,
)
from app.modules.merqry_writer.service import (
    assert_write_gates_open,
    log_writer_audit,
    stage_outbox_command,
)

router = APIRouter(
    prefix="/api/v1/merqry-writer",
    tags=["Merqry Controlled Writer (Apagado por Defecto)"],
)


class PrevalidateMerqryIn(BaseModel):
    circuito_pago: str = Field(..., min_length=2, max_length=40)
    modulo: str = Field(..., min_length=2, max_length=10)
    merqry_mov: str = Field(..., min_length=2, max_length=40)
    payload: Dict[str, Any]


class StageOutboxIn(BaseModel):
    idempotency_key: str = Field(..., description="UUID idempotente del comando")
    empresa_id: int
    circuito_pago: str = Field(..., min_length=2, max_length=40)
    modulo: str = Field(..., min_length=2, max_length=10)
    merqry_mov: str = Field(..., min_length=2, max_length=40)
    modo_objetivo: str = Field("STAGING_DRAFT_ONLY", pattern="^(STAGING_DRAFT_ONLY|CONTROLLED_APPLY)$")
    origen_tabla: Optional[str] = Field(None, max_length=60)
    origen_registro_id: Optional[str] = Field(None, max_length=80)
    payload: Dict[str, Any]


def _parse_uuid_or_422(raw: str, field_name: str) -> str:
    try:
        return str(uuid.UUID(raw))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": "INVALID_UUID", "message": f"{field_name} debe ser un UUID valido."},
        ) from exc


@router.get("/status")
async def estado_merqry_writer(
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=2)),
):
    return {
        "merqry_write_enabled": settings.merqry_write_enabled,
        "merqry_write_mode": settings.merqry_write_mode if settings.merqry_write_enabled else "DISABLED",
        "merqry_readonly_mirror_mode": settings.merqry_readonly_mode,
        "allowed_modules_enabled": sorted(settings.merqry_write_allowed_modules_set),
        "allowed_target_schema": settings.merqry_write_allowed_schema or None,
        "frozen_readonly_schemas": sorted(FROZEN_READONLY_SCHEMAS),
        "allowed_circuit": ALLOWED_CIRCUIT,
        "company_mapping_by_clave": EMPRESA_CLAVE_TO_MERQRY,
        "blacklisted_movs": sorted(BLACKLISTED_MERQRY_MOVS_LOWER),
        "whitelisted_movs_by_module": {k: sorted(v) for k, v in WHITELISTED_MOVS_BY_MODULE.items()},
    }


@router.post("/prevalidate")
async def prevalidar_comando_merqry(
    data: PrevalidateMerqryIn,
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=3)),
):
    """Dry-run puro en memoria (no escribe en PostgreSQL ni en MySQL)."""
    try:
        circ_ok, mod_ok, mov_ok = enforce_circuit_and_mov_firewall(
            circuito_pago=data.circuito_pago,
            modulo=data.modulo,
            merqry_mov=data.merqry_mov,
        )
        resumen = prevalidate_payload(mod_ok, mov_ok, data.payload)
    except CircuitFirewallError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except MerqryPrevalidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.merqry_code, "message": exc.message, "detalles": exc.detalles},
        ) from exc

    return {
        "prevalidacion_ok": True,
        "circuito_pago": circ_ok,
        "modulo": mod_ok,
        "merqry_mov": mov_ok,
        "merqry_write_enabled": settings.merqry_write_enabled,
        "resumen": resumen,
    }


@router.post("/outbox/stage", status_code=status.HTTP_201_CREATED)
async def encolar_outbox_merqry(
    data: StageOutboxIn,
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    """
    Pre-valida y persiste un comando en el outbox de PostgreSQL.
    NO abre conexion ni escribe hacia MySQL/Merqry.
    """
    assert_scope(actor, "merqry.leer_conciliar", empresa_id=data.empresa_id, min_level=3)
    idem_uuid = _parse_uuid_or_422(data.idempotency_key, "idempotency_key")

    try:
        item, replay = await stage_outbox_command(
            db,
            actor=actor,
            idempotency_key=idem_uuid,
            empresa_id=data.empresa_id,
            circuito_pago=data.circuito_pago,
            modulo=data.modulo,
            merqry_mov=data.merqry_mov,
            modo_objetivo=data.modo_objetivo,
            payload=data.payload,
            origen_tabla=data.origen_tabla,
            origen_registro_id=data.origen_registro_id,
        )
    except CircuitFirewallError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except MerqryPrevalidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.merqry_code, "message": exc.message, "detalles": exc.detalles},
        ) from exc
    except ValueError as exc:
        if str(exc) == "IDEMPOTENCY_CONFLICT":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "message": "El idempotency_key ya existe en merqry_write_outbox con un payload distinto.",
                },
            ) from exc
        raise

    return {
        "outbox": item,
        "idempotent_replay": replay,
        "dispatched_to_merqry": False,
        "merqry_write_enabled": settings.merqry_write_enabled,
    }


@router.get("/outbox")
async def listar_outbox_merqry(
    empresa_id: Optional[int] = Query(None),
    modulo: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    if empresa_id is not None:
        assert_scope(actor, "merqry.leer_conciliar", empresa_id=empresa_id, min_level=2)

    clauses = ["1=1"]
    params: Dict[str, Any] = {"lim": limit}
    if empresa_id is not None:
        clauses.append("empresa_id = :eid")
        params["eid"] = empresa_id
    if modulo:
        clauses.append("modulo = :mod")
        params["mod"] = modulo.strip().upper()
    if estado:
        clauses.append("estado = :est")
        params["est"] = estado.strip().upper()

    rows = [
        dict(r._mapping)
        for r in await db.execute(
            text(
                f"""
                SELECT
                    id::text, idempotency_key::text, empresa_id, empresa_clave,
                    merqry_empresa, merqry_sucursal, circuito_pago, modulo,
                    merqry_mov, modo_objetivo, estatus_inicial_merqry,
                    merqry_ref_tag, estado, prevalidacion_ok, intentos,
                    merqry_id_generado, merqry_folio_generado, vg_ok, vg_ok_mensaje,
                    creado_en::text, actualizado_en::text
                FROM merqry_write_outbox
                WHERE {' AND '.join(clauses)}
                ORDER BY creado_en DESC
                LIMIT :lim
                """
            ),
            params,
        )
    ]
    return {"items": rows, "count": len(rows), "merqry_write_enabled": settings.merqry_write_enabled}


@router.post("/outbox/{outbox_id}/dispatch")
async def despachar_outbox_merqry(
    outbox_id: str,
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=4)),
    db: AsyncSession = Depends(get_db),
):
    """
    Punto unico de despacho hacia clon/laboratorio MySQL.
    FAIL-CLOSED por defecto: mientras MERQRY_WRITE_ENABLED=false siempre retorna 503
    y audita el intento bloqueado sin abrir ninguna conexion MySQL.
    """
    oid = _parse_uuid_or_422(outbox_id, "outbox_id")
    row = (
        await db.execute(
            text(
                """
                SELECT id::text, empresa_id, circuito_pago, modulo, merqry_mov, estado
                FROM merqry_write_outbox
                WHERE id = CAST(:oid AS UUID)
                """
            ),
            {"oid": oid},
        )
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Registro de outbox no encontrado.")

    assert_scope(actor, "merqry.leer_conciliar", empresa_id=row["empresa_id"], min_level=4)

    try:
        enforce_circuit_and_mov_firewall(row["circuito_pago"], row["modulo"], row["merqry_mov"])
        gate_cfg = assert_write_gates_open(row["modulo"])
    except CircuitFirewallError as exc:
        await log_writer_audit(
            db,
            outbox_id=oid,
            evento=exc.code,
            severidad="BLOCKED",
            actor_usuario_id=actor.usuario_id,
            circuito_intentado=row["circuito_pago"],
            modulo=row["modulo"],
            merqry_mov=row["merqry_mov"],
            detalle={"message": exc.message},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    except MerqryWriteGateError as exc:
        await log_writer_audit(
            db,
            outbox_id=oid,
            evento=exc.code,
            severidad="BLOCKED",
            actor_usuario_id=actor.usuario_id,
            circuito_intentado=row["circuito_pago"],
            modulo=row["modulo"],
            merqry_mov=row["merqry_mov"],
            detalle={"message": exc.message},
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"code": exc.code, "message": exc.message},
        ) from exc

    # Incluso si se habilitaran los 5 candados en un futuro laboratorio, el ejecutor
    # MySQL real requiere fase explicita de conexion al clon aislado mq_bio_organicos_write_lab.
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={
            "code": "LAB_EXECUTOR_NOT_ATTACHED",
            "message": "Los 5 candados pasaron, pero el driver de ejecucion MySQL solo se habilitara en la fase de laboratorio clonado.",
            "gate_cfg": gate_cfg,
        },
    )


@router.post("/outbox/{outbox_id}/cancel")
async def cancelar_outbox_pendiente(
    outbox_id: str,
    actor: AuthenticatedActor = Depends(require_permission("merqry.leer_conciliar", min_level=3)),
    db: AsyncSession = Depends(get_db),
):
    oid = _parse_uuid_or_422(outbox_id, "outbox_id")
    res = await db.execute(
        text(
            """
            UPDATE merqry_write_outbox
               SET estado = 'CANCELLED', actualizado_en = NOW()
             WHERE id = CAST(:oid AS UUID)
               AND estado IN ('PENDING', 'PREVALIDATED', 'FAILED_RETRYABLE')
            RETURNING id::text, empresa_id, modulo, merqry_mov, estado
            """
        ),
        {"oid": oid},
    )
    updated = res.mappings().first()
    if not updated:
        raise HTTPException(
            status_code=404,
            detail="Registro de outbox no encontrado o ya no esta en estado cancelable.",
        )
    assert_scope(actor, "merqry.leer_conciliar", empresa_id=updated["empresa_id"], min_level=3)
    await log_writer_audit(
        db,
        outbox_id=oid,
        evento="OUTBOX_CANCELLED",
        severidad="INFO",
        actor_usuario_id=actor.usuario_id,
        modulo=updated["modulo"],
        merqry_mov=updated["merqry_mov"],
        detalle={"nuevo_estado": "CANCELLED"},
    )
    await db.commit()
    return dict(updated)
