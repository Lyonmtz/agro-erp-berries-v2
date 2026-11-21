import uuid

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings


async def _login(client: AsyncClient, username: str, password: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _valid_ap_alta_payload() -> dict:
    return {
        "fecha_emision": "2026-11-21",
        "moneda": "Pesos",
        "partidas": [
            {
                "contacto": "EMP-TEST-01",
                "personal_sucursal": "1",
                "departamento": "PRODUCCION",
                "puesto": "COSECHADOR",
                "tipo_nomina": "SEMANAL",
                "zona_economica": "A",
                "periodo": "SEMANAL",
                "jornada": "DIURNA",
                "tipo_contrato": "TIEMPO DETERMINADO",
                "sueldo_diario": 315.04,
                "tipo_dias": "TRABAJADOS",
                "fecha_alta": "2026-11-21",
                "fecha_antiguedad": "2026-11-21",
                "jefe_inmediato": "SUP-001",
            }
        ],
    }


@pytest.mark.asyncio
async def test_merqry_writer_apagado_por_defecto_y_esquema_forense_prohibido(
    async_client: AsyncClient,
):
    admin = await _login(async_client, "admin.dir", "AdminBerries2026!")
    h = _auth(admin["access_token"])

    r = await async_client.get("/api/v1/merqry-writer/status", headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["merqry_write_enabled"] is False
    assert body["merqry_write_mode"] == "DISABLED"
    assert body["merqry_readonly_mirror_mode"] is True
    assert body["allowed_circuit"] == "IMSS_MERQRY"
    assert body["company_mapping_by_clave"] == {"BIO": [1, 1], "NFA": [2, 2]}
    assert "mq_bio_organicos_analisis" in body["frozen_readonly_schemas"]
    assert "nomina especial" in body["blacklisted_movs"]

    # Prohibicion estricta en Settings: nunca apuntar merqry_writer al respaldo forense
    with pytest.raises(ValidationError):
        Settings(merqry_write_allowed_schema="mq_bio_organicos_analisis")


@pytest.mark.asyncio
async def test_firewall_bloqueo_duro_especial_contabilidad_nomina_especial_y_check_pg(
    async_client: AsyncClient, db_session: AsyncSession
):
    admin = await _login(async_client, "admin.dir", "AdminBerries2026!")
    h = _auth(admin["access_token"])
    nfa_id = (await db_session.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()

    # 1) Bloqueo duro contra circuito ESPECIAL_CONTABILIDAD
    r_esp = await async_client.post(
        "/api/v1/merqry-writer/outbox/stage",
        headers=h,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "empresa_id": nfa_id,
            "circuito_pago": "ESPECIAL_CONTABILIDAD",
            "modulo": "AP",
            "merqry_mov": "Alta",
            "payload": _valid_ap_alta_payload(),
        },
    )
    assert r_esp.status_code == 403, r_esp.text
    assert r_esp.json()["detail"]["code"] == "CIRCUIT_FIREWALL_BLOCKED"

    # 2) Bloqueo duro contra 'Nomina Especial' (homonimo fiscal NOM.EX en Merqry)
    r_ne = await async_client.post(
        "/api/v1/merqry-writer/outbox/stage",
        headers=h,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "empresa_id": nfa_id,
            "circuito_pago": "IMSS_MERQRY",
            "modulo": "NOM",
            "merqry_mov": "Nomina Especial",
            "payload": {
                "fecha_emision": "2026-11-21",
                "fecha_del": "2026-11-15",
                "fecha_al": "2026-11-21",
                "fecha_pago": "2026-11-21",
                "formula_id": 1,
                "moneda": "Pesos",
                "partidas": [{"contacto": "EMP-1", "tipo": "P", "importe": 2350}],
            },
        },
    )
    assert r_ne.status_code == 403, r_ne.text
    assert r_ne.json()["detail"]["code"] == "BLACKLISTED_MERQRY_MOV"

    # Verificar que ambos bloqueos quedaron auditados en merqry_write_audit_log
    blocked_cnt = (
        await db_session.execute(
            text("SELECT COUNT(*) FROM merqry_write_audit_log WHERE severidad = 'BLOCKED'")
        )
    ).scalar()
    assert blocked_cnt >= 2

    # 3) Candado fisico CHECK en PostgreSQL impide insertar ESPECIAL_CONTABILIDAD directamente
    with pytest.raises(IntegrityError):
        await db_session.execute(
            text(
                """
                INSERT INTO merqry_write_outbox (
                    idempotency_key, payload_sha256, empresa_id, empresa_clave,
                    merqry_empresa, merqry_sucursal, circuito_pago, modulo,
                    merqry_mov, estatus_inicial_merqry, merqry_ref_tag, payload_json
                ) VALUES (
                    CAST(:idem AS UUID), REPEAT('a', 64), :eid, 'NFA',
                    2, 2, 'ESPECIAL_CONTABILIDAD', 'AP',
                    'Alta', 'SINAPLICAR', 'AGRO:RAWBLOCK001', '{}'::jsonb
                )
                """
            ),
            {"idem": str(uuid.uuid4()), "eid": nfa_id},
        )
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_espejo_bug_sp_nomina_validar_y_cuadre_contable(async_client: AsyncClient):
    admin = await _login(async_client, "admin.dir", "AdminBerries2026!")
    h = _auth(admin["access_token"])

    base_nom = {
        "fecha_emision": "2026-11-21",
        "fecha_del": "2026-11-15",
        "fecha_al": "2026-11-21",
        "fecha_pago": "2026-11-21",
        "formula_id": 10,
        "moneda": "Pesos",
        "partidas": [
            {"contacto": "EMP-100", "tipo": "P", "importe": 2500.00},
            {"contacto": "EMP-100", "tipo": "D", "importe": 300.00},
        ],
    }

    # 1) 09001: falta formula_id
    p1 = {**base_nom, "formula_id": None}
    r1 = await async_client.post(
        "/api/v1/merqry-writer/prevalidate",
        headers=h,
        json={"circuito_pago": "IMSS_MERQRY", "modulo": "NOM", "merqry_mov": "Nomina", "payload": p1},
    )
    assert r1.status_code == 422 and r1.json()["detail"]["code"] == "09001"

    # 2) 09017: falta fecha_pago
    p2 = {**base_nom, "fecha_pago": None}
    r2 = await async_client.post(
        "/api/v1/merqry-writer/prevalidate",
        headers=h,
        json={"circuito_pago": "IMSS_MERQRY", "modulo": "NOM", "merqry_mov": "Nomina", "payload": p2},
    )
    assert r2.status_code == 422 and r2.json()["detail"]["code"] == "09017"

    # 3) 09002: excede saldo/cantidad de incidencia
    p3 = {
        **base_nom,
        "aplicaciones_incid": [{"contacto": "EMP-100", "disponible": 100.00, "valor": 150.00}],
    }
    r3 = await async_client.post(
        "/api/v1/merqry-writer/prevalidate",
        headers=h,
        json={"circuito_pago": "IMSS_MERQRY", "modulo": "NOM", "merqry_mov": "Nomina", "payload": p3},
    )
    assert r3.status_code == 422 and r3.json()["detail"]["code"] == "09002"

    # 4) 09003: importe neto negativo a pagar
    p4 = {
        **base_nom,
        "partidas": [
            {"contacto": "EMP-100", "tipo": "P", "importe": 1000.00},
            {"contacto": "EMP-100", "tipo": "D", "importe": 1250.00},
        ],
    }
    r4 = await async_client.post(
        "/api/v1/merqry-writer/prevalidate",
        headers=h,
        json={"circuito_pago": "IMSS_MERQRY", "modulo": "NOM", "merqry_mov": "Nomina", "payload": p4},
    )
    assert r4.status_code == 422 and r4.json()["detail"]["code"] == "09003"

    # 5) NOM valida pasa y reporta estatus inicial 'PREVIO'
    r_ok = await async_client.post(
        "/api/v1/merqry-writer/prevalidate",
        headers=h,
        json={"circuito_pago": "IMSS_MERQRY", "modulo": "NOM", "merqry_mov": "Nomina", "payload": base_nom},
    )
    assert r_ok.status_code == 200, r_ok.text
    assert r_ok.json()["resumen"]["estatus_inicial_merqry"] == "PREVIO"

    # 6) CONT descuadrada -> 05005
    r_cont = await async_client.post(
        "/api/v1/merqry-writer/prevalidate",
        headers=h,
        json={
            "circuito_pago": "IMSS_MERQRY",
            "modulo": "CONT",
            "merqry_mov": "Diario",
            "payload": {
                "fecha_emision": "2026-11-21",
                "moneda": "Pesos",
                "partidas": [
                    {"cuenta": "601-001-001", "cargo": 500.00, "abono": 0},
                    {"cuenta": "102-001-001", "cargo": 0, "abono": 499.99},
                ],
            },
        },
    )
    assert r_cont.status_code == 422 and r_cont.json()["detail"]["code"] == "05005"


@pytest.mark.asyncio
async def test_outbox_idempotencia_mapeo_empresa_invertido_y_dispatch_fail_closed(
    async_client: AsyncClient, db_session: AsyncSession
):
    admin = await _login(async_client, "admin.dir", "AdminBerries2026!")
    h = _auth(admin["access_token"])

    nfa_id = (await db_session.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()
    bio_id = (await db_session.execute(text("SELECT id FROM empresas WHERE clave = 'BIO'"))).scalar()
    idem = str(uuid.uuid4())
    payload = _valid_ap_alta_payload()

    # 1) Encolar para NFA (PG id=1) -> debe mapear a Merqry (Empresa=2, Sucursal=2)
    r1 = await async_client.post(
        "/api/v1/merqry-writer/outbox/stage",
        headers=h,
        json={
            "idempotency_key": idem,
            "empresa_id": nfa_id,
            "circuito_pago": "IMSS_MERQRY",
            "modulo": "AP",
            "merqry_mov": "Alta",
            "payload": payload,
        },
    )
    assert r1.status_code == 201, r1.text
    b1 = r1.json()
    assert b1["idempotent_replay"] is False
    assert b1["dispatched_to_merqry"] is False
    assert b1["outbox"]["empresa_clave"] == "NFA"
    assert b1["outbox"]["merqry_empresa"] == 2
    assert b1["outbox"]["merqry_sucursal"] == 2
    assert b1["outbox"]["estatus_inicial_merqry"] == "SINAPLICAR"
    assert b1["outbox"]["merqry_ref_tag"].startswith("AGRO:")

    # 2) Replay identico -> mismo ID con idempotent_replay=True
    r2 = await async_client.post(
        "/api/v1/merqry-writer/outbox/stage",
        headers=h,
        json={
            "idempotency_key": idem,
            "empresa_id": nfa_id,
            "circuito_pago": "IMSS_MERQRY",
            "modulo": "AP",
            "merqry_mov": "Alta",
            "payload": payload,
        },
    )
    assert r2.status_code == 201, r2.text
    assert r2.json()["idempotent_replay"] is True
    assert r2.json()["outbox"]["id"] == b1["outbox"]["id"]

    # 3) Mismo idempotency_key con payload mutado -> 409 Conflict
    mutated = _valid_ap_alta_payload()
    mutated["partidas"][0]["sueldo_diario"] = 400.00
    r3 = await async_client.post(
        "/api/v1/merqry-writer/outbox/stage",
        headers=h,
        json={
            "idempotency_key": idem,
            "empresa_id": nfa_id,
            "circuito_pago": "IMSS_MERQRY",
            "modulo": "AP",
            "merqry_mov": "Alta",
            "payload": mutated,
        },
    )
    assert r3.status_code == 409, r3.text
    assert r3.json()["detail"]["code"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"

    # 4) Encolar para BIO (PG id=2) -> debe mapear a Merqry (Empresa=1, Sucursal=1)
    r_bio = await async_client.post(
        "/api/v1/merqry-writer/outbox/stage",
        headers=h,
        json={
            "idempotency_key": str(uuid.uuid4()),
            "empresa_id": bio_id,
            "circuito_pago": "IMSS_MERQRY",
            "modulo": "AP",
            "merqry_mov": "Alta",
            "payload": payload,
        },
    )
    assert r_bio.status_code == 201, r_bio.text
    assert r_bio.json()["outbox"]["empresa_clave"] == "BIO"
    assert r_bio.json()["outbox"]["merqry_empresa"] == 1
    assert r_bio.json()["outbox"]["merqry_sucursal"] == 1

    # 5) Dispatch falla cerrado (503 MERQRY_WRITE_DISABLED) sin abrir MySQL
    oid = b1["outbox"]["id"]
    r_disp = await async_client.post(f"/api/v1/merqry-writer/outbox/{oid}/dispatch", headers=h)
    assert r_disp.status_code == 503, r_disp.text
    assert r_disp.json()["detail"]["code"] == "MERQRY_WRITE_DISABLED"

    # 6) Cancelar outbox pendiente
    r_cancel = await async_client.post(f"/api/v1/merqry-writer/outbox/{oid}/cancel", headers=h)
    assert r_cancel.status_code == 200, r_cancel.text
    assert r_cancel.json()["estado"] == "CANCELLED"
