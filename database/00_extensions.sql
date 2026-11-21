-- ============================================================================
-- 00_extensions.sql
-- Extensiones base de PostgreSQL 16 y metadatos de entorno para guarda de DB
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Metadatos de entorno de base de datos.
-- Regla estricta: ninguna suite destructiva puede operar si db_environment
-- no es explicitamente 'DISPOSABLE_TEST' (nunca inferir por nombre de BD).
CREATE TABLE IF NOT EXISTS app_db_metadata (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    db_environment VARCHAR(32) NOT NULL CHECK (
        db_environment IN ('DEVELOPMENT', 'STAGING', 'PRODUCTION', 'DISPOSABLE_TEST')
    ),
    app_name VARCHAR(80) NOT NULL DEFAULT 'agro-erp-berries-v2',
    merqry_integration_mode VARCHAR(20) NOT NULL DEFAULT 'READ_ONLY' CHECK (
        merqry_integration_mode = 'READ_ONLY'
    ),
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO app_db_metadata (id, db_environment, app_name, merqry_integration_mode, notes)
VALUES (
    1,
    'DEVELOPMENT',
    'agro-erp-berries-v2',
    'READ_ONLY',
    'Base de datos de desarrollo agro_berries_erp. Protegida contra suites destructivas.'
)
ON CONFLICT (id) DO NOTHING;
