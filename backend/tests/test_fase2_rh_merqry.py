from datetime import date, timedelta

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


async def _nfa_ids(db: AsyncSession) -> dict:
    emp_id = (await db.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()
    suc_id = (await db.execute(text("SELECT id FROM sucursales WHERE clave = 'NFA-MATRIZ'"))).scalar()
    uo_id = (await db.execute(text("SELECT id FROM unidades_operativas WHERE clave = 'NFA-UO-FRAMB'"))).scalar()
    puesto_id = (await db.execute(text("SELECT id FROM puestos WHERE codigo_puesto = 'COSECHADOR'"))).scalar()
    return {"empresa_id": emp_id, "sucursal_id": suc_id, "unidad_operativa_id": uo_id, "puesto_id": puesto_id}


@pytest.mark.asyncio
async def test_flujo_completo_plaza_cobertura_vacante_ranking_dictamen_expediente_16_estados_y_finiquito(
    async_client: AsyncClient, db_session: AsyncSession
):
    ids = await _nfa_ids(db_session)
    rh = await _login(async_client, "rh.nfa", "RhNfa2026!")
    h = _auth(rh["access_token"])
    rh_uid = rh["usuario"]["usuario_id"]

    # 1) Crear plaza autorizada (cupo 2) y version de perfil
    r_plaza = await async_client.post(
        "/api/v1/reclutamiento/plazas",
        headers=h,
        json={
            "empresa_id": ids["empresa_id"],
            "sucursal_id": ids["sucursal_id"],
            "unidad_operativa_id": ids["unidad_operativa_id"],
            "puesto_id": ids["puesto_id"],
            "codigo_plaza": "PLZ-NFA-COS-2026",
            "headcount_autorizado": 2,
        },
    )
    assert r_plaza.status_code == 201, r_plaza.text
    plaza_id = r_plaza.json()["id"]

    r_perf = await async_client.post(
        "/api/v1/reclutamiento/perfiles",
        headers=h,
        json={
            "empresa_id": ids["empresa_id"],
            "puesto_id": ids["puesto_id"],
            "version_numero": 1,
            "titulo_perfil": "Cosechador Frambuesa Temporada 2026",
            "objetivo": "Corte y trasplante con inocuidad BPA",
        },
    )
    assert r_perf.status_code == 201
    perfil_id = r_perf.json()["id"]

    # Cobertura excediendo cupo -> 409
    r_over = await async_client.post(
        "/api/v1/reclutamiento/coberturas",
        headers=h,
        json={
            "plaza_autorizada_id": plaza_id,
            "perfil_version_id": perfil_id,
            "cantidad_solicitada": 5,
            "tipo_cobertura": "TEMPORADA",
            "justificacion": "Excede plaza autorizada",
        },
    )
    assert r_over.status_code == 409

    # Solicitud de cobertura valida (2 posiciones) -> PENDIENTE
    r_cob = await async_client.post(
        "/api/v1/reclutamiento/coberturas",
        headers=h,
        json={
            "plaza_autorizada_id": plaza_id,
            "perfil_version_id": perfil_id,
            "cantidad_solicitada": 2,
            "tipo_cobertura": "TEMPORADA",
            "justificacion": "Arranque cosecha Long Cane NFA",
        },
    )
    assert r_cob.status_code == 201
    cob_id = r_cob.json()["id"]

    # Intentar crear vacante sin aprobacion -> 409 COBERTURA_NO_APROBADA
    r_vac_block = await async_client.post(
        "/api/v1/reclutamiento/vacantes",
        headers=h,
        json={"solicitud_cobertura_id": cob_id, "codigo_vacante": "VAC-NFA-001", "canal_tipo": "COSECHA"},
    )
    assert r_vac_block.status_code == 409
    assert r_vac_block.json()["detail"]["code"] == "COBERTURA_NO_APROBADA"

    # Aprobar cobertura -> crear vacante -> publicar
    r_ap = await async_client.post(
        f"/api/v1/reclutamiento/coberturas/{cob_id}/decidir",
        headers=h,
        json={"decision": "APROBADA", "comentarios": "Aprobada por Jefatura RH"},
    )
    assert r_ap.status_code == 200

    r_vac = await async_client.post(
        "/api/v1/reclutamiento/vacantes",
        headers=h,
        json={"solicitud_cobertura_id": cob_id, "codigo_vacante": "VAC-NFA-001", "canal_tipo": "COSECHA"},
    )
    assert r_vac.status_code == 201
    vac_id = r_vac.json()["id"]

    r_pub = await async_client.post(
        f"/api/v1/reclutamiento/vacantes/{vac_id}/publicar",
        headers=h,
        json={"canal": "PORTAL_PUBLICO"},
    )
    assert r_pub.status_code == 201

    # Postulacion externo + postulacion interno (EMP-2001)
    r_post_int = await async_client.post(
        f"/api/v1/reclutamiento/vacantes/{vac_id}/postular",
        headers=h,
        json={
            "curp": "COSL950515MHG00202",
            "nombre": "Lucía",
            "apellido_paterno": "Hernández",
            "telefono": "7710001122",
        },
    )
    assert r_post_int.status_code == 201
    assert r_post_int.json()["categoria_candidato"] == "INTERNO"

    r_post = await async_client.post(
        f"/api/v1/reclutamiento/vacantes/{vac_id}/postular",
        headers=h,
        json={
            "curp": "F2RH960812HHGMRT01",
            "nombre": "Ana",
            "apellido_paterno": "Martínez",
            "apellido_materno": "Ruiz",
            "telefono": "7715554433",
        },
    )
    assert r_post.status_code == 201
    post_id = r_post.json()["id"]

    # Ranking 60/25/15: 80*0.60 + 90*0.25 + 70*0.15 = 81.00
    r_eval = await async_client.patch(
        f"/api/v1/reclutamiento/postulaciones/{post_id}/evaluar",
        headers=h,
        json={"score_evaluacion": 80, "score_entrevista": 90, "score_experiencia": 70},
    )
    assert r_eval.status_code == 200
    assert float(r_eval.json()["ranking_ponderado_60_25_15"]) == pytest.approx(81.0, abs=0.01)

    # Dictaminar + Traspaso formal a Personal (crea relacion + expediente PREALTA)
    r_dict = await async_client.post(
        f"/api/v1/reclutamiento/postulaciones/{post_id}/dictaminar",
        headers=h,
        json={
            "decision": "APROBADO_INGRESO",
            "justificacion": "Ranking superior a umbral minimo",
            "traspasar_a_personal": True,
            "numero_empleado": "RH2-3001",
            "circuito_pago": "IMSS_MERQRY",
            "fecha_ingreso": "2026-01-10",
        },
    )
    assert r_dict.status_code == 201, r_dict.text
    rel_id = r_dict.json()["traspasado_a_relacion_id"]
    exp_id = r_dict.json()["expediente_id"]

    # 2) Contrato: prohibida renuncia anticipada (422) y prohibido saltar VALIDADO (409)
    r_ren = await async_client.post(
        "/api/v1/personal/contratos",
        headers=h,
        json={
            "relacion_laboral_id": rel_id,
            "tipo_contrato": "TEMPORADA",
            "salario_diario": 350.0,
            "fecha_inicio": "2026-01-10",
            "incluye_renuncia_anticipada": True,
        },
    )
    assert r_ren.status_code == 422

    r_con = await async_client.post(
        "/api/v1/personal/contratos",
        headers=h,
        json={
            "relacion_laboral_id": rel_id,
            "tipo_contrato": "TEMPORADA",
            "salario_diario": 350.0,
            "fecha_inicio": "2026-01-10",
        },
    )
    assert r_con.status_code == 201
    con_id = r_con.json()["id"]

    # Saltar de BORRADOR a FIRMADO -> 409
    r_jump = await async_client.patch(
        f"/api/v1/personal/contratos/{con_id}/transicion",
        headers=h,
        json={"nuevo_estatus": "FIRMADO"},
    )
    assert r_jump.status_code == 409

    # BORRADOR -> VALIDADO -> FIRMADO
    assert (
        await async_client.patch(
            f"/api/v1/personal/contratos/{con_id}/transicion", headers=h, json={"nuevo_estatus": "VALIDADO"}
        )
    ).status_code == 200
    assert (
        await async_client.patch(
            f"/api/v1/personal/contratos/{con_id}/transicion", headers=h, json={"nuevo_estatus": "FIRMADO"}
        )
    ).status_code == 200

    # 3) Expediente 16 estados + UPDATE_READY excepcion vencida -> bloqueo automatico
    # Capacitacion solo impartida (no validada) -> 409 para LISTO_PARA_TRABAJAR
    r_cap_only = await async_client.patch(
        f"/api/v1/personal/expedientes/{exp_id}/avanzar",
        headers=h,
        json={"nuevo_estatus": "LISTO_PARA_TRABAJAR", "capacitacion_impartida": True, "capacitacion_validada": False},
    )
    assert r_cap_only.status_code == 409

    # Crear excepcion temporal ya vencida (ayer) -> debe bloquear automaticamente LISTO_PARA_TRABAJAR
    ayer = (date.today() - timedelta(days=1)).isoformat()
    r_exc = await async_client.post(
        f"/api/v1/personal/expedientes/{exp_id}/update-ready",
        headers=h,
        json={
            "nivel_accion": "EXCEPCION_TEMPORAL",
            "requisito_omitido": "EPP_CRITICO",
            "motivo": "Botas en tránsito de almacén",
            "responsable_usuario_id": rh_uid,
            "fecha_limite": ayer,
        },
    )
    assert r_exc.status_code == 201
    exc_id = r_exc.json()["id"]

    r_blocked = await async_client.patch(
        f"/api/v1/personal/expedientes/{exp_id}/avanzar",
        headers=h,
        json={"nuevo_estatus": "LISTO_PARA_TRABAJAR", "capacitacion_impartida": True, "capacitacion_validada": True},
    )
    assert r_blocked.status_code == 409
    assert r_blocked.json()["detail"]["code"] == "EXCEPCION_TEMPORAL_VENCIDA_BLOQUEO"

    # Resolver excepcion + entregar responsiva EPP critico -> avanza a LISTO_PARA_TRABAJAR
    assert (
        await async_client.patch(f"/api/v1/personal/update-ready/{exc_id}/resolver", headers=h)
    ).status_code == 200

    r_resp = await async_client.post(
        "/api/v1/personal/responsivas",
        headers=h,
        json={
            "relacion_laboral_id": rel_id,
            "tipo_responsiva": "EPP",
            "es_critico_operacion": True,
            "descripcion_items": [{"item": "Guantes y lentes BPA", "cantidad": 1}],
        },
    )
    assert r_resp.status_code == 201

    r_lpt = await async_client.patch(
        f"/api/v1/personal/expedientes/{exp_id}/avanzar",
        headers=h,
        json={
            "nuevo_estatus": "LISTO_PARA_TRABAJAR",
            "capacitacion_impartida": True,
            "capacitacion_validada": True,
            "alta_interna_completa": True,
        },
    )
    assert r_lpt.status_code == 200

    # Alta interna NO equivale a alta IMSS -> LISTO_MERQRY bloqueado hasta alta_imss_confirmada=True
    r_no_imss = await async_client.patch(
        f"/api/v1/personal/expedientes/{exp_id}/avanzar",
        headers=h,
        json={"nuevo_estatus": "LISTO_MERQRY", "alta_imss_confirmada": False},
    )
    assert r_no_imss.status_code == 409

    r_lm = await async_client.patch(
        f"/api/v1/personal/expedientes/{exp_id}/avanzar",
        headers=h,
        json={"nuevo_estatus": "LISTO_MERQRY", "alta_imss_confirmada": True},
    )
    assert r_lm.status_code == 200

    # 4) Beneficiarios Art. 501 (tope 100%)
    assert (
        await async_client.post(
            "/api/v1/personal/beneficiarios",
            headers=h,
            json={
                "relacion_laboral_id": rel_id,
                "nombre_completo": "María Ruiz",
                "parentesco": "MADRE",
                "porcentaje_asignado": 60.0,
            },
        )
    ).status_code == 201
    assert (
        await async_client.post(
            "/api/v1/personal/beneficiarios",
            headers=h,
            json={
                "relacion_laboral_id": rel_id,
                "nombre_completo": "José Martínez",
                "parentesco": "PADRE",
                "porcentaje_asignado": 50.0,
            },
        )
    ).status_code == 422

    # 5) Finiquito LFT 2026
    r_fin = await async_client.post(
        "/api/v1/personal/finiquitos",
        headers=h,
        json={
            "relacion_laboral_id": rel_id,
            "fecha_baja": "2026-07-10",
            "motivo_baja": "TERMINO_TEMPORADA",
            "salario_diario": 350.0,
            "dias_salarios_pendientes": 3,
            "aplicar_baja_expediente": True,
        },
    )
    assert r_fin.status_code == 201, r_fin.text
    fin = r_fin.json()
    assert fin["circuito_pago"] == "IMSS_MERQRY"
    assert float(fin["aguinaldo_proporcional"]) > 0
    assert float(fin["vacaciones_proporcionales"]) > 0
    assert float(fin["prima_vacacional"]) > 0
    assert float(fin["total_neto_finiquito"]) > 1050.0


@pytest.mark.asyncio
async def test_merqry_solo_lectura_y_separacion_estricta_imss_vs_especial_contabilidad(
    async_client: AsyncClient, db_session: AsyncSession
):
    ids = await _nfa_ids(db_session)
    rh = await _login(async_client, "rh.nfa", "RhNfa2026!")
    h = _auth(rh["access_token"])

    # 1) Guarda SQL solo lectura hacia Merqry: permite SELECT y bloquea cualquier escritura/DDL
    r_sel = await async_client.post(
        "/api/v1/merqry/validate-readonly-sql",
        headers=h,
        json={"sql": "SELECT id, nombre FROM contactopersonal LIMIT 5"},
    )
    assert r_sel.status_code == 200

    for bad_sql in [
        "UPDATE contactopersonal SET estatus = 'BAJA'",
        "DELETE FROM nominaprevio WHERE id = 1",
        "DROP TABLE auxiliar",
        "SELECT 1; DELETE FROM contactopersonal",
    ]:
        r_bad = await async_client.post(
            "/api/v1/merqry/validate-readonly-sql",
            headers=h,
            json={"sql": bad_sql},
        )
        assert r_bad.status_code == 403
        assert r_bad.json()["detail"]["code"] == "MERQRY_READONLY_VIOLATION"

    # 2) Crear empleado en circuito ESPECIAL_CONTABILIDAD y probar que NO puede pasar a LISTO_MERQRY
    r_per = await async_client.post(
        "/api/v1/identidad/personas",
        headers=h,
        json={
            "curp": "F2RH910215HHGESP02",
            "nombre": "Roberto",
            "apellido_paterno": "Sánchez",
            "empresa_id": ids["empresa_id"],
        },
    )
    assert r_per.status_code == 201
    per_id = r_per.json()["id"]

    r_rel = await async_client.post(
        "/api/v1/identidad/relaciones",
        headers=h,
        json={
            "persona_id": per_id,
            "empresa_id": ids["empresa_id"],
            "sucursal_id": ids["sucursal_id"],
            "unidad_operativa_id": ids["unidad_operativa_id"],
            "numero_empleado": "RH2-ESP-01",
            "circuito_pago": "ESPECIAL_CONTABILIDAD",
            "puesto_nominal_id": ids["puesto_id"],
            "fecha_ingreso": "2026-02-01",
        },
    )
    assert r_rel.status_code == 201
    rel_esp_id = r_rel.json()["id"]

    exp_esp_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO expedientes_personal (relacion_laboral_id, persona_id, empresa_id, estatus)
                VALUES (CAST(:rlid AS uuid), CAST(:pid AS uuid), :emp, 'LISTO_PARA_TRABAJAR')
                RETURNING id::text
                """
            ),
            {"rlid": rel_esp_id, "pid": per_id, "emp": ids["empresa_id"]},
        )
    ).scalar()
    await db_session.commit()

    # Intentar enviar empleado ESPECIAL a LISTO_MERQRY -> 409 SEPARACION_CIRCUITOS
    r_sep = await async_client.patch(
        f"/api/v1/personal/expedientes/{exp_esp_id}/avanzar",
        headers=h,
        json={"nuevo_estatus": "LISTO_MERQRY", "alta_imss_confirmada": True},
    )
    assert r_sep.status_code == 409

    # Si puede pasar a LISTO_PRENOMINA (para Contabilidad)
    r_pre = await async_client.patch(
        f"/api/v1/personal/expedientes/{exp_esp_id}/avanzar",
        headers=h,
        json={"nuevo_estatus": "LISTO_PRENOMINA"},
    )
    assert r_pre.status_code == 200

    # 3) Cargar snapshot READ-ONLY de Merqry y conciliar
    r_snap = await async_client.post(
        "/api/v1/merqry/staging/cargar-snapshot",
        headers=h,
        json={
            "empresa_id": ids["empresa_id"],
            "registros": [
                {
                    "merqry_employee_id": "MRQ-2001",
                    "curp": "COSL950515MHG00202",
                    "nombre_completo": "Lucía Hernández Cruz",
                    "puesto_nominal_merqry": "COSECHADOR",
                },
                {
                    "merqry_employee_id": "MRQ-SOLO-MERQRY",
                    "curp": "SOLO800101HHGXYZ99",
                    "nombre_completo": "Empleado Solo En Merqry",
                    "puesto_nominal_merqry": "OPERADOR",
                },
            ],
        },
    )
    assert r_snap.status_code == 201

    r_conc = await async_client.get(
        f"/api/v1/merqry/conciliacion?empresa_id={ids['empresa_id']}", headers=h
    )
    assert r_conc.status_code == 200
    conc = r_conc.json()
    assert conc["merqry_mode"] == "READ_ONLY"
    assert conc["resumen"]["conciliados_imss"] >= 1
    assert conc["resumen"]["falta_en_erp"] == 1
    assert conc["resumen"]["excluidos_especial_contabilidad"] == 1

    # 4) Exports estrictamente separados: IMSS -> Merqry vs Especial -> Contabilidad
    r_exp_imss = await async_client.post(
        "/api/v1/merqry/exports/imss",
        headers=h,
        json={"empresa_id": ids["empresa_id"], "periodo_label": "SEM-2026-47"},
    )
    assert r_exp_imss.status_code == 201
    imss_regs = r_exp_imss.json()["registros"]
    assert len(imss_regs) >= 3
    assert all(r["circuito_pago"] == "IMSS_MERQRY" for r in imss_regs)
    assert all(r["numero_empleado"] != "RH2-ESP-01" for r in imss_regs)

    r_exp_esp = await async_client.post(
        "/api/v1/merqry/exports/especial-contabilidad",
        headers=h,
        json={"empresa_id": ids["empresa_id"], "periodo_label": "SEM-2026-47"},
    )
    assert r_exp_esp.status_code == 201
    esp_regs = r_exp_esp.json()["registros"]
    assert len(esp_regs) == 1
    assert esp_regs[0]["numero_empleado"] == "RH2-ESP-01"
    assert esp_regs[0]["circuito_pago"] == "ESPECIAL_CONTABILIDAD"
