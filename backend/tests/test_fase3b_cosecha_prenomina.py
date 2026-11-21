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


async def _nfa_ctx(db: AsyncSession) -> dict:
    emp_id = (await db.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()
    suc_id = (await db.execute(text("SELECT id FROM sucursales WHERE clave = 'NFA-MATRIZ'"))).scalar()
    uo_framb = (await db.execute(text("SELECT id FROM unidades_operativas WHERE clave = 'NFA-UO-FRAMB'"))).scalar()
    uo_fresa = (await db.execute(text("SELECT id FROM unidades_operativas WHERE clave = 'NFA-UO-FRESA'"))).scalar()
    lote_framb = (await db.execute(text("SELECT id FROM lotes_produccion WHERE codigo_lote = 'NFA-FRAMB-M01'"))).scalar()
    lote_fresa = (await db.execute(text("SELECT id FROM lotes_produccion WHERE codigo_lote = 'NFA-FRESA-M21'"))).scalar()
    rel = (
        await db.execute(
            text(
                """
                SELECT rl.id::text AS rel_id, rl.persona_id::text AS persona_id
                FROM relaciones_laborales rl
                WHERE rl.numero_empleado = 'EMP-2001'
                """
            )
        )
    ).first()
    puesto_id = (await db.execute(text("SELECT id FROM puestos WHERE codigo_puesto = 'COSECHADOR'"))).scalar()
    return {
        "empresa_id": emp_id,
        "sucursal_id": suc_id,
        "uo_framb": uo_framb,
        "uo_fresa": uo_fresa,
        "lote_framb": lote_framb,
        "lote_fresa": lote_fresa,
        "persona_id": rel.persona_id,
        "rel_id": rel.rel_id,
        "puesto_id": puesto_id,
    }


@pytest.mark.asyncio
async def test_cosecha_culturales_movilidad_separada_y_cierres_concurrentes(
    async_client: AsyncClient, db_session: AsyncSession
):
    ctx = await _nfa_ctx(db_session)
    sup = await _login(async_client, "sup.framb", "SupFramb2026!")
    adm = await _login(async_client, "admin.dir", "AdminBerries2026!")
    sup_h = _auth(sup["access_token"])
    adm_h = _auth(adm["access_token"])

    lunes = "2026-11-16"

    # 1) Captura RETROACTIVA sin autorizacion -> 409
    r_no_aut = await async_client.post(
        "/api/v1/cosecha/capturas",
        headers=sup_h,
        json={
            "fecha": lunes,
            "lote_id": ctx["lote_framb"],
            "persona_id": ctx["persona_id"],
            "relacion_laboral_id": ctx["rel_id"],
            "modo_captura": "RETROACTIVA",
            "codigo_trazabilidad_caja": "BOX-RETRO-NOAUT",
            "cajas_exportacion": 10,
        },
    )
    assert r_no_aut.status_code == 409

    # Crear autorizacion y capturar con idempotencia + alerta merma > 7% (10% merma)
    r_aut = await async_client.post(
        "/api/v1/cosecha/autorizaciones",
        headers=sup_h,
        json={
            "empresa_id": ctx["empresa_id"],
            "sucursal_id": ctx["sucursal_id"],
            "unidad_operativa_id": ctx["uo_framb"],
            "fecha": lunes,
            "tipo_operacion": "COSECHA_RETROACTIVA",
            "motivo": "Regularización por pérdida de batería tablet",
        },
    )
    assert r_aut.status_code == 201
    aut_id = r_aut.json()["id"]

    cmd_cap = str(uuid.uuid4())
    cap_payload = {
        "client_command_id": cmd_cap,
        "fecha": lunes,
        "lote_id": ctx["lote_framb"],
        "persona_id": ctx["persona_id"],
        "relacion_laboral_id": ctx["rel_id"],
        "modo_captura": "RETROACTIVA",
        "autorizacion_id": aut_id,
        "codigo_trazabilidad_caja": "BOX-3B-001",
        "cajas_exportacion": 18,
        "cajas_nacional": 0,
        "cajas_merma_rezaga": 2,
        "nip_confirmado": True,
    }
    r_cap = await async_client.post("/api/v1/cosecha/capturas", headers=sup_h, json=cap_payload)
    assert r_cap.status_code == 201, r_cap.text
    assert r_cap.json()["alerta_merma_7pct"] is True
    assert r_cap.json()["estatus_flujo"] == "CAPTURADA"

    # Reintento idempotente -> mismo id, idempotent_replay=True
    r_rep = await async_client.post("/api/v1/cosecha/capturas", headers=sup_h, json=cap_payload)
    assert r_rep.status_code == 201
    assert r_rep.json()["idempotent_replay"] is True

    # 2) Labor cultural individual diaria
    r_cult = await async_client.post(
        "/api/v1/cosecha/culturales",
        headers=sup_h,
        json={
            "client_command_id": str(uuid.uuid4()),
            "fecha": lunes,
            "lote_id": ctx["lote_framb"],
            "persona_id": ctx["persona_id"],
            "relacion_laboral_id": ctx["rel_id"],
            "labor_codigo": "PODA",
            "unidad_medida": "SURCO",
            "meta_diaria": 6,
            "cantidad_realizada": 8,
            "minutos_trabajados": 360,
            "minutos_pausa": 30,
        },
    )
    assert r_cult.status_code == 201
    assert r_cult.json()["formula_pago_aplicable"] == "PENDIENTE_FORMULA_DIRECCION"

    # 3) Separacion estricta: movilidad de personas vs traslado de cajas
    r_mov = await async_client.post(
        "/api/v1/cosecha/movilidad-personas",
        headers=sup_h,
        json={
            "persona_id": ctx["persona_id"],
            "relacion_laboral_id": ctx["rel_id"],
            "fecha": lunes,
            "unidad_origen_id": ctx["uo_framb"],
            "lote_origen_id": ctx["lote_framb"],
            "unidad_destino_id": ctx["uo_fresa"],
            "lote_destino_id": ctx["lote_fresa"],
            "motivo": "Apoyo vespertino en Fresa M21",
        },
    )
    assert r_mov.status_code == 201
    mov_id = r_mov.json()["id"]
    for est in ("SALIDA", "TRASLADO_AUTORIZADO", "NUEVA_ASIGNACION"):
        assert (
            await async_client.patch(
                f"/api/v1/cosecha/movilidad-personas/{mov_id}/avanzar",
                headers=sup_h,
                json={"nuevo_estatus": est},
            )
        ).status_code == 200

    r_tc = await async_client.post(
        "/api/v1/cosecha/traslados-cajas",
        headers=sup_h,
        json={
            "fecha": lunes,
            "lote_origen_id": ctx["lote_framb"],
            "folio_remision": "REM-3B-001",
            "cantidad_cajas": 18,
            "calidad_fruta": "EXPORTACION",
            "destino_empaque": "Cuarto Frío Principal NFA",
            "vehiculo_clave": "ISUZU-01",
        },
    )
    assert r_tc.status_code == 201
    tc_id = r_tc.json()["id"]
    for est in ("TRASLADO", "RECEPCION_EMPAQUE", "EMPACADO", "DESPACHO"):
        assert (
            await async_client.patch(
                f"/api/v1/cosecha/traslados-cajas/{tc_id}/avanzar",
                headers=sup_h,
                json={"nuevo_estatus": est},
            )
        ).status_code == 200

    # 4) Matriz de cierres: cierre por UNIDAD -> bloquea nuevas capturas en esa unidad
    r_cu = await async_client.post(
        "/api/v1/cosecha/cierres",
        headers=sup_h,
        json={
            "empresa_id": ctx["empresa_id"],
            "sucursal_id": ctx["sucursal_id"],
            "unidad_operativa_id": ctx["uo_framb"],
            "fecha": lunes,
            "alcance_cierre": "UNIDAD",
        },
    )
    assert r_cu.status_code == 201, r_cu.text
    assert r_cu.json()["es_pagable"] is False

    # Captura tras cierre de unidad -> 409 PERIOD_CLOSED_FOR_CAPTURE
    r_after = await async_client.post(
        "/api/v1/cosecha/capturas",
        headers=sup_h,
        json={
            "fecha": lunes,
            "lote_id": ctx["lote_framb"],
            "persona_id": ctx["persona_id"],
            "relacion_laboral_id": ctx["rel_id"],
            "codigo_trazabilidad_caja": "BOX-LATE-001",
            "cajas_exportacion": 5,
        },
    )
    assert r_after.status_code == 409
    assert r_after.json()["detail"]["code"] == "PERIOD_CLOSED_FOR_CAPTURE"

    # Cierre GLOBAL por admin (L4) -> permitido tras cierre de unidad; segundo cierre global -> 409!
    r_cg1 = await async_client.post(
        "/api/v1/cosecha/cierres",
        headers=adm_h,
        json={"empresa_id": ctx["empresa_id"], "fecha": lunes, "alcance_cierre": "GLOBAL"},
    )
    assert r_cg1.status_code == 201

    r_cg2 = await async_client.post(
        "/api/v1/cosecha/cierres",
        headers=adm_h,
        json={"empresa_id": ctx["empresa_id"], "fecha": lunes, "alcance_cierre": "GLOBAL"},
    )
    assert r_cg2.status_code == 409
    assert r_cg2.json()["detail"]["code"] == "GLOBAL_CLOSE_ALREADY_EXISTS"

    # Cierre de otra unidad tras cierre GLOBAL -> 409 ALREADY_CLOSED_BY_GLOBAL
    r_cu2 = await async_client.post(
        "/api/v1/cosecha/cierres",
        headers=adm_h,
        json={
            "empresa_id": ctx["empresa_id"],
            "sucursal_id": ctx["sucursal_id"],
            "unidad_operativa_id": ctx["uo_fresa"],
            "fecha": lunes,
            "alcance_cierre": "UNIDAD",
        },
    )
    assert r_cu2.status_code == 409
    assert r_cu2.json()["detail"]["code"] == "ALREADY_CLOSED_BY_GLOBAL"

    # Cuadro de Honor y Mi Consulta
    r_ch = await async_client.get(
        f"/api/v1/cosecha/cuadro-honor?empresa_id={ctx['empresa_id']}&fecha_inicio={lunes}&fecha_fin={lunes}",
        headers=sup_h,
    )
    assert r_ch.status_code == 200
    assert len(r_ch.json()["ranking"]) >= 1

    r_mc = await async_client.get(
        f"/api/v1/cosecha/mi-consulta/{ctx['persona_id']}?fecha_inicio={lunes}&fecha_fin={lunes}",
        headers=sup_h,
    )
    assert r_mc.status_code == 200
    assert len(r_mc.json()["cosecha"]) == 1
    assert len(r_mc.json()["culturales"]) == 1


@pytest.mark.asyncio
async def test_prenomina_semanal_ls_domingo_escalonado_minimo_2350_inmutable_y_circuitos(
    async_client: AsyncClient, db_session: AsyncSession
):
    ctx = await _nfa_ctx(db_session)
    sup = await _login(async_client, "sup.framb", "SupFramb2026!")
    rh = await _login(async_client, "rh.nfa", "RhNfa2026!")
    sup_h = _auth(sup["access_token"])
    rh_h = _auth(rh["access_token"])

    # Crear segundo trabajador en circuito ESPECIAL_CONTABILIDAD
    r_p2 = await async_client.post(
        "/api/v1/identidad/personas",
        headers=rh_h,
        json={
            "curp": "TEST940610HHGESP3B",
            "nombre": "Mateo",
            "apellido_paterno": "Flores",
            "empresa_id": ctx["empresa_id"],
        },
    )
    assert r_p2.status_code == 201
    p2_id = r_p2.json()["id"]

    r_r2 = await async_client.post(
        "/api/v1/identidad/relaciones",
        headers=rh_h,
        json={
            "persona_id": p2_id,
            "empresa_id": ctx["empresa_id"],
            "sucursal_id": ctx["sucursal_id"],
            "unidad_operativa_id": ctx["uo_framb"],
            "numero_empleado": "TEST-3B-ESP",
            "circuito_pago": "ESPECIAL_CONTABILIDAD",
            "puesto_nominal_id": ctx["puesto_id"],
            "fecha_ingreso": "2026-01-05",
        },
    )
    assert r_r2.status_code == 201
    r2_id = r_r2.json()["id"]

    # Semana 47 (2026-11-16 lunes a 2026-11-22 domingo)
    lunes = "2026-11-16"
    domingo = "2026-11-22"

    # EMP-2001 (IMSS_MERQRY): 90 cajas lunes ($2,520) + 15 cajas domingo (10*$28 + 5*$40 = $480) = $3,000.00
    c1 = await async_client.post(
        "/api/v1/cosecha/capturas",
        headers=sup_h,
        json={
            "fecha": lunes,
            "lote_id": ctx["lote_framb"],
            "persona_id": ctx["persona_id"],
            "relacion_laboral_id": ctx["rel_id"],
            "codigo_trazabilidad_caja": "BOX-SEM47-LS-1",
            "cajas_exportacion": 90,
        },
    )
    assert c1.status_code == 201

    c2 = await async_client.post(
        "/api/v1/cosecha/capturas",
        headers=sup_h,
        json={
            "fecha": domingo,
            "lote_id": ctx["lote_framb"],
            "persona_id": ctx["persona_id"],
            "relacion_laboral_id": ctx["rel_id"],
            "codigo_trazabilidad_caja": "BOX-SEM47-DOM-1",
            "cajas_exportacion": 15,
        },
    )
    assert c2.status_code == 201

    # TEST-3B-ESP (ESPECIAL_CONTABILIDAD): 30 cajas lunes ($840) -> minimo garantizado $2,350 (ajuste $1,510)
    c3 = await async_client.post(
        "/api/v1/cosecha/capturas",
        headers=sup_h,
        json={
            "fecha": lunes,
            "lote_id": ctx["lote_framb"],
            "persona_id": p2_id,
            "relacion_laboral_id": r2_id,
            "codigo_trazabilidad_caja": "BOX-SEM47-LS-2",
            "cajas_exportacion": 30,
        },
    )
    assert c3.status_code == 201

    # Cierres tecnicos de lunes y domingo (aun NO autorizados por oficina)
    for f in (lunes, domingo):
        assert (
            await async_client.post(
                "/api/v1/cosecha/cierres",
                headers=sup_h,
                json={
                    "empresa_id": ctx["empresa_id"],
                    "sucursal_id": ctx["sucursal_id"],
                    "unidad_operativa_id": ctx["uo_framb"],
                    "fecha": f,
                    "alcance_cierre": "UNIDAD",
                },
            )
        ).status_code == 201

    # Intentar generar prenomina ANTES de revision de oficina -> 409 SIN_CAPTURAS_AUTORIZADAS
    r_pre_early = await async_client.post(
        "/api/v1/prenomina/semanal/generar",
        headers=rh_h,
        json={
            "empresa_id": ctx["empresa_id"],
            "anio": 2026,
            "semana_seah": 47,
            "fecha_inicio": lunes,
            "fecha_fin": domingo,
        },
    )
    assert r_pre_early.status_code == 409

    # Revision de oficina (L3 RH): CIERRE_TECNICO -> AUTORIZADA
    r_rev = await async_client.post(
        "/api/v1/cosecha/capturas/revisar-oficina",
        headers=rh_h,
        json={
            "empresa_id": ctx["empresa_id"],
            "captura_ids": [c1.json()["id"], c2.json()["id"], c3.json()["id"]],
            "nuevo_estatus": "AUTORIZADA",
        },
    )
    assert r_rev.status_code == 200

    # Generar prenomina semanal
    r_pre = await async_client.post(
        "/api/v1/prenomina/semanal/generar",
        headers=rh_h,
        json={
            "empresa_id": ctx["empresa_id"],
            "anio": 2026,
            "semana_seah": 47,
            "fecha_inicio": lunes,
            "fecha_fin": domingo,
        },
    )
    assert r_pre.status_code == 201, r_pre.text
    pre = r_pre.json()
    pre_id = pre["prenomina_id"]
    assert pre["total_imss_merqry"] == pytest.approx(3000.00, abs=0.01)
    assert pre["total_especial_contabilidad"] == pytest.approx(2350.00, abs=0.01)
    assert pre["total_general"] == pytest.approx(5350.00, abs=0.01)

    # Verificar separacion de circuitos en consulta
    r_get = await async_client.get(f"/api/v1/prenomina/semanal/{pre_id}", headers=rh_h)
    assert r_get.status_code == 200
    assert len(r_get.json()["imss_merqry"]) == 1
    assert len(r_get.json()["especial_contabilidad"]) == 1
    assert float(r_get.json()["especial_contabilidad"][0]["ajuste_minimo_semanal"]) == pytest.approx(1510.00, abs=0.01)

    # Transiciones: EN_REVISION -> AUTORIZADA -> PAGABLE (cierre inmutable con SHA-256) -> EXPORTADA -> RECIBIDA
    assert (
        await async_client.patch(
            f"/api/v1/prenomina/semanal/{pre_id}/transicion", headers=rh_h, json={"nuevo_estatus": "AUTORIZADA"}
        )
    ).status_code == 200

    r_pag = await async_client.patch(
        f"/api/v1/prenomina/semanal/{pre_id}/transicion", headers=rh_h, json={"nuevo_estatus": "PAGABLE"}
    )
    assert r_pag.status_code == 200
    assert len(r_pag.json()["hash_cierre_inmutable"]) == 64

    # Intentar recalcular tras cierre inmutable -> 409 PRENOMINA_INMUTABLE
    r_immut = await async_client.post(
        "/api/v1/prenomina/semanal/generar",
        headers=rh_h,
        json={
            "empresa_id": ctx["empresa_id"],
            "anio": 2026,
            "semana_seah": 47,
            "fecha_inicio": lunes,
            "fecha_fin": domingo,
        },
    )
    assert r_immut.status_code == 409
    assert r_immut.json()["detail"]["code"] == "PRENOMINA_INMUTABLE"

    # Completar cadena EXPORTADA -> RECIBIDA
    assert (
        await async_client.patch(
            f"/api/v1/prenomina/semanal/{pre_id}/transicion", headers=rh_h, json={"nuevo_estatus": "EXPORTADA"}
        )
    ).status_code == 200
    assert (
        await async_client.patch(
            f"/api/v1/prenomina/semanal/{pre_id}/transicion", headers=rh_h, json={"nuevo_estatus": "RECIBIDA"}
        )
    ).status_code == 200
