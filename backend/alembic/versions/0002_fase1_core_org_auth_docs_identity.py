"""Fase 1: Jerarquia Organizacional (7 niveles), RBAC con Alcance, Documentos/QR e Identidad/ETL.

Revision ID: 0002_fase1_core_org
Revises: 0001_fase0_base
Create Date: 2026-11-21 00:45:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_fase1_core_org"
down_revision: Union[str, None] = "0001_fase0_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATEMENTS = [
    # 1. Jerarquia organizacional
    """
    CREATE TABLE IF NOT EXISTS empresas (
        id SERIAL PRIMARY KEY,
        clave VARCHAR(10) UNIQUE NOT NULL CHECK (clave ~ '^[A-Z0-9_-]{2,10}$'),
        razon_social VARCHAR(180) NOT NULL,
        nombre_comercial VARCHAR(120) NOT NULL,
        tipo_persona VARCHAR(15) NOT NULL DEFAULT 'MORAL' CHECK (tipo_persona IN ('MORAL', 'FISICA')),
        rfc VARCHAR(13) UNIQUE,
        registro_patronal_imss VARCHAR(30),
        regimen_fiscal VARCHAR(120),
        activa BOOLEAN NOT NULL DEFAULT TRUE,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sucursales (
        id SERIAL PRIMARY KEY,
        empresa_id INT NOT NULL REFERENCES empresas(id),
        clave VARCHAR(30) NOT NULL,
        nombre VARCHAR(140) NOT NULL,
        naturaleza_sucursal VARCHAR(30) NOT NULL DEFAULT 'OPERATIVA' CHECK (
            naturaleza_sucursal IN ('MATRIZ', 'OPERATIVA', 'EMPAQUE', 'ADMINISTRATIVA', 'MIXTA')
        ),
        es_matriz BOOLEAN NOT NULL DEFAULT FALSE,
        direccion TEXT,
        municipio VARCHAR(100),
        estado VARCHAR(80),
        codigo_postal VARCHAR(10),
        activa BOOLEAN NOT NULL DEFAULT TRUE,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (empresa_id, clave)
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_sucursales_una_matriz_por_empresa
        ON sucursales (empresa_id)
        WHERE es_matriz = TRUE AND activa = TRUE
    """,
    """
    CREATE TABLE IF NOT EXISTS sucursal_funciones (
        id SERIAL PRIMARY KEY,
        sucursal_id INT NOT NULL REFERENCES sucursales(id) ON DELETE CASCADE,
        funcion VARCHAR(40) NOT NULL CHECK (
            funcion IN (
                'produccion', 'rh', 'empaque', 'inocuidad', 'almacen', 'contabilidad',
                'comercializacion', 'postcosecha', 'calidad', 'mantenimiento',
                'villas', 'comedor', 'transporte', 'compras', 'direccion',
                'sistemas', 'tecnico', 'nomina'
            )
        ),
        activa BOOLEAN NOT NULL DEFAULT TRUE,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (sucursal_id, funcion)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS unidades_operativas (
        id SERIAL PRIMARY KEY,
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT NOT NULL REFERENCES sucursales(id),
        clave VARCHAR(40) NOT NULL,
        nombre VARCHAR(140) NOT NULL,
        tipo_unidad VARCHAR(30) NOT NULL CHECK (
            tipo_unidad IN ('RANCHO', 'BLOQUE_MODULOS', 'EMPAQUE', 'ADMINISTRACION', 'SERVICIOS', 'VIVERO')
        ),
        rancho_id INT REFERENCES ranchos(id),
        activa BOOLEAN NOT NULL DEFAULT TRUE,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (empresa_id, clave)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS areas (
        id SERIAL PRIMARY KEY,
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT REFERENCES sucursales(id),
        unidad_operativa_id INT REFERENCES unidades_operativas(id),
        id_area_padre INT REFERENCES areas(id),
        departamento_id INT REFERENCES departamentos(id),
        clave VARCHAR(40) NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        activa BOOLEAN NOT NULL DEFAULT TRUE,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (empresa_id, clave)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS localizaciones_fisicas (
        id SERIAL PRIMARY KEY,
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT NOT NULL REFERENCES sucursales(id),
        unidad_operativa_id INT REFERENCES unidades_operativas(id),
        area_id INT REFERENCES areas(id),
        lote_id INT REFERENCES lotes_produccion(id),
        clave VARCHAR(60) NOT NULL,
        nombre VARCHAR(140) NOT NULL,
        tipo_localizacion VARCHAR(40) NOT NULL CHECK (
            tipo_localizacion IN (
                'invernadero', 'tunel', 'macrotunel', 'camara_fria', 'linea_empaque',
                'anden', 'comedor', 'cuarto_bombas', 'almacen_agroquimicos',
                'almacen_empaque', 'bodega_general', 'oficina', 'villa', 'enfermeria',
                'estacionamiento', 'caseta', 'laboratorio', 'taller', 'otro'
            )
        ),
        capacidad_referencia NUMERIC(10,2),
        unidad_capacidad VARCHAR(30),
        activa BOOLEAN NOT NULL DEFAULT TRUE,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (empresa_id, clave)
    )
    """,
    """
    CREATE OR REPLACE FUNCTION fn_validar_unidad_operativa_contexto()
    RETURNS TRIGGER AS $$
    DECLARE
        v_suc_empresa INT;
    BEGIN
        SELECT empresa_id INTO v_suc_empresa FROM sucursales WHERE id = NEW.sucursal_id;
        IF v_suc_empresa IS NULL OR v_suc_empresa <> NEW.empresa_id THEN
            RAISE EXCEPTION 'INCONSISTENCIA_CONTEXTO: sucursal_id=% no pertenece a empresa_id=%',
                NEW.sucursal_id, NEW.empresa_id;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS trg_validar_unidad_operativa_contexto ON unidades_operativas",
    """
    CREATE TRIGGER trg_validar_unidad_operativa_contexto
    BEFORE INSERT OR UPDATE ON unidades_operativas
    FOR EACH ROW EXECUTE FUNCTION fn_validar_unidad_operativa_contexto()
    """,
    """
    CREATE OR REPLACE FUNCTION fn_validar_localizacion_fisica_contexto()
    RETURNS TRIGGER AS $$
    DECLARE
        v_suc_empresa INT;
        v_uo_empresa INT;
        v_uo_sucursal INT;
        v_area_empresa INT;
        v_area_sucursal INT;
    BEGIN
        SELECT empresa_id INTO v_suc_empresa FROM sucursales WHERE id = NEW.sucursal_id;
        IF v_suc_empresa IS NULL OR v_suc_empresa <> NEW.empresa_id THEN
            RAISE EXCEPTION 'INCONSISTENCIA_CONTEXTO: sucursal_id=% no pertenece a empresa_id=%',
                NEW.sucursal_id, NEW.empresa_id;
        END IF;

        IF NEW.unidad_operativa_id IS NOT NULL THEN
            SELECT empresa_id, sucursal_id
              INTO v_uo_empresa, v_uo_sucursal
              FROM unidades_operativas
             WHERE id = NEW.unidad_operativa_id;
            IF v_uo_empresa IS NULL OR v_uo_empresa <> NEW.empresa_id OR v_uo_sucursal <> NEW.sucursal_id THEN
                RAISE EXCEPTION 'INCONSISTENCIA_CONTEXTO: unidad_operativa_id=% no coincide con empresa_id=% y sucursal_id=%',
                    NEW.unidad_operativa_id, NEW.empresa_id, NEW.sucursal_id;
            END IF;
        END IF;

        IF NEW.area_id IS NOT NULL THEN
            SELECT empresa_id, sucursal_id
              INTO v_area_empresa, v_area_sucursal
              FROM areas
             WHERE id = NEW.area_id;
            IF v_area_empresa IS NULL OR v_area_empresa <> NEW.empresa_id THEN
                RAISE EXCEPTION 'INCONSISTENCIA_CONTEXTO: area_id=% no pertenece a empresa_id=%',
                    NEW.area_id, NEW.empresa_id;
            END IF;
            IF v_area_sucursal IS NOT NULL AND v_area_sucursal <> NEW.sucursal_id THEN
                RAISE EXCEPTION 'INCONSISTENCIA_CONTEXTO: area_id=% pertenece a sucursal_id=% y no a sucursal_id=%',
                    NEW.area_id, v_area_sucursal, NEW.sucursal_id;
            END IF;
        END IF;

        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS trg_validar_localizacion_fisica_contexto ON localizaciones_fisicas",
    """
    CREATE TRIGGER trg_validar_localizacion_fisica_contexto
    BEFORE INSERT OR UPDATE ON localizaciones_fisicas
    FOR EACH ROW EXECUTE FUNCTION fn_validar_localizacion_fisica_contexto()
    """,
    """
    ALTER TABLE ranchos
        ADD COLUMN IF NOT EXISTS empresa_id INT REFERENCES empresas(id),
        ADD COLUMN IF NOT EXISTS sucursal_id INT REFERENCES sucursales(id)
    """,
    """
    ALTER TABLE lotes_produccion
        ADD COLUMN IF NOT EXISTS empresa_id INT REFERENCES empresas(id),
        ADD COLUMN IF NOT EXISTS unidad_operativa_id INT REFERENCES unidades_operativas(id)
    """,
    """
    ALTER TABLE puestos
        ADD COLUMN IF NOT EXISTS reporta_a_puesto_id INT REFERENCES puestos(id)
    """,
    # 2. Identidad canonica separada
    """
    CREATE TABLE IF NOT EXISTS personas (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        curp VARCHAR(18) UNIQUE,
        rfc VARCHAR(13) UNIQUE,
        nss VARCHAR(11) UNIQUE,
        nombre VARCHAR(100) NOT NULL,
        apellido_paterno VARCHAR(100) NOT NULL,
        apellido_materno VARCHAR(100),
        fecha_nacimiento DATE,
        telefono VARCHAR(25),
        email VARCHAR(150),
        municipio_residencia VARCHAR(120),
        clave_interna_qr VARCHAR(64) UNIQUE NOT NULL,
        activo BOOLEAN NOT NULL DEFAULT TRUE,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_personas_nombre_compuesto
        ON personas (UPPER(nombre), UPPER(apellido_paterno), UPPER(COALESCE(apellido_materno, '')))
    """,
    "CREATE INDEX IF NOT EXISTS idx_personas_telefono ON personas (telefono)",
    """
    CREATE TABLE IF NOT EXISTS relaciones_laborales (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        persona_id UUID NOT NULL REFERENCES personas(id),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT REFERENCES sucursales(id),
        unidad_operativa_id INT REFERENCES unidades_operativas(id),
        empleado_legacy_id UUID UNIQUE REFERENCES empleados(id),
        numero_empleado VARCHAR(30) NOT NULL,
        merqry_employee_id VARCHAR(50),
        circuito_pago VARCHAR(30) NOT NULL DEFAULT 'IMSS_MERQRY' CHECK (
            circuito_pago IN ('IMSS_MERQRY', 'ESPECIAL_CONTABILIDAD')
        ),
        puesto_nominal_id INT NOT NULL REFERENCES puestos(id),
        fecha_ingreso DATE NOT NULL,
        fecha_baja DATE,
        estatus VARCHAR(30) NOT NULL DEFAULT 'ACTIVO' CHECK (
            estatus IN ('PREALTA', 'ACTIVO', 'INCAPACIDAD', 'SUSPENDIDO', 'BAJA', 'REINGRESO_PENDIENTE')
        ),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (empresa_id, numero_empleado)
    )
    """,
    # 3. Seguridad multi-rol, RBAC con alcance, NIPs y auditoria
    """
    CREATE TABLE IF NOT EXISTS roles (
        id SERIAL PRIMARY KEY,
        codigo VARCHAR(40) UNIQUE NOT NULL,
        nombre VARCHAR(100) NOT NULL,
        nivel_autorizacion SMALLINT NOT NULL CHECK (nivel_autorizacion BETWEEN 1 AND 4),
        descripcion TEXT,
        activo BOOLEAN NOT NULL DEFAULT TRUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS permisos (
        id SERIAL PRIMARY KEY,
        codigo VARCHAR(80) UNIQUE NOT NULL,
        modulo VARCHAR(50) NOT NULL,
        descripcion TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roles_permisos (
        rol_id INT NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
        permiso_id INT NOT NULL REFERENCES permisos(id) ON DELETE CASCADE,
        PRIMARY KEY (rol_id, permiso_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usuarios (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        username VARCHAR(60) UNIQUE NOT NULL,
        email VARCHAR(150) UNIQUE,
        nombre_completo VARCHAR(150) NOT NULL,
        password_hash TEXT NOT NULL,
        persona_id UUID REFERENCES personas(id),
        activo BOOLEAN NOT NULL DEFAULT TRUE,
        requiere_cambio_password BOOLEAN NOT NULL DEFAULT FALSE,
        ultimo_login_en TIMESTAMPTZ,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usuarios_roles (
        id BIGSERIAL PRIMARY KEY,
        usuario_id UUID NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        rol_id INT NOT NULL REFERENCES roles(id),
        empresa_id INT REFERENCES empresas(id),
        sucursal_id INT REFERENCES sucursales(id),
        unidad_operativa_id INT REFERENCES unidades_operativas(id),
        alcance_global BOOLEAN NOT NULL DEFAULT FALSE,
        activo BOOLEAN NOT NULL DEFAULT TRUE,
        asignado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK (alcance_global = TRUE OR empresa_id IS NOT NULL)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_usuarios_roles_usuario ON usuarios_roles(usuario_id) WHERE activo = TRUE",
    """
    CREATE TABLE IF NOT EXISTS nips_personal (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        persona_id UUID UNIQUE NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
        nip_hash TEXT NOT NULL,
        intentos_fallidos INT NOT NULL DEFAULT 0 CHECK (intentos_fallidos >= 0),
        bloqueado_hasta TIMESTAMPTZ,
        actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS auditoria_universal (
        id BIGSERIAL PRIMARY KEY,
        usuario_id UUID REFERENCES usuarios(id),
        actor_username VARCHAR(80) NOT NULL,
        rol_codigo VARCHAR(50),
        empresa_id INT REFERENCES empresas(id),
        sucursal_id INT REFERENCES sucursales(id),
        unidad_operativa_id INT REFERENCES unidades_operativas(id),
        modulo VARCHAR(60) NOT NULL,
        accion VARCHAR(60) NOT NULL,
        tipo_entidad VARCHAR(50),
        id_entidad VARCHAR(64),
        datos_antes JSONB,
        datos_despues JSONB,
        ip_origen VARCHAR(45),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_auditoria_modulo_fecha ON auditoria_universal(modulo, creado_en DESC)",
    """
    CREATE TABLE IF NOT EXISTS funciones_operativas_temporales (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        relacion_laboral_id UUID NOT NULL REFERENCES relaciones_laborales(id) ON DELETE CASCADE,
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT REFERENCES sucursales(id),
        unidad_operativa_id INT REFERENCES unidades_operativas(id),
        funcion_operativa VARCHAR(40) NOT NULL CHECK (
            funcion_operativa IN (
                'COSECHADOR', 'JORNALERO', 'SUPERVISOR', 'PESADOR', 'CHALAN',
                'APUNTADOR', 'EMPACADOR', 'TRASPLANTE', 'TECNICO_CAMPO', 'OTRO'
            )
        ),
        fecha_inicio DATE NOT NULL,
        fecha_fin DATE,
        motivo TEXT NOT NULL,
        autorizado_por_usuario_id UUID REFERENCES usuarios(id),
        activa BOOLEAN NOT NULL DEFAULT TRUE,
        cerrada_en TIMESTAMPTZ,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK (fecha_fin IS NULL OR fecha_fin >= fecha_inicio)
    )
    """,
    # 4. Capa documental y codigos alternativos / QR
    """
    CREATE TABLE IF NOT EXISTS catalogo_tipos_documento (
        id SERIAL PRIMARY KEY,
        codigo VARCHAR(40) UNIQUE NOT NULL,
        nombre VARCHAR(120) NOT NULL,
        categoria VARCHAR(30) NOT NULL CHECK (
            categoria IN ('IDENTIDAD', 'LABORAL', 'OPERATIVO', 'FISCAL', 'INOCUIDAD', 'COMERCIAL', 'ACTIVO')
        ),
        requiere_vigencia BOOLEAN NOT NULL DEFAULT FALSE,
        bloquea_operacion BOOLEAN NOT NULL DEFAULT FALSE,
        prohibido_legal BOOLEAN NOT NULL DEFAULT FALSE,
        activo BOOLEAN NOT NULL DEFAULT TRUE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS documentos_entidad (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        tipo_entidad VARCHAR(30) NOT NULL CHECK (
            tipo_entidad IN (
                'EMPRESA', 'SUCURSAL', 'UNIDAD_OPERATIVA', 'LOCALIZACION',
                'PERSONA', 'RELACION_LABORAL', 'LOTE', 'ACTIVO', 'PROCESO'
            )
        ),
        id_entidad VARCHAR(64) NOT NULL,
        tipo_documento_id INT NOT NULL REFERENCES catalogo_tipos_documento(id),
        empresa_id INT REFERENCES empresas(id),
        folio_documento VARCHAR(80),
        nombre_archivo VARCHAR(200) NOT NULL,
        ruta_storage TEXT NOT NULL,
        sha256_archivo VARCHAR(64),
        estatus VARCHAR(20) NOT NULL DEFAULT 'CARGADO' CHECK (
            estatus IN ('BORRADOR', 'CARGADO', 'OBSERVADO', 'VALIDADO', 'VENCIDO', 'RECHAZADO', 'ARCHIVADO')
        ),
        fecha_emision DATE,
        fecha_vencimiento DATE,
        metadatos JSONB NOT NULL DEFAULT '{}'::jsonb,
        subido_por_usuario_id UUID REFERENCES usuarios(id),
        validado_por_usuario_id UUID REFERENCES usuarios(id),
        validado_en TIMESTAMPTZ,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_documentos_entidad_lookup ON documentos_entidad(tipo_entidad, id_entidad)",
    """
    CREATE OR REPLACE FUNCTION fn_bloquear_documento_prohibido()
    RETURNS TRIGGER AS $$
    DECLARE
        v_prohibido BOOLEAN;
        v_codigo VARCHAR(40);
    BEGIN
        SELECT prohibido_legal, codigo
          INTO v_prohibido, v_codigo
          FROM catalogo_tipos_documento
         WHERE id = NEW.tipo_documento_id;
        IF COALESCE(v_prohibido, FALSE) THEN
            RAISE EXCEPTION 'DOCUMENTO_PROHIBIDO_LEGALMENTE: El tipo % esta prohibido por politica legal.',
                v_codigo;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql
    """,
    "DROP TRIGGER IF EXISTS trg_bloquear_documento_prohibido ON documentos_entidad",
    """
    CREATE TRIGGER trg_bloquear_documento_prohibido
    BEFORE INSERT OR UPDATE ON documentos_entidad
    FOR EACH ROW EXECUTE FUNCTION fn_bloquear_documento_prohibido()
    """,
    """
    CREATE TABLE IF NOT EXISTS codigos_alternativos (
        id BIGSERIAL PRIMARY KEY,
        tipo_entidad VARCHAR(30) NOT NULL CHECK (
            tipo_entidad IN (
                'EMPRESA', 'SUCURSAL', 'UNIDAD_OPERATIVA', 'LOCALIZACION',
                'PERSONA', 'RELACION_LABORAL', 'LOTE', 'ACTIVO', 'PRODUCTO'
            )
        ),
        id_entidad VARCHAR(64) NOT NULL,
        sistema_origen VARCHAR(30) NOT NULL CHECK (
            sistema_origen IN (
                'INTERNO_QR', 'MERQRY', 'CUENTA_CONTABLE', 'PROVEEDOR',
                'SERIE', 'PLACAS', 'GSP', 'SENASICA', 'OTRO'
            )
        ),
        codigo_externo VARCHAR(120) NOT NULL,
        descripcion VARCHAR(200),
        activo BOOLEAN NOT NULL DEFAULT TRUE,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (sistema_origen, tipo_entidad, codigo_externo)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_codigos_alt_entidad ON codigos_alternativos(tipo_entidad, id_entidad)",
    # 5. ETL auditable y cuarentena
    """
    CREATE TABLE IF NOT EXISTS etl_lotes_migracion (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        fuente_nombre VARCHAR(150) NOT NULL,
        empresa_id INT NOT NULL REFERENCES empresas(id),
        ejecutado_por_usuario_id UUID REFERENCES usuarios(id),
        total_registros INT NOT NULL DEFAULT 0,
        creados INT NOT NULL DEFAULT 0,
        conciliados_curp INT NOT NULL DEFAULT 0,
        enviados_cuarentena INT NOT NULL DEFAULT 0,
        estatus VARCHAR(20) NOT NULL DEFAULT 'COMPLETADO' CHECK (
            estatus IN ('EN_PROCESO', 'COMPLETADO', 'CON_CUARENTENA', 'FALLIDO')
        ),
        resumen JSONB NOT NULL DEFAULT '{}'::jsonb,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS etl_cuarentena_identidad (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        lote_etl_id UUID NOT NULL REFERENCES etl_lotes_migracion(id) ON DELETE CASCADE,
        empresa_id INT NOT NULL REFERENCES empresas(id),
        fila_origen INT NOT NULL,
        motivo_conflicto VARCHAR(60) NOT NULL CHECK (
            motivo_conflicto IN (
                'HOMONIMO_SIN_CURP_COINCIDENTE',
                'TELEFONO_DUPLICADO_OTRA_PERSONA',
                'CURP_INVALIDO_O_AUSENTE',
                'CONFLICTO_CURP_NOMBRE',
                'OTRO_CONFLICTO'
            )
        ),
        persona_candidata_id UUID REFERENCES personas(id),
        payload_origen JSONB NOT NULL,
        estatus VARCHAR(25) NOT NULL DEFAULT 'PENDIENTE_REVISION' CHECK (
            estatus IN ('PENDIENTE_REVISION', 'RESUELTO_NUEVA_PERSONA', 'RESUELTO_VINCULADO', 'DESCARTADO')
        ),
        resuelto_por_usuario_id UUID REFERENCES usuarios(id),
        resuelto_en TIMESTAMPTZ,
        notas_resolucion TEXT,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for tbl in [
        "etl_cuarentena_identidad",
        "etl_lotes_migracion",
        "codigos_alternativos",
        "documentos_entidad",
        "catalogo_tipos_documento",
        "funciones_operativas_temporales",
        "auditoria_universal",
        "nips_personal",
        "usuarios_roles",
        "usuarios",
        "roles_permisos",
        "permisos",
        "roles",
        "relaciones_laborales",
        "personas",
        "localizaciones_fisicas",
        "areas",
        "unidades_operativas",
        "sucursal_funciones",
        "sucursales",
        "empresas",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
