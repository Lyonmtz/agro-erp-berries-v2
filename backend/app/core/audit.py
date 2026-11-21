import json
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthenticatedActor


async def registrar_auditoria(
    db: AsyncSession,
    actor: Optional[AuthenticatedActor],
    *,
    modulo: str,
    accion: str,
    tipo_entidad: Optional[str] = None,
    id_entidad: Optional[str] = None,
    empresa_id: Optional[int] = None,
    sucursal_id: Optional[int] = None,
    unidad_operativa_id: Optional[int] = None,
    datos_antes: Optional[Any] = None,
    datos_despues: Optional[Any] = None,
) -> None:
    """Registra eventos auditables en auditoria_universal dentro de la transaccion activa."""
    await db.execute(
        text(
            """
            INSERT INTO auditoria_universal (
                usuario_id, actor_username, rol_codigo,
                empresa_id, sucursal_id, unidad_operativa_id,
                modulo, accion, tipo_entidad, id_entidad,
                datos_antes, datos_despues, ip_origen
            ) VALUES (
                CAST(:uid AS uuid), :uname, :rol,
                :emp, :suc, :uo,
                :mod, :acc, :tent, :ient,
                CAST(:antes AS jsonb), CAST(:despues AS jsonb), :ip
            )
            """
        ),
        {
            "uid": actor.usuario_id if actor else None,
            "uname": actor.username if actor else "SYSTEM",
            "rol": actor.primary_rol if actor else "SYSTEM",
            "emp": empresa_id,
            "suc": sucursal_id,
            "uo": unidad_operativa_id,
            "mod": modulo,
            "acc": accion,
            "tent": tipo_entidad,
            "ient": str(id_entidad) if id_entidad is not None else None,
            "antes": json.dumps(datos_antes, default=str) if datos_antes is not None else None,
            "despues": json.dumps(datos_despues, default=str) if datos_despues is not None else None,
            "ip": actor.ip_origen if actor else None,
        },
    )
