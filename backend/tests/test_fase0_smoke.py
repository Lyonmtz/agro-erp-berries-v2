from datetime import datetime, timedelta, timezone
from decimal import Decimal
import os
import uuid

import pytest
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from tests.conftest import (
    DisposableTestDBGuardError,
    get_verified_test_database_url,
    verify_disposable_test_db,
)


async def test_guarda_rechaza_si_falta_bandera_entorno():
    test_url = get_verified_test_database_url()
    with pytest.raises(DisposableTestDBGuardError, match="ALLOW_DESTRUCTIVE_TEST_DB"):
        await verify_disposable_test_db(test_url, allow_destructive_env="false")


async def test_guarda_rechaza_base_development_aunque_bandera_sea_true():
    """
    Verifica con una lectura estrictamente SELECT que la base operativa DEVELOPMENT
    es rechazada por la guarda aunque ALLOW_DESTRUCTIVE_TEST_DB='true'.
    """
    dev_url = os.getenv(
        "DATABASE_URL",
        "postgresql+asyncpg://agro_admin:DevPassword2026!@db:5432/agro_berries_erp",
    )
    with pytest.raises(DisposableTestDBGuardError, match="DEVELOPMENT"):
        await verify_disposable_test_db(dev_url, allow_destructive_env="true")


def test_merqry_siempre_solo_lectura_en_config():
    with pytest.raises(ValidationError, match="MERQRY_READONLY_MODE"):
        Settings(merqry_readonly_mode=False)


async def test_health_endpoint(async_client: AsyncClient):
    resp = await async_client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "online"
    assert body["cultivos_activos"] == 3
    assert body["db_environment"] == "DISPOSABLE_TEST"
    assert body["merqry_mode"] == "READ_ONLY"


async def test_seeds_cultivos_lotes_variedades_y_empleados(db_session: AsyncSession):
    # 1. Cultivos base con especificaciones exactas de Fase 0
    cultivos = {
        r.codigo: r
        for r in (
            await db_session.execute(
                text(
                    """
                    SELECT codigo, nombre, empresa_clave, unidad_cosecha_default,
                           unidades_por_caja, peso_neto_caja_kg, peso_real_caja_kg,
                           merma_maxima_permitida_pct, cajas_por_tarima, permite_cosecha_domingo
                    FROM cultivos
                    """
                )
            )
        ).all()
    }
    assert set(cultivos.keys()) == {"FRAMB", "ARAND", "FRESA"}

    assert cultivos["FRAMB"].empresa_clave == "NFA"
    assert cultivos["FRAMB"].unidades_por_caja == 12
    assert Decimal(str(cultivos["FRAMB"].peso_neto_caja_kg)) == Decimal("2.040")
    assert Decimal(str(cultivos["FRAMB"].peso_real_caja_kg)) == Decimal("2.140")
    assert Decimal(str(cultivos["FRAMB"].merma_maxima_permitida_pct)) == Decimal("10.00")
    assert cultivos["FRAMB"].cajas_por_tarima == 200
    assert cultivos["FRAMB"].permite_cosecha_domingo is True

    assert cultivos["ARAND"].empresa_clave == "BIO"
    assert cultivos["ARAND"].unidades_por_caja == 12
    assert Decimal(str(cultivos["ARAND"].peso_neto_caja_kg)) == Decimal("2.040")
    assert Decimal(str(cultivos["ARAND"].peso_real_caja_kg)) == Decimal("2.140")
    assert Decimal(str(cultivos["ARAND"].merma_maxima_permitida_pct)) == Decimal("8.00")
    assert cultivos["ARAND"].cajas_por_tarima == 192
    assert cultivos["ARAND"].permite_cosecha_domingo is False

    assert cultivos["FRESA"].empresa_clave == "NFA"
    assert cultivos["FRESA"].unidades_por_caja == 8
    assert Decimal(str(cultivos["FRESA"].peso_neto_caja_kg)) == Decimal("3.630")
    assert Decimal(str(cultivos["FRESA"].peso_real_caja_kg)) == Decimal("3.750")
    assert Decimal(str(cultivos["FRESA"].merma_maxima_permitida_pct)) == Decimal("10.00")
    assert cultivos["FRESA"].cajas_por_tarima == 120
    assert cultivos["FRESA"].permite_cosecha_domingo is False

    # 2. Lotes fisicos reales activos (17) e inactivos documentados (2)
    lotes = {
        r.codigo_lote: r
        for r in (
            await db_session.execute(
                text(
                    """
                    SELECT codigo_lote, empresa_clave, superficie_ha, metros_lineales_totales,
                           tipo_estructura, nivel_tecnologia, origen_diseno, ancho_tunel_m, activo
                    FROM lotes_produccion
                    """
                )
            )
        ).all()
    }
    activos = [k for k, v in lotes.items() if v.activo]
    assert len(activos) == 17
    assert lotes["NFA-FRAMB-M01"].tipo_estructura == "BATICENITAL"
    assert Decimal(str(lotes["NFA-FRAMB-M01"].metros_lineales_totales)) == Decimal("3040.00")
    assert lotes["NFA-FRAMB-M11"].tipo_estructura == "AUSTERO"
    assert Decimal(str(lotes["NFA-FRAMB-M11"].metros_lineales_totales)) == Decimal("2736.00")
    assert Decimal(str(lotes["NFA-FRAMB-M1.1"].ancho_tunel_m)) == Decimal("11.50")
    assert lotes["NFA-FRESA-M21"].tipo_estructura == "MEDIA_TECNOLOGIA"
    assert lotes["NFA-FRESA-M22"].tipo_estructura == "MEDIA_TECNOLOGIA"
    assert Decimal(str(lotes["BIO-ARAND-M1.2"].ancho_tunel_m)) == Decimal("11.50")
    assert Decimal(str(lotes["BIO-ARAND-M2.1"].ancho_tunel_m)) == Decimal("10.00")
    assert Decimal(str(lotes["BIO-ARAND-M2.2"].ancho_tunel_m)) == Decimal("10.00")
    assert lotes["REF-MOD7-INF"].activo is False
    assert lotes["REF-VIVERO-PLAN"].activo is False

    # 3. Variedades confirmadas (DJ Long Cane / Primocana, AzraBlue) y densidades M1-M11 confirmadas vs 6 modulos por conciliar
    variedades = {
        r.codigo: r
        for r in (
            await db_session.execute(
                text(
                    """
                    SELECT codigo, cohorte, codigo_genetico, confirmado_tecnico
                    FROM variedades_cultivo
                    """
                )
            )
        ).all()
    }
    assert variedades["FRAMB-DJ-LC"].confirmado_tecnico is True
    assert variedades["FRAMB-DJ-LC"].codigo_genetico == "DJ"
    assert variedades["ARAND-AZRABLUE"].confirmado_tecnico is True
    assert variedades["ARAND-AZRABLUE"].codigo_genetico == "FCM14-031"
    assert variedades["FRESA-ALBION-HIST"].confirmado_tecnico is False

    dens_stats = (
        await db_session.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE confirmado_tecnico = TRUE) AS confirmados,
                    COUNT(*) FILTER (WHERE confirmado_tecnico = FALSE) AS pendientes,
                    COUNT(*) FILTER (WHERE umbral_merma_trasplante_pct IS NULL) AS umbrales_pendientes,
                    SUM(plantas_estimadas_lote) FILTER (WHERE confirmado_tecnico = TRUE) AS canas_m1_m11
                FROM lotes_densidades_config
                """
            )
        )
    ).first()
    assert dens_stats.confirmados == 11  # M1..M11 Frambuesa confirmados por Manual Integral + Catalogo Grower
    assert dens_stats.pendientes == 6    # M1.1, M21, M22, M1.2, M2.1, M2.2 pendientes de cierre con Luis
    assert dens_stats.umbrales_pendientes == 17  # Umbrales de trasplante siguen NULL hasta confirmacion
    assert dens_stats.canas_m1_m11 == 148944     # (8 * 13,920) + (3 * 12,528)

    # 4. Empleados iniciales EMP-1001 y EMP-2001 y baterias
    emps = {
        r.numero_empleado
        for r in (
            await db_session.execute(
                text("SELECT numero_empleado FROM empleados WHERE estatus = 'ACTIVO'")
            )
        ).all()
    }
    assert {"EMP-1001", "EMP-2001"}.issubset(emps)


async def test_trigger_fitosanitario_phi_bloquea_lote_y_cosecha(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    lote = (
        await db_session.execute(
            text("SELECT id FROM lotes_produccion WHERE codigo_lote = 'NFA-FRAMB-M01'")
        )
    ).first()
    ing = (
        await db_session.execute(
            text("SELECT id FROM empleados WHERE numero_empleado = 'EMP-1001'")
        )
    ).first()
    assert lote and ing

    insumo_id = (
        await db_session.execute(
            text(
                """
                INSERT INTO insumos_agricolas (
                    codigo, nombre_comercial, ingrediente_activo, categoria,
                    unidad_medida, dias_intervalo_seguridad, stock_actual, costo_promedio_unitario
                ) VALUES (
                    'TEST-PHI-05', 'Fungicida Test PHI 5d', 'Azoxistrobin', 'AGROQUIMICO',
                    'LITRO', 5, 10.000, 450.00
                )
                RETURNING id
                """
            )
        )
    ).scalar()

    ahora = datetime.now(timezone.utc)
    await db_session.execute(
        text(
            """
            INSERT INTO aplicaciones_fitosanitarias (
                lote_id, insumo_id, ingeniero_responsable_id, dosis_aplicada,
                volumen_agua_litros, plaga_objetivo, fecha_aplicacion,
                fecha_liberacion_calculada, costo_total_aplicacion
            ) VALUES (
                :lid, :iid, :ing, 1.250, 200.00, 'Botrytis', :fa, :fl, 562.50
            )
            """
        ),
        {
            "lid": lote.id,
            "iid": insumo_id,
            "ing": ing.id,
            "fa": ahora,
            "fl": ahora + timedelta(days=5),
        },
    )
    await db_session.commit()

    lote_estado = (
        await db_session.execute(
            text(
                """
                SELECT estatus_fitosanitario, fecha_liberacion_corte
                FROM lotes_produccion
                WHERE id = :lid
                """
            ),
            {"lid": lote.id},
        )
    ).first()
    assert lote_estado.estatus_fitosanitario == "BLOQUEADO_INTERVALO_SEGURIDAD"
    assert lote_estado.fecha_liberacion_corte is not None
    assert lote_estado.fecha_liberacion_corte >= ahora + timedelta(days=4, hours=23)

    # Intentar registrar cosecha en lote bloqueado debe responder 403
    resp = await async_client.post(
        "/api/v1/campo/cosecha",
        json={
            "codigo_trazabilidad_caja": f"BOX-PHI-{uuid.uuid4().hex[:6]}",
            "empleado_qr_o_numero": "EMP-2001",
            "supervisor_numero": "EMP-1001",
            "lote_id": lote.id,
            "cantidad_cajas": 2,
            "calidad_fruta": "EXPORTACION",
        },
    )
    assert resp.status_code == 403
    assert "BLOQUEO FITOSANITARIO" in resp.json()["detail"]


async def test_registro_cajas_exportacion_y_rentabilidad_sin_duplicacion(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    lote = (
        await db_session.execute(
            text("SELECT id FROM lotes_produccion WHERE codigo_lote = 'NFA-FRAMB-M01'")
        )
    ).first()
    assert lote

    # 10 EXPORTACION + 5 NACIONAL + 2 PROCESO_REZAGA = 17 totales, pero solo 10 de exportacion
    payloads = [
        (10.0, "EXPORTACION"),
        (5.0, "NACIONAL"),
        (2.0, "PROCESO_REZAGA"),
    ]
    for idx, (cajas, calidad) in enumerate(payloads):
        r = await async_client.post(
            "/api/v1/campo/cosecha",
            json={
                "codigo_trazabilidad_caja": f"BOX-TEST-{idx}-{uuid.uuid4().hex[:6]}",
                "empleado_qr_o_numero": "EMP-2001",
                "supervisor_numero": "EMP-1001",
                "lote_id": lote.id,
                "cantidad_cajas": cajas,
                "calidad_fruta": calidad,
            },
        )
        assert r.status_code == 200, r.text

    # Verificar que prenomina_diaria.total_cajas_exportacion guardo 10.00 y NO 17.00
    pre = (
        await db_session.execute(
            text(
                """
                SELECT pd.total_cajas_exportacion, pd.total_cajas_rezaga, pd.total_percepcion_dia
                FROM prenomina_diaria pd
                JOIN empleados e ON e.id = pd.empleado_id
                WHERE e.numero_empleado = 'EMP-2001'
                """
            )
        )
    ).first()
    assert pre is not None
    assert Decimal(str(pre.total_cajas_exportacion)) == Decimal("10.00")
    assert Decimal(str(pre.total_cajas_rezaga)) == Decimal("2.00")
    assert Decimal(str(pre.total_percepcion_dia)) > Decimal("0")

    # Verificar que vw_direccion_rentabilidad_cultivo asigna MO solo a Frambuesa (sin duplicar en Arandano/Fresa)
    dash = await async_client.get("/api/v1/direccion/dashboard")
    assert dash.status_code == 200
    por_cultivo = {c["cultivo_codigo"]: c for c in dash.json()["cultivos"]}
    assert Decimal(str(por_cultivo["FRAMB"]["gasto_mano_obra_acumulado"])) == Decimal(
        str(pre.total_percepcion_dia)
    )
    assert Decimal(str(por_cultivo["ARAND"]["gasto_mano_obra_acumulado"])) == Decimal("0")
    assert Decimal(str(por_cultivo["FRESA"]["gasto_mano_obra_acumulado"])) == Decimal("0")


async def test_404_controlado_bateria_y_candidato_inexistentes(
    async_client: AsyncClient,
    db_session: AsyncSession,
):
    # Bateria inexistente
    r_bat = await async_client.post(
        "/api/v1/public/evaluar",
        json={
            "candidato_id": str(uuid.uuid4()),
            "bateria_id": 999999,
            "respuestas": {},
        },
    )
    assert r_bat.status_code == 404

    # Bateria existente pero candidato inexistente
    bat_id = (
        await db_session.execute(
            text("SELECT id FROM baterias_evaluacion WHERE codigo = 'ZAVIC_OP'")
        )
    ).scalar()
    assert bat_id is not None
    r_cand_eval = await async_client.post(
        "/api/v1/public/evaluar",
        json={
            "candidato_id": str(uuid.uuid4()),
            "bateria_id": bat_id,
            "respuestas": {},
        },
    )
    assert r_cand_eval.status_code == 404

    # Candidato inexistente al contratar
    r_cand = await async_client.post(
        "/api/v1/rh/contratar",
        json={
            "candidato_id": str(uuid.uuid4()),
            "numero_empleado": "TEST-9999",
            "salario_diario_pactado": 330.0,
        },
    )
    assert r_cand.status_code == 404
