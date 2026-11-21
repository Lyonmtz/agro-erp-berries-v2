import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.database import get_db
from app.main import app


class DisposableTestDBGuardError(RuntimeError):
    """Error lanzado cuando se intenta correr una suite destructiva sin verificar BD desechable."""


async def verify_disposable_test_db(
    database_url: str,
    allow_destructive_env: str | None = None,
) -> str:
    """
    Guarda estricta para suites destructivas:
    Exige DOS condiciones simultaneas y NUNCA infiere desechabilidad por el nombre de la BD:
      1) Variable ALLOW_DESTRUCTIVE_TEST_DB == 'true'
      2) Verificacion real en PostgreSQL:
         SELECT db_environment FROM app_db_metadata WHERE id = 1  == 'DISPOSABLE_TEST'
    """
    flag = (
        allow_destructive_env
        if allow_destructive_env is not None
        else os.getenv("ALLOW_DESTRUCTIVE_TEST_DB", "")
    )
    if flag.strip().lower() != "true":
        raise DisposableTestDBGuardError(
            "ABORTADO: ALLOW_DESTRUCTIVE_TEST_DB debe estar explicitamente en 'true' "
            "para ejecutar pruebas destructivas."
        )

    if not database_url:
        raise DisposableTestDBGuardError(
            "ABORTADO: TEST_DATABASE_URL no configurada."
        )

    probe_engine: AsyncEngine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with probe_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT db_environment FROM app_db_metadata WHERE id = 1")
            )
            env_value = result.scalar()
    except Exception as exc:
        raise DisposableTestDBGuardError(
            f"ABORTADO: No se pudo verificar app_db_metadata.db_environment en la BD destino: {exc}"
        ) from exc
    finally:
        await probe_engine.dispose()

    if env_value != "DISPOSABLE_TEST":
        raise DisposableTestDBGuardError(
            f"ABORTADO: La BD destino reporta db_environment={env_value!r}; "
            "se requiere explicitamente 'DISPOSABLE_TEST' en app_db_metadata. "
            "Nunca se asume desechabilidad por nombre de base."
        )

    return env_value


def get_verified_test_database_url() -> str:
    url = os.getenv("TEST_DATABASE_URL", "").strip()
    if not url:
        raise DisposableTestDBGuardError(
            "ABORTADO: Define TEST_DATABASE_URL apuntando exclusivamente a una base desechable verificada."
        )
    return url


@pytest_asyncio.fixture
async def verified_test_engine() -> AsyncGenerator[AsyncEngine, None]:
    test_url = get_verified_test_database_url()
    await verify_disposable_test_db(test_url)

    engine = create_async_engine(test_url, poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def db_session(verified_test_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """
    Sesion limpia sobre la base desechable verificada.
    Al terminar cada prueba, restaura tablas operativas transaccionales y el estado
    de lotes modificados sin tocar los seeds base.
    """
    session_factory = async_sessionmaker(
        verified_test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
            # Limpieza destructiva controlada (solo posible tras pasar verify_disposable_test_db)
            await verify_disposable_test_db(get_verified_test_database_url())
            await session.execute(text("DELETE FROM aplicaciones_fitosanitarias"))
            await session.execute(text("DELETE FROM insumos_agricolas WHERE codigo LIKE 'TEST-%'"))
            await session.execute(text("DELETE FROM registros_cosecha"))
            await session.execute(text("DELETE FROM registros_labores_culturales"))
            await session.execute(text("DELETE FROM prenomina_diaria"))
            await session.execute(text("DELETE FROM jornadas_diarias"))
            await session.execute(text("DELETE FROM resultados_evaluaciones"))
            await session.execute(text("DELETE FROM acuses_digitales"))
            await session.execute(text("DELETE FROM empleados WHERE numero_empleado LIKE 'TEST-%'"))
            await session.execute(text("DELETE FROM candidatos"))
            # Limpieza controlada de tablas de merqry_writer (outbox apagado por defecto)
            await session.execute(text("DELETE FROM merqry_write_audit_log"))
            await session.execute(text("DELETE FROM merqry_write_outbox"))
            # Limpieza controlada de tablas transaccionales/test de Fase 3B
            await session.execute(text("DELETE FROM prenomina_semanal_detalle"))
            await session.execute(text("DELETE FROM prenomina_semanal"))
            await session.execute(text("DELETE FROM campo_traslados_cajas"))
            await session.execute(text("DELETE FROM campo_movilidad_personas"))
            await session.execute(text("DELETE FROM campo_culturales_diarios"))
            await session.execute(text("DELETE FROM campo_capturas_cosecha"))
            await session.execute(text("DELETE FROM campo_cierres_operativos"))
            await session.execute(text("DELETE FROM campo_autorizaciones_operativas"))
            # Limpieza controlada de tablas transaccionales/test de Fase 2
            await session.execute(text("DELETE FROM merqry_exports_nomina"))
            await session.execute(text("DELETE FROM merqry_staging_empleados"))
            await session.execute(text("DELETE FROM bajas_finiquitos_lft"))
            await session.execute(text("DELETE FROM beneficiarios_art501"))
            await session.execute(text("DELETE FROM contratos_laborales"))
            await session.execute(text("DELETE FROM responsivas_personal"))
            await session.execute(text("DELETE FROM update_ready_excepciones"))
            await session.execute(text("DELETE FROM expedientes_personal"))
            await session.execute(text("DELETE FROM dictamenes_ingreso_reingreso"))
            await session.execute(text("DELETE FROM postulaciones_rh"))
            await session.execute(text("DELETE FROM publicaciones_vacante"))
            await session.execute(text("DELETE FROM vacantes"))
            await session.execute(text("DELETE FROM aprobaciones_cobertura"))
            await session.execute(text("DELETE FROM solicitudes_cobertura"))
            await session.execute(text("DELETE FROM perfiles_puesto_versiones"))
            await session.execute(text("DELETE FROM plazas_autorizadas"))
            # Limpieza controlada de tablas transaccionales/test de Fase 3A
            await session.execute(text("DELETE FROM trasplante_cierres_persona_dia"))
            await session.execute(text("DELETE FROM trasplante_review_tokens"))
            await session.execute(text("DELETE FROM trasplante_produccion_lineas"))
            await session.execute(text("DELETE FROM trasplante_segmentos_tiempo"))
            await session.execute(text("DELETE FROM trasplante_asignacion_participantes"))
            await session.execute(text("DELETE FROM trasplante_asignaciones"))
            await session.execute(text("DELETE FROM trasplante_bins_ledger"))
            await session.execute(text("DELETE FROM trasplante_bins"))
            await session.execute(text("DELETE FROM trasplante_camiones_lotes"))
            await session.execute(text("DELETE FROM trasplante_programacion_llegadas"))
            await session.execute(text("DELETE FROM sync_command_fences"))
            await session.execute(text("DELETE FROM sync_idempotency_log"))
            # Limpieza controlada de tablas transaccionales/test de Fase 1
            await session.execute(text("DELETE FROM etl_cuarentena_identidad"))
            await session.execute(text("DELETE FROM etl_lotes_migracion"))
            await session.execute(text("DELETE FROM funciones_operativas_temporales"))
            await session.execute(text("DELETE FROM documentos_entidad"))
            await session.execute(text("DELETE FROM nips_personal"))
            await session.execute(text("DELETE FROM auditoria_universal"))
            await session.execute(text("DELETE FROM codigos_alternativos WHERE codigo_externo LIKE 'TEST-%' OR descripcion LIKE '%ETL%' OR descripcion LIKE '%canónica de persona%'"))
            await session.execute(text("DELETE FROM localizaciones_fisicas WHERE clave LIKE 'TEST-%'"))
            await session.execute(text("DELETE FROM unidades_operativas WHERE clave LIKE 'TEST-%'"))
            await session.execute(text("DELETE FROM sucursales WHERE clave LIKE 'TEST-%'"))
            await session.execute(text("DELETE FROM relaciones_laborales WHERE numero_empleado LIKE 'TEST-%' OR numero_empleado LIKE 'ETL-%' OR numero_empleado LIKE 'RH2-%'"))
            await session.execute(text("DELETE FROM personas WHERE curp LIKE 'TEST%' OR curp LIKE 'ETLP%' OR curp LIKE 'F2RH%'"))
            await session.execute(text("DELETE FROM usuarios_roles WHERE usuario_id IN (SELECT id FROM usuarios WHERE username LIKE 'test.%')"))
            await session.execute(text("DELETE FROM usuarios WHERE username LIKE 'test.%'"))
            await session.execute(
                text(
                    """
                    UPDATE lotes_produccion
                       SET estatus_fitosanitario = CASE WHEN activo THEN 'LIBRE_CORTE' ELSE 'CERRADO' END,
                           fecha_liberacion_corte = NULL
                    """
                )
            )
            await session.commit()


@pytest_asyncio.fixture
async def async_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client
    finally:
        app.dependency_overrides.clear()
