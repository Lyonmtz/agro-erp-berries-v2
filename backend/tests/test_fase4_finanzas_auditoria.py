import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _login(client: AsyncClient, username: str, password: str) -> dict:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_presupuesto_gastos_circuito_separado_y_semaforo_sobregiro(
    async_client: AsyncClient, db_session: AsyncSession
):
    admin = await _login(async_client, "admin.dir", "AdminBerries2026!")
    h = _auth(admin["access_token"])
    nfa_id = (await db_session.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()

    # 1) Crear presupuesto para MANO_OBRA_IMSS ($10,000) y EMPAQUE ($5,000)
    r_p1 = await async_client.post(
        "/api/v1/finanzas/presupuestos",
        headers=h,
        json={
            "empresa_id": nfa_id,
            "anio": 2026,
            "periodo_clave": "2026-S47",
            "rubro": "MANO_OBRA_IMSS",
            "monto_presupuestado": 10000.00,
            "notas": "Presupuesto semanal IMSS Frambuesa",
        },
    )
    assert r_p1.status_code == 201, r_p1.text

    # 2) Bloqueo duro si intenta mezclar MANO_OBRA_IMSS con circuito ESPECIAL_CONTABILIDAD
    r_bad = await async_client.post(
        "/api/v1/finanzas/gastos",
        headers=h,
        json={
            "empresa_id": nfa_id,
            "fecha": "2026-11-20",
            "periodo_clave": "2026-S47",
            "rubro": "MANO_OBRA_IMSS",
            "circuito_origen": "ESPECIAL_CONTABILIDAD",
            "concepto": "Intento de mezcla prohibida",
            "monto": 500.00,
        },
    )
    assert r_bad.status_code == 403, r_bad.text
    assert r_bad.json()["detail"]["code"] == "CIRCUIT_MISMATCH"

    # 3) Registrar gasto valido (90% -> ALERTA) y segundo gasto (110% -> SOBREGIRO)
    r_g1 = await async_client.post(
        "/api/v1/finanzas/gastos",
        headers=h,
        json={
            "empresa_id": nfa_id,
            "fecha": "2026-11-20",
            "periodo_clave": "2026-S47",
            "rubro": "MANO_OBRA_IMSS",
            "circuito_origen": "IMSS_MERQRY",
            "concepto": "Semana 47 IMSS cuadrilla A",
            "monto": 9000.00,
            "folio_comprobante": "NOM-S47-A",
        },
    )
    assert r_g1.status_code == 201, r_g1.text
    assert r_g1.json()["control_presupuestal"]["semaforo"] == "ALERTA"

    r_g2 = await async_client.post(
        "/api/v1/finanzas/gastos",
        headers=h,
        json={
            "empresa_id": nfa_id,
            "fecha": "2026-11-21",
            "periodo_clave": "2026-S47",
            "rubro": "MANO_OBRA_IMSS",
            "circuito_origen": "IMSS_MERQRY",
            "concepto": "Horas extra dominical IMSS",
            "monto": 2000.00,
            "folio_comprobante": "NOM-S47-B",
        },
    )
    assert r_g2.status_code == 201, r_g2.text
    assert r_g2.json()["control_presupuestal"]["semaforo"] == "SOBREGIRO"

    r_ctrl = await async_client.get(
        f"/api/v1/finanzas/presupuestos/control?empresa_id={nfa_id}&periodo_clave=2026-S47",
        headers=h,
    )
    assert r_ctrl.status_code == 200, r_ctrl.text
    assert "MANO_OBRA_IMSS" in r_ctrl.json()["alertas_sobregiro"]


@pytest.mark.asyncio
async def test_conciliacion_multietapa_inmutable_reporte_ejecutivo_y_deteccion_tampering(
    async_client: AsyncClient, db_session: AsyncSession
):
    admin = await _login(async_client, "admin.dir", "AdminBerries2026!")
    h = _auth(admin["access_token"])

    nfa_id = (await db_session.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()
    lote_framb = (
        await db_session.execute(text("SELECT id FROM lotes_produccion WHERE codigo_lote = 'NFA-FRAMB-M01'"))
    ).scalar()
    rel = (
        await db_session.execute(
            text(
                "SELECT id::text AS rel_id, persona_id::text AS persona_id "
                "FROM relaciones_laborales WHERE numero_empleado = 'EMP-2001'"
            )
        )
    ).first()

    # 1) Capturar 20 cajas exportacion en campo y trasladar solo 18 a empaque (brecha = 2 cajas)
    r_cap = await async_client.post(
        "/api/v1/cosecha/capturas",
        headers=h,
        json={
            "client_command_id": str(uuid.uuid4()),
            "fecha": "2026-11-20",
            "lote_id": lote_framb,
            "persona_id": rel.persona_id,
            "relacion_laboral_id": rel.rel_id,
            "modo_captura": "VIVO",
            "codigo_trazabilidad_caja": f"F4-CAJA-{uuid.uuid4().hex[:6]}",
            "cajas_exportacion": 20,
            "cajas_nacional": 0,
            "cajas_merma_rezaga": 1,
            "nip_confirmado": True,
        },
    )
    assert r_cap.status_code == 201, r_cap.text

    r_tras = await async_client.post(
        "/api/v1/cosecha/traslados-cajas",
        headers=h,
        json={
            "fecha": "2026-11-20",
            "lote_origen_id": lote_framb,
            "folio_remision": f"REM-F4-{uuid.uuid4().hex[:6]}",
            "cantidad_cajas": 18,
            "calidad_fruta": "EXPORTACION",
            "destino_empaque": "Empaque Central NFA",
        },
    )
    assert r_tras.status_code == 201, r_tras.text

    # 2) Registrar un gasto IMSS ($1,000) y un gasto Especial ($500) separados
    for rubro, circ, monto in [
        ("MANO_OBRA_IMSS", "IMSS_MERQRY", 1000.00),
        ("MANO_OBRA_ESPECIAL", "ESPECIAL_CONTABILIDAD", 500.00),
    ]:
        rg = await async_client.post(
            "/api/v1/finanzas/gastos",
            headers=h,
            json={
                "empresa_id": nfa_id,
                "fecha": "2026-11-20",
                "periodo_clave": "2026-S47",
                "rubro": rubro,
                "circuito_origen": circ,
                "concepto": f"Gasto {rubro}",
                "monto": monto,
            },
        )
        assert rg.status_code == 201, rg.text

    # 3) Generar conciliacion operativa multi-etapa
    r_con = await async_client.post(
        "/api/v1/finanzas/conciliaciones",
        headers=h,
        json={"empresa_id": nfa_id, "fecha_inicio": "2026-11-16", "fecha_fin": "2026-11-22"},
    )
    assert r_con.status_code == 201, r_con.text
    con = r_con.json()
    assert con["cajas_campo_exportacion"] == 20.0
    assert con["cajas_trasladadas_empaque"] == 18.0
    assert con["delta_cajas_campo_vs_empaque"] == 2.0
    assert con["total_mo_imss_merqry"] == 1000.0
    assert con["total_mo_especial_contabilidad"] == 500.0
    assert con["costo_mo_por_caja_exportable"] == 75.0  # (1000+500)/20
    assert len(con["hash_conciliacion_sha256"]) == 64

    cid = con["id"]

    # 4) Transicion BORRADOR -> CONCILIADA -> CERRADA_AUDITORIA y bloqueo 409 inmutable
    r_t1 = await async_client.patch(
        f"/api/v1/finanzas/conciliaciones/{cid}/transicion",
        headers=h,
        json={"nuevo_estatus": "CONCILIADA"},
    )
    assert r_t1.status_code == 200 and r_t1.json()["estatus"] == "CONCILIADA"

    r_t2 = await async_client.patch(
        f"/api/v1/finanzas/conciliaciones/{cid}/transicion",
        headers=h,
        json={"nuevo_estatus": "CERRADA_AUDITORIA"},
    )
    assert r_t2.status_code == 200 and r_t2.json()["estatus"] == "CERRADA_AUDITORIA"

    r_t3 = await async_client.patch(
        f"/api/v1/finanzas/conciliaciones/{cid}/transicion",
        headers=h,
        json={"nuevo_estatus": "CONCILIADA"},
    )
    assert r_t3.status_code == 409
    assert r_t3.json()["detail"]["code"] == "CONCILIACION_INMUTABLE"

    # 5) Reporte ejecutivo y explorador de auditoria
    r_rep = await async_client.get(
        f"/api/v1/finanzas/reportes/ejecutivo?empresa_id={nfa_id}&fecha_inicio=2026-11-16&fecha_fin=2026-11-22&periodo_clave=2026-S47",
        headers=h,
    )
    assert r_rep.status_code == 200, r_rep.text
    rep = r_rep.json()
    assert rep["kpis_operativos"]["delta_cajas_campo_vs_empaque"] == 2.0
    assert rep["kpis_financieros_separados"]["mano_obra_imss_merqry"] == 1000.0
    assert rep["kpis_financieros_separados"]["mano_obra_especial_contabilidad"] == 500.0

    r_aud = await async_client.get(
        f"/api/v1/finanzas/auditoria/eventos?empresa_id={nfa_id}&modulo=finanzas_auditoria",
        headers=h,
    )
    assert r_aud.status_code == 200 and r_aud.json()["total_eventos"] >= 3

    # 6) Integridad SHA-256: OK antes de alteracion, TAMPER_DETECTED si se altera en BD
    r_int_ok = await async_client.get(
        f"/api/v1/finanzas/auditoria/integridad?empresa_id={nfa_id}",
        headers=h,
    )
    assert r_int_ok.status_code == 200
    assert r_int_ok.json()["estado_global"] == "INTEGRIDAD_OK"

    # Simular alteracion maliciosa directa en BD fuera de flujo
    await db_session.execute(
        text(
            "UPDATE fin_conciliaciones_operativas "
            "SET total_mo_especial_contabilidad = 9999.00 "
            "WHERE id = CAST(:cid AS UUID)"
        ),
        {"cid": cid},
    )
    await db_session.commit()

    r_int_bad = await async_client.get(
        f"/api/v1/finanzas/auditoria/integridad?empresa_id={nfa_id}",
        headers=h,
    )
    assert r_int_bad.status_code == 200
    assert r_int_bad.json()["estado_global"] == "TAMPER_DETECTED"
    assert r_int_bad.json()["alteraciones_detectadas"] == 1
