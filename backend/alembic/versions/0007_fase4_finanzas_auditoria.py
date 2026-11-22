"""Fase 4: Control Financiero, Presupuestos, Conciliacion Operativa Multi-Etapa y Auditoria Avanzada.

Revision ID: 0007_fase4_finanzas_auditoria
Revises: 0006_merqry_writer_outbox
Create Date: 2026-11-21 21:20:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007_fase4_finanzas_auditoria"
down_revision: Union[str, None] = "0006_merqry_writer_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS fin_presupuestos_operativos (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        unidad_operativa_id INT REFERENCES unidades_operativas(id),
        anio INT NOT NULL CHECK (anio BETWEEN 2024 AND 2100),
        periodo_clave VARCHAR(20) NOT NULL,
        rubro VARCHAR(30) NOT NULL CHECK (
            rubro IN (
                'MANO_OBRA_IMSS',
                'MANO_OBRA_ESPECIAL',
                'INSUMOS_FITO',
                'TRASPLANTE',
                'EMPAQUE',
                'LOGISTICA'
            )
        ),
        monto_presupuestado NUMERIC(14,2) NOT NULL CHECK (monto_presupuestado >= 0),
        notas TEXT,
        creado_por_usuario_id UUID REFERENCES usuarios(id),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_fin_presupuesto_scope
        ON fin_presupuestos_operativos (
            empresa_id,
            COALESCE(unidad_operativa_id, 0),
            anio,
            periodo_clave,
            rubro
        )
    """,
    """
    CREATE TABLE IF NOT EXISTS fin_gastos_operativos (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT REFERENCES sucursales(id),
        unidad_operativa_id INT REFERENCES unidades_operativas(id),
        lote_id INT REFERENCES lotes_produccion(id),
        fecha DATE NOT NULL,
        periodo_clave VARCHAR(20) NOT NULL,
        rubro VARCHAR(30) NOT NULL CHECK (
            rubro IN (
                'MANO_OBRA_IMSS',
                'MANO_OBRA_ESPECIAL',
                'INSUMOS_FITO',
                'TRASPLANTE',
                'EMPAQUE',
                'LOGISTICA'
            )
        ),
        circuito_origen VARCHAR(30) NOT NULL CHECK (
            circuito_origen IN ('IMSS_MERQRY', 'ESPECIAL_CONTABILIDAD', 'OPERACION_GENERAL')
        ),
        CHECK (
            (rubro = 'MANO_OBRA_IMSS' AND circuito_origen = 'IMSS_MERQRY')
            OR (rubro = 'MANO_OBRA_ESPECIAL' AND circuito_origen = 'ESPECIAL_CONTABILIDAD')
            OR (rubro NOT IN ('MANO_OBRA_IMSS', 'MANO_OBRA_ESPECIAL'))
        ),
        concepto VARCHAR(160) NOT NULL,
        monto NUMERIC(14,2) NOT NULL CHECK (monto > 0),
        folio_comprobante VARCHAR(80),
        creado_por_usuario_id UUID REFERENCES usuarios(id),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_fin_gastos_emp_fecha
        ON fin_gastos_operativos (empresa_id, fecha, rubro, circuito_origen)
    """,
    """
    CREATE TABLE IF NOT EXISTS fin_conciliaciones_operativas (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        fecha_inicio DATE NOT NULL,
        fecha_fin DATE NOT NULL,
        CHECK (fecha_fin >= fecha_inicio),
        estatus VARCHAR(25) NOT NULL DEFAULT 'BORRADOR' CHECK (
            estatus IN ('BORRADOR', 'CONCILIADA', 'CERRADA_AUDITORIA')
        ),
        cajas_campo_exportacion NUMERIC(12,2) NOT NULL DEFAULT 0,
        cajas_campo_nacional NUMERIC(12,2) NOT NULL DEFAULT 0,
        cajas_campo_merma NUMERIC(12,2) NOT NULL DEFAULT 0,
        cajas_trasladadas_empaque NUMERIC(12,2) NOT NULL DEFAULT 0,
        delta_cajas_campo_vs_empaque NUMERIC(12,2) NOT NULL DEFAULT 0,
        total_mo_imss_merqry NUMERIC(14,2) NOT NULL DEFAULT 0,
        total_mo_especial_contabilidad NUMERIC(14,2) NOT NULL DEFAULT 0,
        total_insumos_fito NUMERIC(14,2) NOT NULL DEFAULT 0,
        total_otros_gastos NUMERIC(14,2) NOT NULL DEFAULT 0,
        costo_total_directo NUMERIC(14,2) NOT NULL DEFAULT 0,
        costo_mo_por_caja_exportable NUMERIC(10,4) NOT NULL DEFAULT 0,
        detalle_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        hash_conciliacion_sha256 CHAR(64) NOT NULL,
        creado_por_usuario_id UUID REFERENCES usuarios(id),
        cerrado_por_usuario_id UUID REFERENCES usuarios(id),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        cerrado_en TIMESTAMPTZ
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_fin_conciliacion_emp_fechas
        ON fin_conciliaciones_operativas (empresa_id, fecha_inicio, fecha_fin, creado_en DESC)
    """,
    """
    INSERT INTO permisos (codigo, modulo, descripcion) VALUES
        ('finanzas.presupuesto.gestionar', 'finanzas_auditoria', 'Crear y consultar presupuestos y gastos operativos'),
        ('finanzas.conciliar',             'finanzas_auditoria', 'Ejecutar y cerrar conciliaciones operativas multi-etapa'),
        ('finanzas.reportes.leer',         'finanzas_auditoria', 'Consultar reportes ejecutivos financieros y de desviaciones')
    ON CONFLICT (codigo) DO UPDATE SET
        modulo      = EXCLUDED.modulo,
        descripcion = EXCLUDED.descripcion
    """,
    """
    INSERT INTO roles_permisos (rol_id, permiso_id)
    SELECT r.id, p.id
    FROM roles r
    JOIN permisos p ON (
        (r.codigo IN ('DIRECCION_GENERAL', 'ADMIN_SISTEMA', 'CONTABILIDAD') AND p.codigo IN (
            'finanzas.presupuesto.gestionar', 'finanzas.conciliar', 'finanzas.reportes.leer', 'auditoria.leer'
        ))
        OR (r.codigo = 'GERENTE_OPERACIONES' AND p.codigo IN (
            'finanzas.presupuesto.gestionar', 'finanzas.reportes.leer'
        ))
        OR (r.codigo = 'JEFE_RH' AND p.codigo IN (
            'finanzas.reportes.leer'
        ))
    )
    ON CONFLICT DO NOTHING
    """,
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fin_conciliaciones_operativas")
    op.execute("DROP TABLE IF EXISTS fin_gastos_operativos")
    op.execute("DROP TABLE IF EXISTS fin_presupuestos_operativos")
