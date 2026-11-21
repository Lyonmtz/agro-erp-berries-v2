"""Fase 3A: Sync Idempotency/Fencing Durable, Recepcion Multi-Camion/Bin, Coordinador Norte/Sur y CLOSE_PERSON_DAY.

Revision ID: 0003_fase3a_trasplante
Revises: 0002_fase1_core_org
Create Date: 2026-11-21 15:45:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_fase3a_trasplante"
down_revision: Union[str, None] = "0002_fase1_core_org"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS sync_idempotency_log (
        client_command_id UUID PRIMARY KEY,
        command_type VARCHAR(60) NOT NULL,
        actor_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        empresa_id INT REFERENCES empresas(id),
        payload_sha256 VARCHAR(64) NOT NULL,
        http_status INT NOT NULL DEFAULT 200,
        committed_ack_json JSONB NOT NULL,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sync_command_fences (
        client_command_id UUID PRIMARY KEY,
        fenced_by_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        motivo TEXT NOT NULL,
        fenced_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trasplante_programacion_llegadas (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT NOT NULL REFERENCES sucursales(id),
        unidad_operativa_id INT NOT NULL REFERENCES unidades_operativas(id),
        orden_compra_ref VARCHAR(60) NOT NULL,
        numero_camion_plan INT NOT NULL CHECK (numero_camion_plan > 0),
        proveedor VARCHAR(120) NOT NULL,
        variedad_id INT REFERENCES variedades_cultivo(id),
        unidad_planta VARCHAR(30) NOT NULL CHECK (
            unidad_planta IN (
                'PLANTS', 'CANES', 'GRADE_A', 'SINGLES',
                'CHAROLA', 'MACETA', 'RAIZ_DESNUDA', 'CEPELLON'
            )
        ),
        cantidad_documental INT NOT NULL CHECK (cantidad_documental > 0),
        bins_esperados INT CHECK (bins_esperados IS NULL OR bins_esperados > 0),
        cajas_plasticas_retornables_esperadas INT CHECK (
            cajas_plasticas_retornables_esperadas IS NULL OR cajas_plasticas_retornables_esperadas >= 0
        ),
        fecha_arribo_estimada DATE NOT NULL,
        fuente_documental TEXT,
        plan_version INT NOT NULL DEFAULT 1,
        mapping_invalidado BOOLEAN NOT NULL DEFAULT FALSE,
        estatus VARCHAR(25) NOT NULL DEFAULT 'PROGRAMADO' CHECK (
            estatus IN ('PROGRAMADO', 'ARRIBADO', 'CANCELADO')
        ),
        creado_por_usuario_id UUID REFERENCES usuarios(id),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trasplante_camiones_lotes (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT NOT NULL REFERENCES sucursales(id),
        unidad_operativa_id INT NOT NULL REFERENCES unidades_operativas(id),
        programacion_id UUID REFERENCES trasplante_programacion_llegadas(id),
        programacion_version_snapshot INT,
        codigo_camion VARCHAR(50) NOT NULL,
        guia_remision VARCHAR(80),
        placas_transporte VARCHAR(30),
        chofer_nombre VARCHAR(120),
        proveedor VARCHAR(120) NOT NULL,
        variedad_id INT REFERENCES variedades_cultivo(id),
        cajas_plasticas_recibidas INT NOT NULL DEFAULT 0 CHECK (cajas_plasticas_recibidas >= 0),
        cajas_plasticas_devueltas INT NOT NULL DEFAULT 0 CHECK (cajas_plasticas_devueltas >= 0),
        estatus VARCHAR(30) NOT NULL DEFAULT 'DECLARED' CHECK (
            estatus IN ('DECLARED', 'RECEIVING', 'FINISHED_OPERATIONAL', 'FINALIZED')
        ),
        verified BOOLEAN NOT NULL DEFAULT FALSE,
        declarado_por_usuario_id UUID REFERENCES usuarios(id),
        declarado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finalizado_operativo_en TIMESTAMPTZ,
        finalizado_recibo_por_usuario_id UUID REFERENCES usuarios(id),
        finalizado_recibo_en TIMESTAMPTZ,
        notas_cierre TEXT,
        UNIQUE (empresa_id, codigo_camion)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trasplante_bins (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        camion_lote_id UUID NOT NULL REFERENCES trasplante_camiones_lotes(id) ON DELETE CASCADE,
        empresa_id INT NOT NULL REFERENCES empresas(id),
        unidad_operativa_id INT NOT NULL REFERENCES unidades_operativas(id),
        bin_code VARCHAR(40) NOT NULL,
        unidad_planta VARCHAR(30) NOT NULL CHECK (
            unidad_planta IN (
                'PLANTS', 'CANES', 'GRADE_A', 'SINGLES',
                'CHAROLA', 'MACETA', 'RAIZ_DESNUDA', 'CEPELLON'
            )
        ),
        cantidad_recibida INT NOT NULL CHECK (cantidad_recibida > 0),
        cantidad_aceptada INT CHECK (cantidad_aceptada IS NULL OR cantidad_aceptada >= 0),
        cantidad_rechazada INT CHECK (cantidad_rechazada IS NULL OR cantidad_rechazada >= 0),
        motivo_rechazo TEXT,
        recibido_por_usuario_id UUID REFERENCES usuarios(id),
        recibido_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (camion_lote_id, bin_code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trasplante_bins_ledger (
        id BIGSERIAL PRIMARY KEY,
        bin_id UUID NOT NULL REFERENCES trasplante_bins(id) ON DELETE CASCADE,
        camion_lote_id UUID NOT NULL REFERENCES trasplante_camiones_lotes(id) ON DELETE CASCADE,
        empresa_id INT NOT NULL REFERENCES empresas(id),
        unidad_operativa_id INT NOT NULL REFERENCES unidades_operativas(id),
        unidad_planta VARCHAR(30) NOT NULL,
        tipo_evento VARCHAR(30) NOT NULL CHECK (
            tipo_evento IN ('BIN_RECEIVE', 'BIN_RELEASE', 'TRANSPLANT_CONSUME', 'BIN_REJECT_FINAL')
        ),
        cantidad INT NOT NULL CHECK (cantidad >= 0),
        referencia_id VARCHAR(64),
        actor_usuario_id UUID REFERENCES usuarios(id),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_bins_ledger_bin ON trasplante_bins_ledger(bin_id, tipo_evento)",
    """
    CREATE TABLE IF NOT EXISTS trasplante_asignaciones (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT NOT NULL REFERENCES sucursales(id),
        unidad_operativa_id INT NOT NULL REFERENCES unidades_operativas(id),
        fecha DATE NOT NULL,
        camion_lote_id UUID NOT NULL REFERENCES trasplante_camiones_lotes(id),
        bin_id UUID NOT NULL REFERENCES trasplante_bins(id),
        lote_id INT NOT NULL REFERENCES lotes_produccion(id),
        tunel_numero INT NOT NULL CHECK (tunel_numero > 0),
        equipo_lado VARCHAR(10) NOT NULL CHECK (equipo_lado IN ('NORTE', 'SUR')),
        linea_inicio INT NOT NULL CHECK (linea_inicio > 0),
        linea_fin INT NOT NULL CHECK (linea_fin >= linea_inicio),
        funcion_codigo VARCHAR(20) NOT NULL CHECK (
            funcion_codigo IN ('SUPPLY', 'MOVE', 'TRANSPLANT', 'CLIPS', 'BARRER')
        ),
        estatus VARCHAR(20) NOT NULL DEFAULT 'ASSIGNED' CHECK (
            estatus IN ('ASSIGNED', 'RUNNING', 'PAUSED', 'FINISHED', 'CANCELLED')
        ),
        cross_batch_continuation_of UUID REFERENCES trasplante_asignaciones(id),
        supervisor_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_trasplante_asig_rango
        ON trasplante_asignaciones(empresa_id, lote_id, tunel_numero, equipo_lado, funcion_codigo)
        WHERE estatus IN ('ASSIGNED', 'RUNNING', 'PAUSED', 'FINISHED')
    """,
    """
    CREATE TABLE IF NOT EXISTS trasplante_asignacion_participantes (
        asignacion_id UUID NOT NULL REFERENCES trasplante_asignaciones(id) ON DELETE CASCADE,
        persona_id UUID NOT NULL REFERENCES personas(id),
        activo BOOLEAN NOT NULL DEFAULT TRUE,
        agregado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (asignacion_id, persona_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_trasplante_part_persona ON trasplante_asignacion_participantes(persona_id) WHERE activo = TRUE",
    """
    CREATE TABLE IF NOT EXISTS trasplante_segmentos_tiempo (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        asignacion_id UUID NOT NULL REFERENCES trasplante_asignaciones(id) ON DELETE CASCADE,
        funcion_codigo VARCHAR(20) NOT NULL CHECK (
            funcion_codigo IN ('SUPPLY', 'MOVE', 'TRANSPLANT', 'CLIPS', 'BARRER')
        ),
        participantes_persona_ids JSONB NOT NULL,
        inicio_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        fin_en TIMESTAMPTZ,
        minutos_activos NUMERIC(8,2) GENERATED ALWAYS AS (
            CASE
                WHEN fin_en IS NOT NULL THEN ROUND(EXTRACT(EPOCH FROM (fin_en - inicio_en)) / 60.0, 2)
                ELSE NULL
            END
        ) STORED,
        motivo_cambio VARCHAR(80),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trasplante_produccion_lineas (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        asignacion_id UUID NOT NULL REFERENCES trasplante_asignaciones(id) ON DELETE CASCADE,
        camion_lote_id UUID NOT NULL REFERENCES trasplante_camiones_lotes(id),
        bin_id UUID NOT NULL REFERENCES trasplante_bins(id),
        lote_id INT NOT NULL REFERENCES lotes_produccion(id),
        tunel_numero INT NOT NULL,
        equipo_lado VARCHAR(10) NOT NULL CHECK (equipo_lado IN ('NORTE', 'SUR')),
        linea_inicio INT NOT NULL,
        linea_fin INT NOT NULL,
        unidad_planta VARCHAR(30) NOT NULL,
        cantidad_trasplantada INT NOT NULL CHECK (cantidad_trasplantada > 0),
        participantes_count INT NOT NULL CHECK (participantes_count > 0),
        registrado_por_usuario_id UUID REFERENCES usuarios(id),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trasplante_review_tokens (
        token UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        actor_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        persona_id UUID NOT NULL REFERENCES personas(id),
        camion_lote_id UUID NOT NULL REFERENCES trasplante_camiones_lotes(id),
        fecha DATE NOT NULL,
        snapshot_sha256 VARCHAR(64) NOT NULL,
        usado BOOLEAN NOT NULL DEFAULT FALSE,
        expira_en TIMESTAMPTZ NOT NULL,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS trasplante_cierres_persona_dia (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        unidad_operativa_id INT NOT NULL REFERENCES unidades_operativas(id),
        persona_id UUID NOT NULL REFERENCES personas(id),
        camion_lote_id UUID NOT NULL REFERENCES trasplante_camiones_lotes(id),
        fecha DATE NOT NULL,
        review_token_id UUID NOT NULL REFERENCES trasplante_review_tokens(token),
        total_asignaciones_cerradas INT NOT NULL DEFAULT 0,
        total_minutos_participacion NUMERIC(10,2) NOT NULL DEFAULT 0,
        total_plantas_equipo INT NOT NULL DEFAULT 0,
        es_pagable BOOLEAN NOT NULL DEFAULT FALSE CHECK (es_pagable = FALSE),
        cerrado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        cerrado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (persona_id, camion_lote_id, fecha)
    )
    """,
    """
    INSERT INTO permisos (codigo, modulo, descripcion) VALUES
        ('campo.elegibilidad.leer',     'operacion_campo',      'Consultar proyeccion minima DailyEligibleWorker.v0.1'),
        ('trasplante.programar',        'trasplante_recepcion', 'Crear y editar programacion documental de llegadas'),
        ('trasplante.recepcionar',      'trasplante_recepcion', 'Declarar camiones, recibir y liberar bins'),
        ('trasplante.finalizar',        'trasplante_recepcion', 'Ejecutar FINISH_TRUCK y FINALIZE_RECEIPT con conciliacion'),
        ('trasplante.operar',           'trasplante_recepcion', 'Crear asignaciones Norte/Sur, segmentos, cambios y produccion'),
        ('trasplante.cerrar_persona_dia','trasplante_recepcion','Generar reviewToken y ejecutar CLOSE_PERSON_DAY'),
        ('sync.fencing',                'sync_offline',         'Cercar commandIds offline pendientes (DURABLE_COMMAND_FENCE)')
    ON CONFLICT (codigo) DO UPDATE SET
        modulo      = EXCLUDED.modulo,
        descripcion = EXCLUDED.descripcion
    """,
    """
    INSERT INTO roles_permisos (rol_id, permiso_id)
    SELECT r.id, p.id
    FROM roles r
    JOIN permisos p ON (
        r.codigo IN ('DIRECCION_GENERAL', 'ADMIN_SISTEMA')
        OR (r.codigo = 'GERENTE_OPERACIONES' AND p.codigo IN (
            'campo.elegibilidad.leer', 'trasplante.programar', 'trasplante.recepcionar',
            'trasplante.finalizar', 'trasplante.operar', 'trasplante.cerrar_persona_dia', 'sync.fencing'
        ))
        OR (r.codigo = 'SUPERVISOR_CAMPO' AND p.codigo IN (
            'campo.elegibilidad.leer', 'trasplante.recepcionar', 'trasplante.operar',
            'trasplante.cerrar_persona_dia', 'sync.fencing'
        ))
        OR (r.codigo = 'PESADOR_CAMPO' AND p.codigo IN (
            'campo.elegibilidad.leer', 'trasplante.recepcionar', 'trasplante.operar'
        ))
        OR (r.codigo = 'JEFE_RH' AND p.codigo IN ('campo.elegibilidad.leer'))
    )
    ON CONFLICT DO NOTHING
    """,
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for tbl in [
        "trasplante_cierres_persona_dia",
        "trasplante_review_tokens",
        "trasplante_produccion_lineas",
        "trasplante_segmentos_tiempo",
        "trasplante_asignacion_participantes",
        "trasplante_asignaciones",
        "trasplante_bins_ledger",
        "trasplante_bins",
        "trasplante_camiones_lotes",
        "trasplante_programacion_llegadas",
        "sync_command_fences",
        "sync_idempotency_log",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
