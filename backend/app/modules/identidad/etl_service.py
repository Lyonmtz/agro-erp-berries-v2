from datetime import date
import json
import re
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import registrar_auditoria
from app.core.security import AuthenticatedActor

CURP_REGEX = re.compile(r"^[A-Z]{4}\d{6}[HM][A-Z0-9]{6}\d$")


def _norm_str(val: Optional[str]) -> Optional[str]:
    if val is None:
        return None
    s = " ".join(str(val).strip().split())
    return s if s else None


def _norm_upper(val: Optional[str]) -> Optional[str]:
    s = _norm_str(val)
    return s.upper() if s else None


def _norm_phone(val: Optional[str]) -> Optional[str]:
    if val is None:
        return None
    digits = re.sub(r"\D+", "", str(val))
    return digits if len(digits) >= 7 else None


async def ejecutar_etl_identidades(
    db: AsyncSession,
    *,
    fuente_nombre: str,
    empresa_id: int,
    registros: List[Dict[str, Any]],
    actor: Optional[AuthenticatedActor] = None,
    sucursal_id: Optional[int] = None,
    unidad_operativa_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    ETL auditable de migracion de identidades desde CSV/Sheets/historicos.

    Reglas estrictas (de campo + rrhh-automation-system):
    1. Concilia unicamente por CURP valido y exacto.
    2. Si existe un CURP exacto pero el nombre/apellido difiere sustancialmente ->
       NO sobreescribe: envia a etl_cuarentena_identidad (CONFLICTO_CURP_NOMBRE).
    3. PROHIBIDO fusionar personas por coincidencia de nombre completo o telefono:
       si el CURP falta/es invalido o es nuevo pero coincide el nombre completo o el telefono
       con otra persona existente -> envia a etl_cuarentena_identidad para revision humana.
    4. Cuando crea/concilia una persona y vienen datos laborales (numero_empleado, puesto_codigo),
       crea/concilia relaciones_laborales preservando circuito_pago (IMSS_MERQRY vs ESPECIAL_CONTABILIDAD).
    """
    lote_row = (
        await db.execute(
            text(
                """
                INSERT INTO etl_lotes_migracion (
                    fuente_nombre, empresa_id, ejecutado_por_usuario_id,
                    total_registros, estatus
                ) VALUES (
                    :fuente, :emp, CAST(:uid AS uuid), :tot, 'EN_PROCESO'
                )
                RETURNING id::text AS id
                """
            ),
            {
                "fuente": fuente_nombre,
                "emp": empresa_id,
                "uid": actor.usuario_id if actor else None,
                "tot": len(registros),
            },
        )
    ).first()
    lote_id = lote_row.id

    creados = 0
    conciliados_curp = 0
    enviados_cuarentena = 0
    detalles_cuarentena: List[Dict[str, Any]] = []

    for idx, raw in enumerate(registros, start=1):
        curp = _norm_upper(raw.get("curp"))
        nombre = _norm_str(raw.get("nombre"))
        ap_pat = _norm_str(raw.get("apellido_paterno"))
        ap_mat = _norm_str(raw.get("apellido_materno"))
        tel = _norm_phone(raw.get("telefono"))
        rfc = _norm_upper(raw.get("rfc"))
        nss = _norm_str(raw.get("nss"))
        num_emp = _norm_upper(raw.get("numero_empleado"))
        merqry_id = _norm_str(raw.get("merqry_employee_id"))
        circuito = _norm_upper(raw.get("circuito_pago")) or "IMSS_MERQRY"
        if circuito not in ("IMSS_MERQRY", "ESPECIAL_CONTABILIDAD"):
            circuito = "IMSS_MERQRY"
        puesto_codigo = _norm_upper(raw.get("puesto_codigo")) or "COSECHADOR"

        if not nombre or not ap_pat:
            enviados_cuarentena += 1
            await _enviar_cuarentena(
                db, lote_id, empresa_id, idx, "OTRO_CONFLICTO", None, raw
            )
            detalles_cuarentena.append({"fila": idx, "motivo": "OTRO_CONFLICTO"})
            continue

        # Caso 1: CURP ausente o formato invalido -> nunca fusionar ni crear a ciegas
        if not curp or not CURP_REGEX.match(curp):
            cand = await _buscar_homonimo_o_telefono(db, nombre, ap_pat, ap_mat, tel)
            motivo = (
                "HOMONIMO_SIN_CURP_COINCIDENTE"
                if cand
                else "CURP_INVALIDO_O_AUSENTE"
            )
            enviados_cuarentena += 1
            await _enviar_cuarentena(
                db, lote_id, empresa_id, idx, motivo, cand, raw
            )
            detalles_cuarentena.append(
                {"fila": idx, "motivo": motivo, "persona_candidata_id": cand}
            )
            continue

        # Caso 2: Buscar por CURP exacto
        existente = (
            await db.execute(
                text(
                    """
                    SELECT id::text AS id, nombre, apellido_paterno, apellido_materno
                    FROM personas
                    WHERE curp = :curp
                    """
                ),
                {"curp": curp},
            )
        ).first()

        if existente:
            # Validar que el nombre/apellido paterno no contradiga el CURP
            if (
                existente.nombre.strip().upper() != nombre.upper()
                or existente.apellido_paterno.strip().upper() != ap_pat.upper()
            ):
                enviados_cuarentena += 1
                await _enviar_cuarentena(
                    db,
                    lote_id,
                    empresa_id,
                    idx,
                    "CONFLICTO_CURP_NOMBRE",
                    existente.id,
                    raw,
                )
                detalles_cuarentena.append(
                    {
                        "fila": idx,
                        "motivo": "CONFLICTO_CURP_NOMBRE",
                        "persona_candidata_id": existente.id,
                    }
                )
                continue

            persona_id = existente.id
            conciliados_curp += 1
        else:
            # CURP nuevo: verificar que NO exista homonimo ni telefono duplicado
            homonimo = (
                await db.execute(
                    text(
                        """
                        SELECT id::text AS id
                        FROM personas
                        WHERE UPPER(nombre) = :nom
                          AND UPPER(apellido_paterno) = :ap
                          AND UPPER(COALESCE(apellido_materno, '')) = :am
                        LIMIT 1
                        """
                    ),
                    {
                        "nom": nombre.upper(),
                        "ap": ap_pat.upper(),
                        "am": (ap_mat or "").upper(),
                    },
                )
            ).first()
            if homonimo:
                enviados_cuarentena += 1
                await _enviar_cuarentena(
                    db,
                    lote_id,
                    empresa_id,
                    idx,
                    "HOMONIMO_SIN_CURP_COINCIDENTE",
                    homonimo.id,
                    raw,
                )
                detalles_cuarentena.append(
                    {
                        "fila": idx,
                        "motivo": "HOMONIMO_SIN_CURP_COINCIDENTE",
                        "persona_candidata_id": homonimo.id,
                    }
                )
                continue

            if tel:
                tel_dup = (
                    await db.execute(
                        text("SELECT id::text AS id FROM personas WHERE telefono = :tel LIMIT 1"),
                        {"tel": tel},
                    )
                ).first()
                if tel_dup:
                    enviados_cuarentena += 1
                    await _enviar_cuarentena(
                        db,
                        lote_id,
                        empresa_id,
                        idx,
                        "TELEFONO_DUPLICADO_OTRA_PERSONA",
                        tel_dup.id,
                        raw,
                    )
                    detalles_cuarentena.append(
                        {
                            "fila": idx,
                            "motivo": "TELEFONO_DUPLICADO_OTRA_PERSONA",
                            "persona_candidata_id": tel_dup.id,
                        }
                    )
                    continue

            clave_qr = f"QR-PER-{uuid.uuid4().hex[:10].upper()}"
            nueva = (
                await db.execute(
                    text(
                        """
                        INSERT INTO personas (
                            curp, rfc, nss, nombre, apellido_paterno, apellido_materno,
                            telefono, email, clave_interna_qr
                        ) VALUES (
                            :curp, :rfc, :nss, :nom, :ap, :am, :tel, :em, :qr
                        )
                        RETURNING id::text AS id
                        """
                    ),
                    {
                        "curp": curp,
                        "rfc": rfc,
                        "nss": nss,
                        "nom": nombre,
                        "ap": ap_pat,
                        "am": ap_mat,
                        "tel": tel,
                        "em": _norm_str(raw.get("email")),
                        "qr": clave_qr,
                    },
                )
            ).first()
            persona_id = nueva.id
            await db.execute(
                text(
                    """
                    INSERT INTO codigos_alternativos (
                        tipo_entidad, id_entidad, sistema_origen, codigo_externo, descripcion
                    ) VALUES ('PERSONA', :pid, 'INTERNO_QR', :qr, 'QR generado por ETL')
                    ON CONFLICT (sistema_origen, tipo_entidad, codigo_externo) DO NOTHING
                    """
                ),
                {"pid": persona_id, "qr": clave_qr},
            )
            creados += 1

        # Si trae numero_empleado, crear/conciliar relacion laboral sin sobrescribir puesto existente
        if num_emp:
            puesto_id = (
                await db.execute(
                    text("SELECT id FROM puestos WHERE codigo_puesto = :c LIMIT 1"),
                    {"c": puesto_codigo},
                )
            ).scalar()
            if puesto_id is None:
                puesto_id = (
                    await db.execute(text("SELECT id FROM puestos ORDER BY id LIMIT 1"))
                ).scalar()

            f_ing_raw = raw.get("fecha_ingreso")
            f_ing = date.fromisoformat(f_ing_raw) if isinstance(f_ing_raw, str) and f_ing_raw else date.today()

            rel = (
                await db.execute(
                    text(
                        """
                        INSERT INTO relaciones_laborales (
                            persona_id, empresa_id, sucursal_id, unidad_operativa_id,
                            numero_empleado, merqry_employee_id, circuito_pago,
                            puesto_nominal_id, fecha_ingreso, estatus
                        ) VALUES (
                            CAST(:pid AS uuid), :emp, :suc, :uo,
                            :num, :mrq, :circ, :puesto, :fing, 'ACTIVO'
                        )
                        ON CONFLICT (empresa_id, numero_empleado) DO UPDATE SET
                            merqry_employee_id = COALESCE(EXCLUDED.merqry_employee_id, relaciones_laborales.merqry_employee_id),
                            actualizado_en = NOW()
                        RETURNING id::text AS id
                        """
                    ),
                    {
                        "pid": persona_id,
                        "emp": empresa_id,
                        "suc": sucursal_id,
                        "uo": unidad_operativa_id,
                        "num": num_emp,
                        "mrq": merqry_id,
                        "circ": circuito,
                        "puesto": puesto_id,
                        "fing": f_ing,
                    },
                )
            ).first()

            if merqry_id and rel:
                await db.execute(
                    text(
                        """
                        INSERT INTO codigos_alternativos (
                            tipo_entidad, id_entidad, sistema_origen, codigo_externo, descripcion
                        ) VALUES ('RELACION_LABORAL', :rid, 'MERQRY', :mrq, 'ID Merqry importado por ETL (solo lectura)')
                        ON CONFLICT (sistema_origen, tipo_entidad, codigo_externo) DO NOTHING
                        """
                    ),
                    {"rid": rel.id, "mrq": merqry_id},
                )

    estatus_lote = "CON_CUARENTENA" if enviados_cuarentena > 0 else "COMPLETADO"
    resumen = {
        "total_registros": len(registros),
        "creados": creados,
        "conciliados_curp": conciliados_curp,
        "enviados_cuarentena": enviados_cuarentena,
        "cuarentena": detalles_cuarentena,
    }
    await db.execute(
        text(
            """
            UPDATE etl_lotes_migracion
               SET creados = :cr,
                   conciliados_curp = :co,
                   enviados_cuarentena = :cu,
                   estatus = :est,
                   resumen = CAST(:res AS jsonb)
             WHERE id = CAST(:lid AS uuid)
            """
        ),
        {
            "cr": creados,
            "co": conciliados_curp,
            "cu": enviados_cuarentena,
            "est": estatus_lote,
            "res": json.dumps(resumen),
            "lid": lote_id,
        },
    )
    await registrar_auditoria(
        db,
        actor,
        modulo="identidad",
        accion="ETL_IMPORTAR_IDENTIDADES",
        tipo_entidad="ETL_LOTE",
        id_entidad=lote_id,
        empresa_id=empresa_id,
        sucursal_id=sucursal_id,
        unidad_operativa_id=unidad_operativa_id,
        datos_despues=resumen,
    )
    return {"lote_id": lote_id, "estatus": estatus_lote, **resumen}


async def _buscar_homonimo_o_telefono(
    db: AsyncSession,
    nombre: str,
    ap_pat: str,
    ap_mat: Optional[str],
    tel: Optional[str],
) -> Optional[str]:
    if tel:
        sql = """
            SELECT id::text AS id
            FROM personas
            WHERE (UPPER(nombre) = :nom AND UPPER(apellido_paterno) = :ap
                   AND UPPER(COALESCE(apellido_materno, '')) = :am)
               OR telefono = :tel
            LIMIT 1
        """
        params = {
            "nom": nombre.upper(),
            "ap": ap_pat.upper(),
            "am": (ap_mat or "").upper(),
            "tel": tel,
        }
    else:
        sql = """
            SELECT id::text AS id
            FROM personas
            WHERE UPPER(nombre) = :nom
              AND UPPER(apellido_paterno) = :ap
              AND UPPER(COALESCE(apellido_materno, '')) = :am
            LIMIT 1
        """
        params = {
            "nom": nombre.upper(),
            "ap": ap_pat.upper(),
            "am": (ap_mat or "").upper(),
        }
    row = (await db.execute(text(sql), params)).first()
    return row.id if row else None


async def _enviar_cuarentena(
    db: AsyncSession,
    lote_id: str,
    empresa_id: int,
    fila: int,
    motivo: str,
    candidata_id: Optional[str],
    payload: Dict[str, Any],
) -> None:
    await db.execute(
        text(
            """
            INSERT INTO etl_cuarentena_identidad (
                lote_etl_id, empresa_id, fila_origen, motivo_conflicto,
                persona_candidata_id, payload_origen
            ) VALUES (
                CAST(:lid AS uuid), :emp, :fila, :motivo,
                CAST(:cand AS uuid), CAST(:pay AS jsonb)
            )
            """
        ),
        {
            "lid": lote_id,
            "emp": empresa_id,
            "fila": fila,
            "motivo": motivo,
            "cand": candidata_id,
            "pay": json.dumps(payload, default=str),
        },
    )
