-- ============================================================================
-- 10_schema_merqry_writer_outbox.sql
-- Scaffolding seguro para escritura controlada futura hacia Merqry (APAGADO
-- POR DEFECTO via MERQRY_WRITE_ENABLED=false).
--
-- Candados fisicos a nivel PostgreSQL:
--   1. circuito_pago restringido fisicamente a 'IMSS_MERQRY' (bloqueo duro
--      contra ESPECIAL_CONTABILIDAD / efectivo).
--   2. Lista negra fisica contra 'Nomina Especial' y movimientos prohibidos.
--   3. Idempotencia estricta (idempotency_key UNIQUE + payload_sha256) y
--      referencia trazable (merqry_ref_tag UNIQUE).
--   4. Bitacora inmutable de auditoria (merqry_write_audit_log).
-- ============================================================================

CREATE TABLE IF NOT EXISTS merqry_write_outbox (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    idempotency_key UUID UNIQUE NOT NULL,
    payload_sha256 CHAR(64) NOT NULL,
    empresa_id INT NOT NULL REFERENCES empresas(id),
    empresa_clave VARCHAR(20) NOT NULL CHECK (empresa_clave IN ('BIO', 'NFA')),
    merqry_empresa INT NOT NULL CHECK (merqry_empresa IN (1, 2)),
    merqry_sucursal INT NOT NULL CHECK (merqry_sucursal IN (1, 2)),
    -- Candado fisico: BIO <-> (1,1), NFA <-> (2,2)
    CHECK (
        (empresa_clave = 'BIO' AND merqry_empresa = 1 AND merqry_sucursal = 1)
        OR (empresa_clave = 'NFA' AND merqry_empresa = 2 AND merqry_sucursal = 2)
    ),
    -- Candado fisico de circuito: NUNCA ESPECIAL_CONTABILIDAD / efectivo
    circuito_pago VARCHAR(30) NOT NULL CHECK (circuito_pago = 'IMSS_MERQRY'),
    modulo VARCHAR(10) NOT NULL CHECK (modulo IN ('AP', 'INCID', 'NOM', 'INV', 'CONT')),
    merqry_mov VARCHAR(30) NOT NULL CHECK (
        merqry_mov NOT IN (
            'Nomina Especial', 'Liquidacion', 'Finiquito', 'Aguinaldo',
            'PTU Articulo 142', 'PTU Articulo 96', 'PTU ESP', 'SDI'
        )
    ),
    modo_objetivo VARCHAR(25) NOT NULL DEFAULT 'STAGING_DRAFT_ONLY' CHECK (
        modo_objetivo IN ('STAGING_DRAFT_ONLY', 'CONTROLLED_APPLY')
    ),
    estatus_inicial_merqry VARCHAR(15) NOT NULL CHECK (
        (modulo = 'NOM' AND estatus_inicial_merqry = 'PREVIO')
        OR (modulo <> 'NOM' AND estatus_inicial_merqry IN ('SINAPLICAR', 'PREVIO'))
    ),
    merqry_ref_tag VARCHAR(50) UNIQUE NOT NULL,
    origen_tabla VARCHAR(60),
    origen_registro_id VARCHAR(80),
    payload_json JSONB NOT NULL,
    prevalidacion_ok BOOLEAN NOT NULL DEFAULT FALSE,
    prevalidacion_resumen JSONB NOT NULL DEFAULT '{}'::jsonb,
    estado VARCHAR(30) NOT NULL DEFAULT 'PREVALIDATED' CHECK (
        estado IN (
            'PENDING',
            'PREVALIDATED',
            'STAGED_SINAPLICAR',
            'VALIDATED_IN_MERQRY',
            'APPLIED',
            'REJECTED_BY_SP',
            'FAILED_RETRYABLE',
            'CANCELLED'
        )
    ),
    intentos INT NOT NULL DEFAULT 0 CHECK (intentos >= 0),
    merqry_target_schema VARCHAR(80),
    merqry_id_generado INT,
    merqry_folio_generado VARCHAR(30),
    merqry_estatus_final VARCHAR(20),
    vg_ok VARCHAR(20),
    vg_ok_mensaje VARCHAR(255),
    sp_duration_ms INT,
    ultimo_error TEXT,
    creado_por_usuario_id UUID REFERENCES usuarios(id),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_mq_outbox_estado
    ON merqry_write_outbox (estado, modulo, empresa_id, creado_en DESC);

CREATE TABLE IF NOT EXISTS merqry_write_audit_log (
    id BIGSERIAL PRIMARY KEY,
    outbox_id UUID REFERENCES merqry_write_outbox(id) ON DELETE SET NULL,
    evento VARCHAR(40) NOT NULL,
    severidad VARCHAR(15) NOT NULL DEFAULT 'INFO' CHECK (
        severidad IN ('INFO', 'WARNING', 'BLOCKED', 'ERROR')
    ),
    circuito_intentado VARCHAR(40),
    modulo VARCHAR(15),
    merqry_mov VARCHAR(40),
    actor_usuario_id UUID REFERENCES usuarios(id),
    detalle JSONB NOT NULL DEFAULT '{}'::jsonb,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_mq_write_audit_outbox
    ON merqry_write_audit_log (outbox_id, creado_en DESC);
