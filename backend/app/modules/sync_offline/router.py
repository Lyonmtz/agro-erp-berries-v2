from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.database import get_db
from app.core.security import AuthenticatedActor, assert_scope, require_permission
from app.modules.sync_offline.service import parse_command_id

router = APIRouter(prefix="/api/v1/sync", tags=["Offline Sync & Fencing"])


class FenceCommandIn(BaseModel):
    client_command_id: str
    empresa_id: int
    sucursal_id: int | None = None
    unidad_operativa_id: int | None = None
    motivo: str = Field(..., min_length=4)


@router.post("/fences", status_code=status.HTTP_201_CREATED)
async def crear_command_fence(
    data: FenceCommandIn,
    actor: AuthenticatedActor = Depends(require_permission("sync.fencing", min_level=2)),
    db: AsyncSession = Depends(get_db),
):
    """
    DURABLE_COMMAND_FENCE: cerca de forma durable un client_command_id pendiente
    dentro de la misma transaccion bloqueada.
    - Si ya fue aplicado (existe en sync_idempotency_log) -> 409 ALREADY_COMMITTED.
    - Si no existe -> crea el fence; cualquier entrega tardia desde tablet offline
      sera rechazada con COMMAND_FENCED_NOT_APPLIED.
    """
    assert_scope(
        actor,
        "sync.fencing",
        empresa_id=data.empresa_id,
        sucursal_id=data.sucursal_id,
        unidad_operativa_id=data.unidad_operativa_id,
        min_level=2,
    )
    cmd_uuid = parse_command_id(data.client_command_id)

    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:cid))"), {"cid": cmd_uuid})

    committed = (
        await db.execute(
            text(
                """
                SELECT committed_ack_json
                FROM sync_idempotency_log
                WHERE client_command_id = CAST(:cid AS uuid)
                """
            ),
            {"cid": cmd_uuid},
        )
    ).first()
    if committed:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "COMMAND_ALREADY_COMMITTED",
                "client_command_id": cmd_uuid,
                "committed_ack": committed.committed_ack_json,
            },
        )

    await db.execute(
        text(
            """
            INSERT INTO sync_command_fences (
                client_command_id, fenced_by_usuario_id, empresa_id, motivo
            ) VALUES (
                CAST(:cid AS uuid), CAST(:uid AS uuid), :emp, :mot
            )
            ON CONFLICT (client_command_id) DO NOTHING
            """
        ),
        {
            "cid": cmd_uuid,
            "uid": actor.usuario_id,
            "emp": data.empresa_id,
            "mot": data.motivo.strip(),
        },
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="sync_offline",
        accion="DURABLE_COMMAND_FENCE",
        tipo_entidad="SYNC_COMMAND",
        id_entidad=cmd_uuid,
        empresa_id=data.empresa_id,
        datos_despues={"motivo": data.motivo.strip()},
    )
    await db.commit()
    return {
        "client_command_id": cmd_uuid,
        "status": "NOT_APPLIED_VERIFIED",
        "fence_active": True,
        "motivo": data.motivo.strip(),
    }


@router.get("/commands/{client_command_id}")
async def consultar_estado_comando(
    client_command_id: str,
    actor: AuthenticatedActor = Depends(require_permission("campo.elegibilidad.leer")),
    db: AsyncSession = Depends(get_db),
):
    """
    Distingue explicitamente:
      - COMMITTED (devuelve committed_ack original para recuperar ACK perdido)
      - FENCED / NOT_APPLIED_VERIFIED (cercado de forma durable)
      - ABSENCE_OBSERVED (no encontrado en servidor; no se asume cancelado hasta cercarlo)
    """
    cmd_uuid = parse_command_id(client_command_id)

    committed = (
        await db.execute(
            text(
                """
                SELECT command_type, committed_ack_json, creado_en
                FROM sync_idempotency_log
                WHERE client_command_id = CAST(:cid AS uuid)
                """
            ),
            {"cid": cmd_uuid},
        )
    ).first()
    if committed:
        return {
            "client_command_id": cmd_uuid,
            "status": "COMMITTED",
            "command_type": committed.command_type,
            "committed_ack": committed.committed_ack_json,
            "committed_at": committed.creado_en,
        }

    fence = (
        await db.execute(
            text(
                """
                SELECT motivo, fenced_at
                FROM sync_command_fences
                WHERE client_command_id = CAST(:cid AS uuid)
                """
            ),
            {"cid": cmd_uuid},
        )
    ).first()
    if fence:
        return {
            "client_command_id": cmd_uuid,
            "status": "NOT_APPLIED_VERIFIED",
            "code": "COMMAND_FENCED_NOT_APPLIED",
            "motivo": fence.motivo,
            "fenced_at": fence.fenced_at,
        }

    return {
        "client_command_id": cmd_uuid,
        "status": "ABSENCE_OBSERVED",
        "message": "El comando no figura en el servidor; puede seguir en tránsito offline. Use /fences para anularlo de forma durable.",
    }
