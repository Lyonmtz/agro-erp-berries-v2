"""
Servicio del modulo merqry_writer (APAGADO POR DEFECTO).

Responsabilidades actuales:
  1. Validar firewall de circuito IMSS_MERQRY y pre-validaciones de SPs.
  2. Persistir comandos en PostgreSQL (`merqry_write_outbox`) con idempotencia
     estricta (`idempotency_key` + `payload_sha256` -> 409 en payload distinto)
     y bitacora inmutable (`merqry_write_audit_log` + `auditoria_universal`).
  3. Mantener el dispatch hacia MySQL estrictamente BLOQUEADO (fail-closed)
     mientras `MERQRY_WRITE_ENABLED=false` o falte cualquiera de los 5 candados.
"""

import hashlib
import json
import uuid
from typing import Any, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.config import settings
from app.core.security import AuthenticatedActor
from app.modules.merqry_writer.firewall import (
    FROZEN_READONLY_SCHEMAS,
    SAFE_INITIAL_STATUS_BY_MODULE,
    CircuitFirewallError,
    MerqryPrevalidationError,
    MerqryWriteGateError,
    enforce_circuit_and_mov_firewall,
    prevalidate_payload,
    resolve_merqry_company,
)


def compute_payload_sha256(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_merqry_ref_tag(idempotency_key: str) -> str:
    compact = uuid.UUID(str(idempotency_key)).hex[:12].upper()
    return f"AGRO:{compact}"


def assert_write_gates_open(modulo: str) -> Dict[str, Any]:
    """
    Evalua los 5 candados fail-closed antes de permitir CUALQUIER conexion de
    escritura hacia un clon/laboratorio MySQL. Por defecto siempre falla cerrado.
    """
    if not settings.merqry_write_enabled:
        raise MerqryWriteGateError(
            "MERQRY_WRITE_DISABLED",
            "merqry_writer esta APAGADO por defecto (MERQRY_WRITE_ENABLED=false). "
            "No se permite abrir conexiones de escritura hacia MySQL.",
        )

    mode = settings.merqry_write_mode.strip().upper()
    if mode not in {"STAGING_DRAFT_ONLY", "CONTROLLED_APPLY"}:
        raise MerqryWriteGateError(
            "MERQRY_WRITE_MODE_DISABLED",
            f"MERQRY_WRITE_MODE='{mode}' bloquea cualquier despacho hacia MySQL.",
        )

    allowed_mods = settings.merqry_write_allowed_modules_set
    if modulo.upper() not in allowed_mods:
        raise MerqryWriteGateError(
            "MERQRY_MODULE_NOT_ENABLED",
            f"El modulo '{modulo}' no esta habilitado en MERQRY_WRITE_ALLOWED_MODULES ({sorted(allowed_mods)}).",
        )

    target_schema = settings.merqry_write_allowed_schema.strip()
    if not target_schema or target_schema.lower() in FROZEN_READONLY_SCHEMAS:
        raise MerqryWriteGateError(
            "MERQRY_TARGET_SCHEMA_BLOCKED",
            "MERQRY_WRITE_ALLOWED_SCHEMA debe apuntar explicitamente a un clon/lab autorizado "
            "y NUNCA a 'mq_bio_organicos_analisis'.",
        )

    if not settings.merqry_write_mysql_host or not settings.merqry_write_mysql_user:
        raise MerqryWriteGateError(
            "MERQRY_WRITE_CREDENTIALS_MISSING",
            "Faltan credenciales dedicadas de escritura (MERQRY_WRITE_MYSQL_HOST / USER).",
        )

    return {
        "mode": mode,
        "target_schema": target_schema,
        "target_host": settings.merqry_write_mysql_host,
        "target_port": settings.merqry_write_mysql_port,
        "actor_user": settings.merqry_write_actor_user[:15],
    }


async def log_writer_audit(
    db: AsyncSession,
    *,
    evento: str,
    severidad: str,
    actor_usuario_id: Optional[str],
    outbox_id: Optional[str] = None,
    circuito_intentado: Optional[str] = None,
    modulo: Optional[str] = None,
    merqry_mov: Optional[str] = None,
    detalle: Optional[Dict[str, Any]] = None,
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO merqry_write_audit_log (
                outbox_id, evento, severidad, circuito_intentado,
                modulo, merqry_mov, actor_usuario_id, detalle
            ) VALUES (
                CAST(:outbox_id AS UUID), :evento, :severidad, :circ,
                :mod, :mov, CAST(:actor AS UUID), CAST(:detalle AS JSONB)
            )
            """
        ),
        {
            "outbox_id": outbox_id,
            "evento": evento,
            "severidad": severidad,
            "circ": circuito_intentado,
            "mod": modulo,
            "mov": merqry_mov,
            "actor": actor_usuario_id,
            "detalle": json.dumps(detalle or {}, ensure_ascii=False),
        },
    )


async def stage_outbox_command(
    db: AsyncSession,
    *,
    actor: AuthenticatedActor,
    idempotency_key: str,
    empresa_id: int,
    circuito_pago: str,
    modulo: str,
    merqry_mov: str,
    modo_objetivo: str,
    payload: Dict[str, Any],
    origen_tabla: Optional[str] = None,
    origen_registro_id: Optional[str] = None,
) -> Tuple[Dict[str, Any], bool]:
    """
    Valida y registra un comando en `merqry_write_outbox` (solo PostgreSQL, sin tocar MySQL).
    Retorna `(row_dict, idempotent_replay)`.
    Lanza:
      - CircuitFirewallError -> 403
      - MerqryPrevalidationError -> 422
      - ValueError("IDEMPOTENCY_CONFLICT") -> 409
    """
    idem_uuid = str(uuid.UUID(str(idempotency_key)))

    # 1. Firewall duro de circuito y lista negra (siempre se audita el bloqueo)
    try:
        circ_ok, mod_ok, mov_ok = enforce_circuit_and_mov_firewall(
            circuito_pago=circuito_pago,
            modulo=modulo,
            merqry_mov=merqry_mov,
        )
    except CircuitFirewallError as exc:
        await log_writer_audit(
            db,
            evento=exc.code,
            severidad="BLOCKED",
            actor_usuario_id=actor.usuario_id,
            circuito_intentado=circuito_pago,
            modulo=modulo,
            merqry_mov=merqry_mov,
            detalle={"message": exc.message, "idempotency_key": idem_uuid},
        )
        await db.commit()
        raise

    # 2. Resolver empresa por clave oficial (BIO->(1,1), NFA->(2,2))
    emp_res = await db.execute(
        text("SELECT id, clave, razon_social FROM empresas WHERE id = :eid"),
        {"eid": empresa_id},
    )
    emp_row = emp_res.mappings().first()
    if not emp_row:
        raise MerqryPrevalidationError("00120", f"Empresa id={empresa_id} no existe en PostgreSQL.")

    merqry_emp, merqry_suc = resolve_merqry_company(emp_row["clave"])

    # 3. Pre-validacion espejo de SPs de Merqry
    try:
        preval_summary = prevalidate_payload(mod_ok, mov_ok, payload)
    except CircuitFirewallError as exc:
        await log_writer_audit(
            db,
            evento=exc.code,
            severidad="BLOCKED",
            actor_usuario_id=actor.usuario_id,
            circuito_intentado=circuito_pago,
            modulo=mod_ok,
            merqry_mov=mov_ok,
            detalle={"message": exc.message, "idempotency_key": idem_uuid},
        )
        await db.commit()
        raise
    except MerqryPrevalidationError as exc:
        await log_writer_audit(
            db,
            evento="PREVALIDATION_FAILED",
            severidad="WARNING",
            actor_usuario_id=actor.usuario_id,
            circuito_intentado=circ_ok,
            modulo=mod_ok,
            merqry_mov=mov_ok,
            detalle={
                "merqry_code": exc.merqry_code,
                "message": exc.message,
                "detalles": exc.detalles,
                "idempotency_key": idem_uuid,
            },
        )
        await db.commit()
        raise

    # 4. Idempotencia estricta con hash canonico
    canonical_envelope = {
        "empresa_id": empresa_id,
        "circuito_pago": circ_ok,
        "modulo": mod_ok,
        "merqry_mov": mov_ok,
        "modo_objetivo": modo_objetivo,
        "payload": payload,
    }
    payload_sha256 = compute_payload_sha256(canonical_envelope)

    existing_res = await db.execute(
        text(
            """
            SELECT
                id::text, idempotency_key::text, payload_sha256, empresa_id, empresa_clave,
                merqry_empresa, merqry_sucursal, circuito_pago, modulo, merqry_mov,
                modo_objetivo, estatus_inicial_merqry, merqry_ref_tag, estado,
                prevalidacion_ok, prevalidacion_resumen, intentos, creado_en::text
            FROM merqry_write_outbox
            WHERE idempotency_key = CAST(:idem AS UUID)
            """
        ),
        {"idem": idem_uuid},
    )
    existing = existing_res.mappings().first()
    if existing:
        if existing["payload_sha256"] != payload_sha256:
            raise ValueError("IDEMPOTENCY_CONFLICT")
        return dict(existing), True

    # 5. Insertar en outbox PostgreSQL (todavia sin tocar MySQL)
    ref_tag = build_merqry_ref_tag(idem_uuid)
    estatus_inicial = SAFE_INITIAL_STATUS_BY_MODULE[mod_ok]

    ins_res = await db.execute(
        text(
            """
            INSERT INTO merqry_write_outbox (
                idempotency_key, payload_sha256, empresa_id, empresa_clave,
                merqry_empresa, merqry_sucursal, circuito_pago, modulo, merqry_mov,
                modo_objetivo, estatus_inicial_merqry, merqry_ref_tag,
                origen_tabla, origen_registro_id, payload_json,
                prevalidacion_ok, prevalidacion_resumen, estado, creado_por_usuario_id
            ) VALUES (
                CAST(:idem AS UUID), :sha, :eid, :eclave,
                :mq_emp, :mq_suc, :circ, :mod, :mov,
                :modo, :est_ini, :ref_tag,
                :orig_tbl, :orig_id, CAST(:payload AS JSONB),
                TRUE, CAST(:preval AS JSONB), 'PREVALIDATED', CAST(:actor AS UUID)
            )
            RETURNING
                id::text, idempotency_key::text, payload_sha256, empresa_id, empresa_clave,
                merqry_empresa, merqry_sucursal, circuito_pago, modulo, merqry_mov,
                modo_objetivo, estatus_inicial_merqry, merqry_ref_tag, estado,
                prevalidacion_ok, prevalidacion_resumen, intentos, creado_en::text
            """
        ),
        {
            "idem": idem_uuid,
            "sha": payload_sha256,
            "eid": empresa_id,
            "eclave": emp_row["clave"],
            "mq_emp": merqry_emp,
            "mq_suc": merqry_suc,
            "circ": circ_ok,
            "mod": mod_ok,
            "mov": mov_ok,
            "modo": modo_objetivo,
            "est_ini": estatus_inicial,
            "ref_tag": ref_tag,
            "orig_tbl": origen_tabla,
            "orig_id": origen_registro_id,
            "payload": json.dumps(payload, ensure_ascii=False),
            "preval": json.dumps(preval_summary, ensure_ascii=False),
            "actor": actor.usuario_id,
        },
    )
    created = dict(ins_res.mappings().first())

    await log_writer_audit(
        db,
        outbox_id=created["id"],
        evento="OUTBOX_STAGED_PREVALIDATED",
        severidad="INFO",
        actor_usuario_id=actor.usuario_id,
        circuito_intentado=circ_ok,
        modulo=mod_ok,
        merqry_mov=mov_ok,
        detalle={
            "merqry_ref_tag": ref_tag,
            "merqry_empresa": merqry_emp,
            "merqry_sucursal": merqry_suc,
            "prevalidacion_resumen": preval_summary,
        },
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="merqry_writer",
        accion="STAGE_OUTBOX",
        tipo_entidad="merqry_write_outbox",
        id_entidad=created["id"],
        empresa_id=empresa_id,
        datos_despues={
            "modulo": mod_ok,
            "merqry_mov": mov_ok,
            "merqry_ref_tag": ref_tag,
            "circuito_pago": circ_ok,
        },
    )
    await db.commit()
    return created, False
