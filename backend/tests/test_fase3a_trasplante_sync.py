from datetime import date
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


async def _get_nfa_context(db: AsyncSession) -> dict:
    emp_id = (await db.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()
    suc_id = (await db.execute(text("SELECT id FROM sucursales WHERE clave = 'NFA-MATRIZ'"))).scalar()
    uo_id = (await db.execute(text("SELECT id FROM unidades_operativas WHERE clave = 'NFA-UO-FRAMB'"))).scalar()
    lote_id = (await db.execute(text("SELECT id FROM lotes_produccion WHERE codigo_lote = 'NFA-FRAMB-M01'"))).scalar()
    var_id = (await db.execute(text("SELECT id FROM variedades_cultivo WHERE codigo = 'FRAMB-DJ-LC'"))).scalar()
    p1 = (await db.execute(text("SELECT id::text FROM personas WHERE curp = 'COSL950515MHG00202'"))).scalar()
    p2 = (await db.execute(text("SELECT id::text FROM personas WHERE curp = 'INGT880320HHG00303'"))).scalar()
    p3 = (await db.execute(text("SELECT id::text FROM personas WHERE curp = 'SUPC900101HHG00101'"))).scalar()
    return {
        "empresa_id": emp_id,
        "sucursal_id": suc_id,
        "unidad_operativa_id": uo_id,
        "lote_id": lote_id,
        "variedad_id": var_id,
        "p1": p1,
        "p2": p2,
        "p3": p3,
    }


@pytest.mark.asyncio
async def test_daily_eligible_worker_privacidad_y_ttl(async_client: AsyncClient):
    sup = await _login(async_client, "sup.framb", "SupFramb2026!")
    resp = await async_client.get(
        "/api/v1/campo/eligibility/daily",
        headers=_auth(sup["access_token"]),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["contract_version"] == "DailyEligibleWorker.v0.1"
    assert body["ttl_seconds"] == 12 * 3600
    assert body["expires_at"] > body["generated_at"]
    assert len(body["workers"]) >= 3

    # Privacidad estricta RH -> Campo: cero campos sensibles o salariales
    forbidden = {
        "curp",
        "rfc",
        "nss",
        "salario_diario_pactado",
        "cuenta_bancaria_clabe",
        "banco",
        "telefono",
        "email",
        "circuito_pago",
    }
    for w in body["workers"]:
        assert forbidden.isdisjoint(set(w.keys()))
        assert "TRASPLANTE" in w["operaciones_autorizadas"]


@pytest.mark.asyncio
async def test_idempotencia_ack_perdido_409_payload_distinto_y_durable_command_fence(
    async_client: AsyncClient, db_session: AsyncSession
):
    ctx = await _get_nfa_context(db_session)
    sup = await _login(async_client, "sup.framb", "SupFramb2026!")
    headers = _auth(sup["access_token"])

    cmd_id = str(uuid.uuid4())
    payload = {
        "client_command_id": cmd_id,
        "empresa_id": ctx["empresa_id"],
        "sucursal_id": ctx["sucursal_id"],
        "unidad_operativa_id": ctx["unidad_operativa_id"],
        "codigo_camion": "CAM-IDEMP-01",
        "proveedor": "Mastronardi / Vivero",
        "variedad_id": ctx["variedad_id"],
        "cajas_plasticas_recibidas": 26,
    }

    # 1) Primera ejecucion
    r1 = await async_client.post("/api/v1/trasplante/camiones/declare", headers=headers, json=payload)
    assert r1.status_code == 201, r1.text
    b1 = r1.json()
    assert b1["committed_ack"] is True
    assert b1["idempotent_replay"] is False

    # 2) Reintento identico (ACK perdido) -> recupera committed_ack original sin duplicar
    r2 = await async_client.post("/api/v1/trasplante/camiones/declare", headers=headers, json=payload)
    assert r2.status_code == 201
    b2 = r2.json()
    assert b2["id"] == b1["id"]
    assert b2["idempotent_replay"] is True

    # 3) Mismo client_command_id con payload distinto -> 409 IDEMPOTENCY_PAYLOAD_MISMATCH
    bad_payload = {**payload, "codigo_camion": "CAM-DISTINTO-99"}
    r3 = await async_client.post("/api/v1/trasplante/camiones/declare", headers=headers, json=bad_payload)
    assert r3.status_code == 409
    assert r3.json()["detail"]["code"] == "IDEMPOTENCY_PAYLOAD_MISMATCH"

    # 4) Consulta de comando ausente -> ABSENCE_OBSERVED
    pending_cmd = str(uuid.uuid4())
    r_abs = await async_client.get(f"/api/v1/sync/commands/{pending_cmd}", headers=headers)
    assert r_abs.status_code == 200
    assert r_abs.json()["status"] == "ABSENCE_OBSERVED"

    # 5) DURABLE_COMMAND_FENCE -> NOT_APPLIED_VERIFIED y bloquea entrega tardia
    r_fence = await async_client.post(
        "/api/v1/sync/fences",
        headers=headers,
        json={
            "client_command_id": pending_cmd,
            "empresa_id": ctx["empresa_id"],
            "sucursal_id": ctx["sucursal_id"],
            "unidad_operativa_id": ctx["unidad_operativa_id"],
            "motivo": "Tablet reemplazada antes de sincronizar",
        },
    )
    assert r_fence.status_code == 201, r_fence.text
    assert r_fence.json()["status"] == "NOT_APPLIED_VERIFIED"

    r_late = await async_client.post(
        "/api/v1/trasplante/camiones/declare",
        headers=headers,
        json={**payload, "client_command_id": pending_cmd, "codigo_camion": "CAM-TARDIO-02"},
    )
    assert r_late.status_code == 409
    assert r_late.json()["detail"]["code"] == "COMMAND_FENCED_NOT_APPLIED"


@pytest.mark.asyncio
async def test_programacion_documental_y_documentary_truck_final_v1(
    async_client: AsyncClient, db_session: AsyncSession
):
    ctx = await _get_nfa_context(db_session)
    admin = await _login(async_client, "admin.dir", "AdminBerries2026!")
    sup = await _login(async_client, "sup.framb", "SupFramb2026!")
    adm_h = _auth(admin["access_token"])
    sup_h = _auth(sup["access_token"])

    # 1) Programacion documental (no promueve a stock; conserva unidad CANES sin conversion)
    r_plan = await async_client.post(
        "/api/v1/trasplante/programacion",
        headers=adm_h,
        json={
            "empresa_id": ctx["empresa_id"],
            "sucursal_id": ctx["sucursal_id"],
            "unidad_operativa_id": ctx["unidad_operativa_id"],
            "orden_compra_ref": "MPL-260100",
            "numero_camion_plan": 1,
            "proveedor": "Mastronardi Produce Limited",
            "variedad_id": ctx["variedad_id"],
            "unidad_planta": "CANES",
            "cantidad_documental": 20800,
            "bins_esperados": 26,
            "cajas_plasticas_retornables_esperadas": 26,
            "fecha_arribo_estimada": date.today().isoformat(),
            "fuente_documental": "OC #260100 firmada 02/11/2026",
        },
    )
    assert r_plan.status_code == 201, r_plan.text
    plan_id = r_plan.json()["id"]
    assert r_plan.json()["promovido_a_stock"] is False

    # Editar plan -> incrementa plan_version e invalida mapping
    r_edit = await async_client.patch(
        f"/api/v1/trasplante/programacion/{plan_id}",
        headers=adm_h,
        json={"cantidad_documental": 20000},
    )
    assert r_edit.status_code == 200
    assert r_edit.json()["plan_version"] == 2
    assert r_edit.json()["mapping_invalidado"] is True

    # 2) DECLARE_TRUCK -> verified=False
    r_decl = await async_client.post(
        "/api/v1/trasplante/camiones/declare",
        headers=sup_h,
        json={
            "empresa_id": ctx["empresa_id"],
            "sucursal_id": ctx["sucursal_id"],
            "unidad_operativa_id": ctx["unidad_operativa_id"],
            "programacion_id": plan_id,
            "codigo_camion": "CAM-DOC-01",
            "proveedor": "Mastronardi Produce Limited",
            "variedad_id": ctx["variedad_id"],
            "cajas_plasticas_recibidas": 26,
        },
    )
    assert r_decl.status_code == 201
    cam_id = r_decl.json()["id"]
    assert r_decl.json()["verified"] is False

    # 3) BIN_RECEIVE -> cantidad_rechazada DEBE ser NULL y stock disponible = 0 hasta BIN_RELEASE
    r_bin = await async_client.post(
        f"/api/v1/trasplante/camiones/{cam_id}/bins/receive",
        headers=sup_h,
        json={"bin_code": "BIN-01", "unidad_planta": "CANES", "cantidad_recibida": 800},
    )
    assert r_bin.status_code == 201
    bin_id = r_bin.json()["id"]
    assert r_bin.json()["cantidad_rechazada"] is None
    assert r_bin.json()["stock_disponible"] == 0

    # Intentar asignar TRANSPLANT antes de BIN_RELEASE -> 409 BIN_SIN_STOCK_LIBERADO
    r_unrel = await async_client.post(
        "/api/v1/trasplante/asignaciones",
        headers=sup_h,
        json={
            "fecha": date.today().isoformat(),
            "camion_lote_id": cam_id,
            "bin_id": bin_id,
            "lote_id": ctx["lote_id"],
            "tunel_numero": 1,
            "equipo_lado": "NORTE",
            "linea_inicio": 1,
            "linea_fin": 5,
            "funcion_codigo": "TRANSPLANT",
            "participantes_persona_ids": [ctx["p1"]],
        },
    )
    assert r_unrel.status_code == 409

    # 4) BIN_RELEASE -> stock derivado = 750
    r_rel = await async_client.post(
        f"/api/v1/trasplante/bins/{bin_id}/release",
        headers=sup_h,
        json={"cantidad": 750},
    )
    assert r_rel.status_code == 200
    assert r_rel.json()["disponible"] == 750
    assert r_rel.json()["cantidad_rechazada"] is None

    # 5) FINISH_TRUCK + FINALIZE_RECEIPT (exige accepted + rejected == received)
    r_fin = await async_client.post(f"/api/v1/trasplante/camiones/{cam_id}/finish", headers=adm_h)
    assert r_fin.status_code == 200
    assert r_fin.json()["estatus"] == "FINISHED_OPERATIONAL"

    # Descuadre (750 + 40 != 800) -> 422
    r_bad_final = await async_client.post(
        f"/api/v1/trasplante/camiones/{cam_id}/finalize-receipt",
        headers=adm_h,
        json={"bins": [{"bin_id": bin_id, "cantidad_aceptada": 750, "cantidad_rechazada": 40}]},
    )
    assert r_bad_final.status_code == 422

    # Conciliacion exacta (750 + 50 == 800) -> FINALIZED y verified=True
    r_final = await async_client.post(
        f"/api/v1/trasplante/camiones/{cam_id}/finalize-receipt",
        headers=adm_h,
        json={
            "bins": [
                {
                    "bin_id": bin_id,
                    "cantidad_aceptada": 750,
                    "cantidad_rechazada": 50,
                    "motivo_rechazo": "1a merma caña rota al arribo",
                }
            ],
            "cajas_plasticas_devueltas": 26,
            "notas_cierre": "Conciliación documental-física completa",
        },
    )
    assert r_final.status_code == 200, r_final.text
    assert r_final.json()["estatus"] == "FINALIZED"
    assert r_final.json()["verified"] is True
    assert r_final.json()["bins"][0]["rejected"] == 50


@pytest.mark.asyncio
async def test_shared_trucks_multicamion_sin_doble_reserva_ni_solape_y_close_person_day(
    async_client: AsyncClient, db_session: AsyncSession
):
    ctx = await _get_nfa_context(db_session)
    sup = await _login(async_client, "sup.framb", "SupFramb2026!")
    h = _auth(sup["access_token"])
    hoy = date.today().isoformat()

    # Declarar, recibir y liberar 2 camiones simultaneos (CAM-A y CAM-B) para el mismo modulo compartido
    cam_ids = []
    bin_ids = []
    for code in ("CAM-MULTI-A", "CAM-MULTI-B"):
        rc = await async_client.post(
            "/api/v1/trasplante/camiones/declare",
            headers=h,
            json={
                "empresa_id": ctx["empresa_id"],
                "sucursal_id": ctx["sucursal_id"],
                "unidad_operativa_id": ctx["unidad_operativa_id"],
                "codigo_camion": code,
                "proveedor": "Mastronardi",
                "variedad_id": ctx["variedad_id"],
            },
        )
        assert rc.status_code == 201
        cid = rc.json()["id"]
        rb = await async_client.post(
            f"/api/v1/trasplante/camiones/{cid}/bins/receive",
            headers=h,
            json={"bin_code": f"B-{code}", "unidad_planta": "CANES", "cantidad_recibida": 800},
        )
        assert rb.status_code == 201
        bid = rb.json()["id"]
        rr = await async_client.post(
            f"/api/v1/trasplante/bins/{bid}/release",
            headers=h,
            json={"cantidad": 800},
        )
        assert rr.status_code == 200
        cam_ids.append(cid)
        bin_ids.append(bid)

    cam_a, cam_b = cam_ids
    bin_a, bin_b = bin_ids

    # 1) Asignar pareja (p1 + p2) en CAM-A, Tunel 1 NORTE lineas 1..10 (TRANSPLANT)
    ra1 = await async_client.post(
        "/api/v1/trasplante/asignaciones",
        headers=h,
        json={
            "fecha": hoy,
            "camion_lote_id": cam_a,
            "bin_id": bin_a,
            "lote_id": ctx["lote_id"],
            "tunel_numero": 1,
            "equipo_lado": "NORTE",
            "linea_inicio": 1,
            "linea_fin": 10,
            "funcion_codigo": "TRANSPLANT",
            "participantes_persona_ids": [ctx["p1"], ctx["p2"]],
        },
    )
    assert ra1.status_code == 201, ra1.text
    asig_a = ra1.json()["id"]

    # 2) Bloqueo de doble asignacion de p1 en CAM-B (sin revelar CAM-A en el error)
    ra_double = await async_client.post(
        "/api/v1/trasplante/asignaciones",
        headers=h,
        json={
            "fecha": hoy,
            "camion_lote_id": cam_b,
            "bin_id": bin_b,
            "lote_id": ctx["lote_id"],
            "tunel_numero": 2,
            "equipo_lado": "SUR",
            "linea_inicio": 1,
            "linea_fin": 5,
            "funcion_codigo": "TRANSPLANT",
            "participantes_persona_ids": [ctx["p1"]],
        },
    )
    assert ra_double.status_code == 409
    assert ra_double.json()["detail"]["code"] == "PERSON_ALREADY_ASSIGNED"
    assert "CAM-MULTI-A" not in str(ra_double.json())

    # 3) Bloqueo de solapamiento fisico de rango TRANSPLANT desde CAM-B con p3 (lineas 8..15 chocan con 1..10)
    ra_overlap = await async_client.post(
        "/api/v1/trasplante/asignaciones",
        headers=h,
        json={
            "fecha": hoy,
            "camion_lote_id": cam_b,
            "bin_id": bin_b,
            "lote_id": ctx["lote_id"],
            "tunel_numero": 1,
            "equipo_lado": "NORTE",
            "linea_inicio": 8,
            "linea_fin": 15,
            "funcion_codigo": "TRANSPLANT",
            "participantes_persona_ids": [ctx["p3"]],
        },
    )
    assert ra_overlap.status_code == 409
    assert ra_overlap.json()["detail"]["code"] == "LINE_RANGE_OVERLAP"

    # 4) Coexistencia de labor auxiliar CLIPS sobre mismo rango 1..10 con p3 -> SI permitida
    ra_clips = await async_client.post(
        "/api/v1/trasplante/asignaciones",
        headers=h,
        json={
            "fecha": hoy,
            "camion_lote_id": cam_b,
            "bin_id": bin_b,
            "lote_id": ctx["lote_id"],
            "tunel_numero": 1,
            "equipo_lado": "NORTE",
            "linea_inicio": 1,
            "linea_fin": 10,
            "funcion_codigo": "CLIPS",
            "participantes_persona_ids": [ctx["p3"]],
        },
    )
    assert ra_clips.status_code == 201
    asig_clips = ra_clips.json()["id"]

    # Pero intentar apropiarse del rango cambiando CLIPS -> TRANSPLANT via CHANGE_FUNCTION debe ser 409!
    r_steal = await async_client.patch(
        f"/api/v1/trasplante/asignaciones/{asig_clips}/estado",
        headers=h,
        json={"accion": "CHANGE_FUNCTION", "nueva_funcion_codigo": "TRANSPLANT"},
    )
    assert r_steal.status_code == 409
    assert r_steal.json()["detail"]["code"] == "LINE_RANGE_OVERLAP"

    # 5) Produccion compartida de pareja (350 CANES en lineas 1..5): sin multiplicar por 2 ni conversion de unidad
    r_bad_unit = await async_client.post(
        f"/api/v1/trasplante/asignaciones/{asig_a}/produccion",
        headers=h,
        json={"linea_inicio": 1, "linea_fin": 5, "unidad_planta": "PLANTS", "cantidad_trasplantada": 350},
    )
    assert r_bad_unit.status_code == 422

    r_prod = await async_client.post(
        f"/api/v1/trasplante/asignaciones/{asig_a}/produccion",
        headers=h,
        json={"linea_inicio": 1, "linea_fin": 5, "unidad_planta": "CANES", "cantidad_trasplantada": 350},
    )
    assert r_prod.status_code == 201
    assert r_prod.json()["cantidad_trasplantada"] == 350
    assert r_prod.json()["participantes_count"] == 2
    assert r_prod.json()["stock_restante_bin"] == 450

    # 6) CLOSE_PERSON_DAY bloqueado mientras asig_a siga abierta
    r_tok_open = await async_client.post(
        "/api/v1/trasplante/cierre-persona-dia/review-token",
        headers=h,
        json={"persona_id": ctx["p1"], "camion_lote_id": cam_a, "fecha": hoy},
    )
    assert r_tok_open.status_code == 200
    tok_stale = r_tok_open.json()["review_token"]

    r_close_open = await async_client.post(
        "/api/v1/trasplante/cierre-persona-dia/close",
        headers=h,
        json={"persona_id": ctx["p1"], "camion_lote_id": cam_a, "fecha": hoy, "review_token": tok_stale},
    )
    assert r_close_open.status_code == 409
    assert r_close_open.json()["detail"]["code"] == "OPEN_ASSIGNMENTS_EXIST"

    # 7) Pausar -> Reanudar -> Finalizar asig_a (genera multiples segmentos historicos)
    assert (
        await async_client.patch(
            f"/api/v1/trasplante/asignaciones/{asig_a}/estado", headers=h, json={"accion": "PAUSE"}
        )
    ).status_code == 200
    assert (
        await async_client.patch(
            f"/api/v1/trasplante/asignaciones/{asig_a}/estado", headers=h, json={"accion": "RESUME"}
        )
    ).status_code == 200
    assert (
        await async_client.patch(
            f"/api/v1/trasplante/asignaciones/{asig_a}/estado", headers=h, json={"accion": "FINISH"}
        )
    ).status_code == 200

    # Token viejo ahora es STALE_REVIEW_TOKEN porque asig_a cambio a FINISHED!
    r_stale = await async_client.post(
        "/api/v1/trasplante/cierre-persona-dia/close",
        headers=h,
        json={"persona_id": ctx["p1"], "camion_lote_id": cam_a, "fecha": hoy, "review_token": tok_stale},
    )
    assert r_stale.status_code == 409
    assert r_stale.json()["detail"]["code"] == "STALE_REVIEW_TOKEN"

    # Generar review_token fresco y cerrar persona-dia (es_pagable=False)
    r_tok_fresh = await async_client.post(
        "/api/v1/trasplante/cierre-persona-dia/review-token",
        headers=h,
        json={"persona_id": ctx["p1"], "camion_lote_id": cam_a, "fecha": hoy},
    )
    assert r_tok_fresh.status_code == 200
    r_closed = await async_client.post(
        "/api/v1/trasplante/cierre-persona-dia/close",
        headers=h,
        json={
            "persona_id": ctx["p1"],
            "camion_lote_id": cam_a,
            "fecha": hoy,
            "review_token": r_tok_fresh.json()["review_token"],
        },
    )
    assert r_closed.status_code == 200, r_closed.text
    assert r_closed.json()["es_pagable"] is False
    assert r_closed.json()["total_plantas_equipo"] == 350

    # 8) crossBatchContinuationOf: continuar subrango pendiente 6..10 en CAM-B desde asig_a FINISHED
    # Primero validar que pisar linea 5 (ya terminada) falla:
    r_cont_bad = await async_client.post(
        "/api/v1/trasplante/asignaciones",
        headers=h,
        json={
            "fecha": hoy,
            "camion_lote_id": cam_b,
            "bin_id": bin_b,
            "lote_id": ctx["lote_id"],
            "tunel_numero": 1,
            "equipo_lado": "NORTE",
            "linea_inicio": 5,
            "linea_fin": 10,
            "funcion_codigo": "TRANSPLANT",
            "participantes_persona_ids": [ctx["p2"]],
            "cross_batch_continuation_of": asig_a,
        },
    )
    assert r_cont_bad.status_code == 409

    # Subrango pendiente exacto 6..10 -> permitido!
    r_cont_ok = await async_client.post(
        "/api/v1/trasplante/asignaciones",
        headers=h,
        json={
            "fecha": hoy,
            "camion_lote_id": cam_b,
            "bin_id": bin_b,
            "lote_id": ctx["lote_id"],
            "tunel_numero": 1,
            "equipo_lado": "NORTE",
            "linea_inicio": 6,
            "linea_fin": 10,
            "funcion_codigo": "TRANSPLANT",
            "participantes_persona_ids": [ctx["p2"]],
            "cross_batch_continuation_of": asig_a,
        },
    )
    assert r_cont_ok.status_code == 201, r_cont_ok.text
    assert r_cont_ok.json()["cross_batch_continuation_of"] == asig_a
