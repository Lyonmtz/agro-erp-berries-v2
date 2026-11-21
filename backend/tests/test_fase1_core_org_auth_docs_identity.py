from datetime import date

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
async def test_auth_requerida_y_login_jwt_con_roles_y_alcances(async_client: AsyncClient):
    # Sin token -> 401
    r_no_auth = await async_client.get("/api/v1/org/empresas")
    assert r_no_auth.status_code == 401

    # Password invalido -> 401
    r_bad = await async_client.post(
        "/api/v1/auth/login",
        json={"username": "admin.dir", "password": "WrongPassword!"},
    )
    assert r_bad.status_code == 401

    # Login valido admin.dir (L4 global)
    data = await _login(async_client, "admin.dir", "AdminBerries2026!")
    assert data["token_type"] == "bearer"
    assert data["usuario"]["alcance_global"] is True
    assert data["usuario"]["nivel_autorizacion_max"] == 4

    me = await async_client.get("/api/v1/auth/me", headers=_auth(data["access_token"]))
    assert me.status_code == 200
    assert me.json()["username"] == "admin.dir"


@pytest.mark.asyncio
async def test_aislamiento_rbac_por_empresa_y_unidad_en_servidor(
    async_client: AsyncClient, db_session: AsyncSession
):
    nfa_id = (await db_session.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()
    bio_id = (await db_session.execute(text("SELECT id FROM empresas WHERE clave = 'BIO'"))).scalar()

    # rh.nfa solo debe ver NFA y no BIO
    rh_nfa = await _login(async_client, "rh.nfa", "RhNfa2026!")
    rh_headers = _auth(rh_nfa["access_token"])

    emp_resp = await async_client.get("/api/v1/org/empresas", headers=rh_headers)
    assert emp_resp.status_code == 200
    claves = [e["clave"] for e in emp_resp.json()]
    assert claves == ["NFA"]

    # rh.nfa NO puede crear una persona en BIO (403)
    r_cross = await async_client.post(
        "/api/v1/identidad/personas",
        headers=rh_headers,
        json={
            "curp": "TEST900101HHG00001",
            "nombre": "Bloqueado",
            "apellido_paterno": "Bio",
            "empresa_id": bio_id,
        },
    )
    assert r_cross.status_code == 403

    # sup.framb esta acotado solo a NFA-UO-FRAMB: solo ve localizaciones de su unidad
    sup_framb = await _login(async_client, "sup.framb", "SupFramb2026!")
    sup_headers = _auth(sup_framb["access_token"])

    uo_framb_id = (
        await db_session.execute(text("SELECT id FROM unidades_operativas WHERE clave = 'NFA-UO-FRAMB'"))
    ).scalar()
    locs = await async_client.get("/api/v1/org/localizaciones", headers=sup_headers)
    assert locs.status_code == 200
    assert len(locs.json()) >= 12
    assert all(l["unidad_operativa_id"] == uo_framb_id for l in locs.json())

    # sup.framb NO puede crear una sucursal a nivel empresa (ni permiso ni nivel L3) -> 403
    r_suc = await async_client.post(
        "/api/v1/org/sucursales",
        headers=sup_headers,
        json={"empresa_id": nfa_id, "clave": "TEST-SUC-X", "nombre": "Sucursal No Autorizada"},
    )
    assert r_suc.status_code == 403


@pytest.mark.asyncio
async def test_jerarquia_una_matriz_por_empresa_y_trigger_contexto_localizacion(
    async_client: AsyncClient, db_session: AsyncSession
):
    admin = await _login(async_client, "admin.dir", "AdminBerries2026!")
    headers = _auth(admin["access_token"])

    nfa_id = (await db_session.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()
    bio_suc_id = (
        await db_session.execute(text("SELECT id FROM sucursales WHERE clave = 'BIO-MATRIZ'"))
    ).scalar()

    # 1) Segunda matriz en NFA debe fallar con 409
    r_dup_mat = await async_client.post(
        "/api/v1/org/sucursales",
        headers=headers,
        json={
            "empresa_id": nfa_id,
            "clave": "TEST-NFA-MAT2",
            "nombre": "Segunda Matriz Invalida",
            "naturaleza_sucursal": "MATRIZ",
            "es_matriz": True,
        },
    )
    assert r_dup_mat.status_code == 409

    # 2) Sucursal operativa normal si se permite con sus funciones
    r_ok = await async_client.post(
        "/api/v1/org/sucursales",
        headers=headers,
        json={
            "empresa_id": nfa_id,
            "clave": "TEST-NFA-OP2",
            "nombre": "Sucursal Empaque Sur",
            "naturaleza_sucursal": "EMPAQUE",
            "es_matriz": False,
            "funciones": ["empaque", "postcosecha"],
        },
    )
    assert r_ok.status_code == 201
    assert r_ok.json()["funciones"] == ["empaque", "postcosecha"]

    # 3) Trigger trg_validar_localizacion_fisica_contexto bloquea mezcla empresa NFA + sucursal BIO
    r_bad_loc = await async_client.post(
        "/api/v1/org/localizaciones",
        headers=headers,
        json={
            "empresa_id": nfa_id,
            "sucursal_id": bio_suc_id,
            "clave": "TEST-LOC-CRUZADA",
            "nombre": "Localizacion Contexto Invalido",
            "tipo_localizacion": "invernadero",
        },
    )
    assert r_bad_loc.status_code == 422
    assert "INCONSISTENCIA_CONTEXTO" in r_bad_loc.json()["detail"]


@pytest.mark.asyncio
async def test_documentos_bloqueo_renuncia_anticipada_y_codigos_alternativos(
    async_client: AsyncClient, db_session: AsyncSession
):
    rh_nfa = await _login(async_client, "rh.nfa", "RhNfa2026!")
    headers = _auth(rh_nfa["access_token"])

    nfa_id = (await db_session.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()
    persona_id = (
        await db_session.execute(text("SELECT id::text FROM personas WHERE curp = 'COSL950515MHG00202'"))
    ).scalar()

    # 1) Bloqueo legal absoluto de RENUNCIA_ANTICIPADA
    r_prohib = await async_client.post(
        "/api/v1/documentos",
        headers=headers,
        json={
            "tipo_entidad": "PERSONA",
            "id_entidad": persona_id,
            "tipo_documento_codigo": "RENUNCIA_ANTICIPADA",
            "empresa_id": nfa_id,
            "nombre_archivo": "renuncia.pdf",
            "ruta_storage": "s3://docs/renuncia.pdf",
        },
    )
    assert r_prohib.status_code == 422
    assert "DOCUMENTO_PROHIBIDO_LEGALMENTE" in r_prohib.json()["detail"]

    # 2) Bloqueo de base64 / binarios embebidos
    r_bin = await async_client.post(
        "/api/v1/documentos",
        headers=headers,
        json={
            "tipo_entidad": "PERSONA",
            "id_entidad": persona_id,
            "tipo_documento_codigo": "INE",
            "empresa_id": nfa_id,
            "nombre_archivo": "ine.png",
            "ruta_storage": "data:image/png;base64,AAAA",
        },
    )
    assert r_bin.status_code == 400

    # 3) Registro y validacion de documento valido + codigo alternativo cuenta contable separado
    r_doc = await async_client.post(
        "/api/v1/documentos",
        headers=headers,
        json={
            "tipo_entidad": "PERSONA",
            "id_entidad": persona_id,
            "tipo_documento_codigo": "INE",
            "empresa_id": nfa_id,
            "folio_documento": "INE-2026-001",
            "nombre_archivo": "ine_lucia.pdf",
            "ruta_storage": "/uploads/nfa/personas/ine_lucia.pdf",
        },
    )
    assert r_doc.status_code == 201
    doc_id = r_doc.json()["id"]

    r_val = await async_client.patch(
        f"/api/v1/documentos/{doc_id}/validar",
        headers=headers,
        json={"estatus": "VALIDADO", "observaciones": "Legible y vigente"},
    )
    assert r_val.status_code == 200
    assert r_val.json()["estatus"] == "VALIDADO"

    r_cod = await async_client.post(
        "/api/v1/documentos/codigos-alternativos",
        headers=headers,
        json={
            "tipo_entidad": "LOTE",
            "id_entidad": "NFA-FRAMB-M01",
            "sistema_origen": "CUENTA_CONTABLE",
            "codigo_externo": "TEST-CC-5101-FRAMB",
            "descripcion": "Cuenta contable separada de clave operativa",
            "empresa_id": nfa_id,
        },
    )
    assert r_cod.status_code == 201


@pytest.mark.asyncio
async def test_nip_hasheado_bcrypt_y_bloqueo_intentos_fallidos(
    async_client: AsyncClient, db_session: AsyncSession
):
    rh_nfa = await _login(async_client, "rh.nfa", "RhNfa2026!")
    sup_framb = await _login(async_client, "sup.framb", "SupFramb2026!")

    persona_id = (
        await db_session.execute(text("SELECT id::text FROM personas WHERE curp = 'COSL950515MHG00202'"))
    ).scalar()

    r_set = await async_client.post(
        "/api/v1/auth/nips/establecer",
        headers=_auth(rh_nfa["access_token"]),
        json={"persona_id": persona_id, "nip": "4829"},
    )
    assert r_set.status_code == 200

    # Verificar que en BD nunca se guarda en texto plano
    stored_hash = (
        await db_session.execute(
            text("SELECT nip_hash FROM nips_personal WHERE persona_id = CAST(:pid AS uuid)"),
            {"pid": persona_id},
        )
    ).scalar()
    assert stored_hash != "4829"
    assert stored_hash.startswith("$2")

    # Verificacion correcta por supervisor
    r_ok = await async_client.post(
        "/api/v1/auth/nips/verificar",
        headers=_auth(sup_framb["access_token"]),
        json={"persona_id": persona_id, "nip": "4829"},
    )
    assert r_ok.status_code == 200
    assert r_ok.json()["valido"] is True

    # 5 intentos fallidos -> bloqueo 423 en el 6o intento
    for _ in range(5):
        r_fail = await async_client.post(
            "/api/v1/auth/nips/verificar",
            headers=_auth(sup_framb["access_token"]),
            json={"persona_id": persona_id, "nip": "0000"},
        )
        assert r_fail.status_code == 200
        assert r_fail.json()["valido"] is False

    r_locked = await async_client.post(
        "/api/v1/auth/nips/verificar",
        headers=_auth(sup_framb["access_token"]),
        json={"persona_id": persona_id, "nip": "4829"},
    )
    assert r_locked.status_code == 423


@pytest.mark.asyncio
async def test_funcion_operativa_temporal_no_sobrescribe_puesto_nominal(
    async_client: AsyncClient, db_session: AsyncSession
):
    sup_framb = await _login(async_client, "sup.framb", "SupFramb2026!")
    headers = _auth(sup_framb["access_token"])

    rel = (
        await db_session.execute(
            text(
                """
                SELECT id::text AS id, puesto_nominal_id
                FROM relaciones_laborales
                WHERE numero_empleado = 'EMP-2001'
                """
            )
        )
    ).first()

    r_asig = await async_client.post(
        "/api/v1/identidad/funciones-temporales",
        headers=headers,
        json={
            "relacion_laboral_id": rel.id,
            "funcion_operativa": "PESADOR",
            "fecha_inicio": date.today().isoformat(),
            "motivo": "Cobertura temporal de pesaje en Modulo 3 por incapacidad",
        },
    )
    assert r_asig.status_code == 201
    func_id = r_asig.json()["id"]
    assert r_asig.json()["puesto_nominal_intacto_id"] == rel.puesto_nominal_id

    # Confirmar en BD que puesto_nominal_id sigue exactamente igual
    puesto_actual = (
        await db_session.execute(
            text("SELECT puesto_nominal_id FROM relaciones_laborales WHERE id = CAST(:id AS uuid)"),
            {"id": rel.id},
        )
    ).scalar()
    assert puesto_actual == rel.puesto_nominal_id

    # Cerrar funcion temporal
    r_close = await async_client.patch(
        f"/api/v1/identidad/funciones-temporales/{func_id}/cerrar",
        headers=headers,
    )
    assert r_close.status_code == 200
    assert r_close.json()["activa"] is False


@pytest.mark.asyncio
async def test_etl_identidades_concilia_curp_y_cuarentena_sin_fusionar_por_nombre_o_telefono(
    async_client: AsyncClient, db_session: AsyncSession
):
    rh_nfa = await _login(async_client, "rh.nfa", "RhNfa2026!")
    headers = _auth(rh_nfa["access_token"])

    nfa_id = (await db_session.execute(text("SELECT id FROM empresas WHERE clave = 'NFA'"))).scalar()
    nfa_suc_id = (
        await db_session.execute(text("SELECT id FROM sucursales WHERE clave = 'NFA-MATRIZ'"))
    ).scalar()
    uo_framb_id = (
        await db_session.execute(text("SELECT id FROM unidades_operativas WHERE clave = 'NFA-UO-FRAMB'"))
    ).scalar()

    payload = {
        "fuente_nombre": "Padron_Historico_Prueba_2026",
        "empresa_id": nfa_id,
        "sucursal_id": nfa_suc_id,
        "unidad_operativa_id": uo_framb_id,
        "registros": [
            # 1) Persona nueva limpia con circuito ESPECIAL_CONTABILIDAD
            {
                "curp": "ETLP920410HHGGRL01",
                "nombre": "Pedro",
                "apellido_paterno": "García",
                "apellido_materno": "López",
                "telefono": "7711234567",
                "numero_empleado": "ETL-9001",
                "circuito_pago": "ESPECIAL_CONTABILIDAD",
                "puesto_codigo": "COSECHADOR",
            },
            # 2) Conciliacion exacta por CURP existente (EMP-2001)
            {
                "curp": "COSL950515MHG00202",
                "nombre": "Lucía",
                "apellido_paterno": "Hernández",
                "apellido_materno": "Cruz",
                "numero_empleado": "EMP-2001",
                "circuito_pago": "IMSS_MERQRY",
            },
            # 3) Homonimo exacto con CURP distinto -> CUARENTENA (NO fusionar)
            {
                "curp": "ETLP990101MHGHRZ09",
                "nombre": "Lucía",
                "apellido_paterno": "Hernández",
                "apellido_materno": "Cruz",
                "telefono": "7719998877",
                "numero_empleado": "ETL-9002",
            },
            # 4) Telefono duplicado de Pedro Garcia con otro nombre y CURP -> CUARENTENA (NO fusionar)
            {
                "curp": "ETLP930520HHGPRS02",
                "nombre": "Juan",
                "apellido_paterno": "Pérez",
                "apellido_materno": "Solís",
                "telefono": "771-123-4567",
                "numero_empleado": "ETL-9003",
            },
        ],
    }

    r_etl = await async_client.post("/api/v1/identidad/etl/importar", headers=headers, json=payload)
    assert r_etl.status_code == 201, r_etl.text
    res = r_etl.json()
    assert res["estatus"] == "CON_CUARENTENA"
    assert res["creados"] == 1
    assert res["conciliados_curp"] == 1
    assert res["enviados_cuarentena"] == 2

    # Verificar cuarentena via API
    r_q = await async_client.get("/api/v1/identidad/etl/cuarentena", headers=headers)
    assert r_q.status_code == 200
    motivos = {item["motivo_conflicto"] for item in r_q.json()}
    assert "HOMONIMO_SIN_CURP_COINCIDENTE" in motivos
    assert "TELEFONO_DUPLICADO_OTRA_PERSONA" in motivos

    # Verificar que Pedro quedo con circuito ESPECIAL_CONTABILIDAD y que los 2 en cuarentena NO se crearon
    circuito = (
        await db_session.execute(
            text("SELECT circuito_pago FROM relaciones_laborales WHERE numero_empleado = 'ETL-9001'")
        )
    ).scalar()
    assert circuito == "ESPECIAL_CONTABILIDAD"

    no_creados = (
        await db_session.execute(
            text("SELECT COUNT(*) FROM personas WHERE curp IN ('ETLP990101MHGHRZ09', 'ETLP930520HHGPRS02')")
        )
    ).scalar()
    assert no_creados == 0

    # Verificar rastro en auditoria_universal
    aud_cnt = (
        await db_session.execute(
            text("SELECT COUNT(*) FROM auditoria_universal WHERE accion = 'ETL_IMPORTAR_IDENTIDADES'")
        )
    ).scalar()
    assert aud_cnt >= 1
