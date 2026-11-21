import hashlib
import json
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple
import uuid

from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedActor


def canonical_payload_hash(command_type: str, payload: Dict[str, Any]) -> str:
    """Hash SHA-256 canonico del payload (excluyendo client_command_id)."""
    clean = {k: v for k, v in payload.items() if k != "client_command_id"}
    raw = json.dumps(
        {"command_type": command_type, "payload": clean},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def parse_command_id(raw_id: Optional[str]) -> Optional[str]:
    if not raw_id:
        return None
    try:
        return str(uuid.UUID(raw_id))
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="client_command_id debe ser un UUID válido.",
        ) from exc


async def run_idempotent_command(
    db: AsyncSession,
    *,
    client_command_id: Optional[str],
    command_type: str,
    payload: Dict[str, Any],
    actor: AuthenticatedActor,
    empresa_id: Optional[int],
    executor: Callable[[], Awaitable[Dict[str, Any]]],
) -> Tuple[bool, Dict[str, Any]]:
    """
    Protocolo endurecido de idempotencia + fencing durable:
    - Si client_command_id es None, ejecuta directamente sin registro de replay.
    - Si client_command_id esta presente:
      1) Toma lock transaccional por command_id (pg_advisory_xact_lock).
      2) Si esta cercado en sync_command_fences -> 409 COMMAND_FENCED_NOT_APPLIED.
      3) Si ya existe en sync_idempotency_log:
         - Mismo payload_sha256 -> devuelve (True, committed_ack) con idempotent_replay=True.
         - Payload distinto     -> 409 IDEMPOTENCY_PAYLOAD_MISMATCH.
      4) Ejecuta el comando y persiste committed_ack_json en la misma transaccion.
    """
    cmd_uuid = parse_command_id(client_command_id)
    if not cmd_uuid:
        result = await executor()
        return False, result

    payload_hash = canonical_payload_hash(command_type, payload)

    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:cid))"),
        {"cid": cmd_uuid},
    )

    fence = (
        await db.execute(
            text(
                """
                SELECT client_command_id::text AS id, motivo, fenced_at
                FROM sync_command_fences
                WHERE client_command_id = CAST(:cid AS uuid)
                """
            ),
            {"cid": cmd_uuid},
        )
    ).first()
    if fence:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "COMMAND_FENCED_NOT_APPLIED",
                "client_command_id": cmd_uuid,
                "motivo": fence.motivo,
            },
        )

    existing = (
        await db.execute(
            text(
                """
                SELECT payload_sha256, committed_ack_json
                FROM sync_idempotency_log
                WHERE client_command_id = CAST(:cid AS uuid)
                """
            ),
            {"cid": cmd_uuid},
        )
    ).first()

    if existing:
        if existing.payload_sha256 != payload_hash:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "IDEMPOTENCY_PAYLOAD_MISMATCH",
                    "client_command_id": cmd_uuid,
                    "message": "El mismo client_command_id fue reutilizado con un payload distinto.",
                },
            )
        ack = dict(existing.committed_ack_json)
        ack["idempotent_replay"] = True
        return True, ack

    result = await executor()
    ack_to_store = {
        **result,
        "client_command_id": cmd_uuid,
        "committed_ack": True,
        "idempotent_replay": False,
    }

    await db.execute(
        text(
            """
            INSERT INTO sync_idempotency_log (
                client_command_id, command_type, actor_usuario_id,
                empresa_id, payload_sha256, http_status, committed_ack_json
            ) VALUES (
                CAST(:cid AS uuid), :ctype, CAST(:uid AS uuid),
                :emp, :sha, 200, CAST(:ack AS jsonb)
            )
            """
        ),
        {
            "cid": cmd_uuid,
            "ctype": command_type,
            "uid": actor.usuario_id,
            "emp": empresa_id,
            "sha": payload_hash,
            "ack": json.dumps(ack_to_store, default=str),
        },
    )
    return False, ack_to_store
