"""Fase 3B: Cosecha Offline-First, Culturales Individuales, Movilidad vs Cajas, Cierres Concurrentes y Prenomina Semanal.

Revision ID: 0005_fase3b_cosecha_prenomina
Revises: 0004_fase2_rh_merqry
Create Date: 2026-11-21 16:30:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0005_fase3b_cosecha_prenomina"
down_revision: Union[str, None] = "0004_fase2_rh_merqry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS campo_autorizaciones_operativas (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT NOT NULL REFERENCES sucursales(id),
        unidad_operativa_id INT NOT NULL REFERENCES unidades_operativas(id),
        fecha DATE NOT NULL,
        tipo_operacion VARCHAR(30) NOT NULL CHECK (
            tipo_operacion IN ('COSECHA_VIVO', 'COSECHA_RETROACTIVA', 'COSECHA_DOMINGO', 'LABORES_CULTURALES')
        ),
        motivo TEXT NOT NULL,
        autorizado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        vigente BOOLEAN NOT NULL DEFAULT TRUE,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campo_cierres_operativos (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT REFERENCES sucursales(id),
        unidad_operativa_id INT REFERENCES unidades_operativas(id),
        fecha DATE NOT NULL,
        alcance_cierre VARCHAR(15) NOT NULL CHECK (alcance_cierre IN ('UNIDAD', 'GLOBAL')),
        estatus VARCHAR(20) NOT NULL DEFAULT 'CIERRE_TECNICO' CHECK (
            estatus IN ('CIERRE_TECNICO', 'EN_REVISION', 'AUTORIZADO', 'REABIERTO')
        ),
        total_capturas INT NOT NULL DEFAULT 0,
        total_cajas_exportacion NUMERIC(12,2) NOT NULL DEFAULT 0,
        total_cajas_nacional NUMERIC(12,2) NOT NULL DEFAULT 0,
        total_cajas_merma NUMERIC(12,2) NOT NULL DEFAULT 0,
        es_pagable BOOLEAN NOT NULL DEFAULT FALSE CHECK (es_pagable = FALSE),
        cerrado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        cerrado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK (
            (alcance_cierre = 'GLOBAL' AND unidad_operativa_id IS NULL)
            OR (alcance_cierre = 'UNIDAD' AND unidad_operativa_id IS NOT NULL)
        )
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_cierre_global_activo
        ON campo_cierres_operativos (empresa_id, fecha)
        WHERE alcance_cierre = 'GLOBAL' AND estatus <> 'REABIERTO'
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS ux_cierre_unidad_activo
        ON campo_cierres_operativos (empresa_id, unidad_operativa_id, fecha)
        WHERE alcance_cierre = 'UNIDAD' AND estatus <> 'REABIERTO'
    """,
    """
    CREATE TABLE IF NOT EXISTS campo_capturas_cosecha (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT NOT NULL REFERENCES sucursales(id),
        unidad_operativa_id INT NOT NULL REFERENCES unidades_operativas(id),
        fecha DATE NOT NULL,
        es_domingo BOOLEAN NOT NULL DEFAULT FALSE,
        lote_id INT NOT NULL REFERENCES lotes_produccion(id),
        cultivo_id INT NOT NULL REFERENCES cultivos(id),
        persona_id UUID NOT NULL REFERENCES personas(id),
        relacion_laboral_id UUID NOT NULL REFERENCES relaciones_laborales(id),
        circuito_pago VARCHAR(30) NOT NULL CHECK (
            circuito_pago IN ('IMSS_MERQRY', 'ESPECIAL_CONTABILIDAD')
        ),
        modo_captura VARCHAR(15) NOT NULL DEFAULT 'VIVO' CHECK (
            modo_captura IN ('VIVO', 'RETROACTIVA')
        ),
        autorizacion_id UUID REFERENCES campo_autorizaciones_operativas(id),
        codigo_trazabilidad_caja VARCHAR(80) UNIQUE NOT NULL,
        cajas_exportacion NUMERIC(8,2) NOT NULL DEFAULT 0 CHECK (cajas_exportacion >= 0),
        cajas_nacional NUMERIC(8,2) NOT NULL DEFAULT 0 CHECK (cajas_nacional >= 0),
        cajas_merma_rezaga NUMERIC(8,2) NOT NULL DEFAULT 0 CHECK (cajas_merma_rezaga >= 0),
        porcentaje_merma NUMERIC(5,2) NOT NULL DEFAULT 0,
        alerta_merma_7pct BOOLEAN NOT NULL DEFAULT FALSE,
        nip_confirmado BOOLEAN NOT NULL DEFAULT FALSE,
        estatus_flujo VARCHAR(20) NOT NULL DEFAULT 'CAPTURADA' CHECK (
            estatus_flujo IN (
                'CAPTURADA', 'CIERRE_TECNICO', 'EN_REVISION',
                'AUTORIZADA', 'PAGABLE', 'EXPORTADA', 'RECIBIDA'
            )
        ),
        cierre_operativo_id UUID REFERENCES campo_cierres_operativos(id),
        capturado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        revisado_por_usuario_id UUID REFERENCES usuarios(id),
        revisado_en TIMESTAMPTZ,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CHECK ((cajas_exportacion + cajas_nacional + cajas_merma_rezaga) > 0)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_capturas_cosecha_fecha_persona ON campo_capturas_cosecha(empresa_id, fecha, persona_id)",
    """
    CREATE TABLE IF NOT EXISTS campo_culturales_diarios (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT NOT NULL REFERENCES sucursales(id),
        unidad_operativa_id INT NOT NULL REFERENCES unidades_operativas(id),
        fecha DATE NOT NULL,
        lote_id INT NOT NULL REFERENCES lotes_produccion(id),
        persona_id UUID NOT NULL REFERENCES personas(id),
        relacion_laboral_id UUID NOT NULL REFERENCES relaciones_laborales(id),
        labor_codigo VARCHAR(30) NOT NULL,
        unidad_medida VARCHAR(25) NOT NULL CHECK (
            unidad_medida IN ('SURCO', 'METRO_LINEAL', 'PLANTA', 'MACETA', 'HORA', 'JORNAL', 'CAJA')
        ),
        meta_diaria NUMERIC(10,2) CHECK (meta_diaria IS NULL OR meta_diaria >= 0),
        cantidad_realizada NUMERIC(10,2) NOT NULL CHECK (cantidad_realizada > 0),
        minutos_trabajados INT NOT NULL CHECK (minutos_trabajados > 0),
        minutos_pausa INT NOT NULL DEFAULT 0 CHECK (minutos_pausa >= 0),
        observaciones TEXT,
        formula_pago_aplicable VARCHAR(35) NOT NULL DEFAULT 'PENDIENTE_FORMULA_DIRECCION' CHECK (
            formula_pago_aplicable IN ('JORNAL_BASE', 'PENDIENTE_FORMULA_DIRECCION')
        ),
        estatus_revision VARCHAR(20) NOT NULL DEFAULT 'CAPTURADA' CHECK (
            estatus_revision IN ('CAPTURADA', 'EN_REVISION', 'AUTORIZADA', 'RECHAZADA')
        ),
        capturado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        revisado_por_usuario_id UUID REFERENCES usuarios(id),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campo_movilidad_personas (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        persona_id UUID NOT NULL REFERENCES personas(id),
        relacion_laboral_id UUID NOT NULL REFERENCES relaciones_laborales(id),
        fecha DATE NOT NULL,
        unidad_origen_id INT NOT NULL REFERENCES unidades_operativas(id),
        lote_origen_id INT REFERENCES lotes_produccion(id),
        unidad_destino_id INT NOT NULL REFERENCES unidades_operativas(id),
        lote_destino_id INT REFERENCES lotes_produccion(id),
        estatus_movilidad VARCHAR(25) NOT NULL DEFAULT 'ENTREGA' CHECK (
            estatus_movilidad IN ('ENTREGA', 'SALIDA', 'TRASLADO_AUTORIZADO', 'NUEVA_ASIGNACION', 'CANCELADO')
        ),
        motivo TEXT NOT NULL,
        autorizado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS campo_traslados_cajas (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        sucursal_id INT NOT NULL REFERENCES sucursales(id),
        unidad_operativa_id INT NOT NULL REFERENCES unidades_operativas(id),
        fecha DATE NOT NULL,
        lote_origen_id INT NOT NULL REFERENCES lotes_produccion(id),
        cultivo_id INT NOT NULL REFERENCES cultivos(id),
        folio_remision VARCHAR(60) UNIQUE NOT NULL,
        cantidad_cajas NUMERIC(10,2) NOT NULL CHECK (cantidad_cajas > 0),
        calidad_fruta VARCHAR(20) NOT NULL DEFAULT 'EXPORTACION' CHECK (
            calidad_fruta IN ('EXPORTACION', 'NACIONAL', 'PROCESO_REZAGA')
        ),
        destino_empaque VARCHAR(100) NOT NULL,
        vehiculo_clave VARCHAR(40),
        estatus_traslado VARCHAR(25) NOT NULL DEFAULT 'RECOLECCION_PARCIAL' CHECK (
            estatus_traslado IN ('RECOLECCION_PARCIAL', 'TRASLADO', 'RECEPCION_EMPAQUE', 'EMPACADO', 'DESPACHO')
        ),
        registrado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prenomina_reglas_semanales (
        id SERIAL PRIMARY KEY,
        empresa_id INT NOT NULL REFERENCES empresas(id),
        cultivo_id INT REFERENCES cultivos(id),
        nombre_regla VARCHAR(100) NOT NULL,
        tarifa_caja_ls NUMERIC(10,2) NOT NULL DEFAULT 28.00 CHECK (tarifa_caja_ls >= 0),
        domingo_umbral_cajas NUMERIC(8,2) NOT NULL DEFAULT 10.00 CHECK (domingo_umbral_cajas >= 0),
        domingo_tarifa_base NUMERIC(10,2) NOT NULL DEFAULT 28.00 CHECK (domingo_tarifa_base >= 0),
        domingo_tarifa_excedente NUMERIC(10,2) NOT NULL DEFAULT 40.00 CHECK (domingo_tarifa_excedente >= 0),
        minimo_semanal_garantizado NUMERIC(10,2) NOT NULL DEFAULT 2350.00 CHECK (minimo_semanal_garantizado >= 0),
        dias_minimos_para_garantia INT NOT NULL DEFAULT 1 CHECK (dias_minimos_para_garantia BETWEEN 1 AND 7),
        alerta_merma_pct NUMERIC(5,2) NOT NULL DEFAULT 7.00 CHECK (alerta_merma_pct >= 0 AND alerta_merma_pct <= 100),
        activa BOOLEAN NOT NULL DEFAULT TRUE,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (empresa_id, nombre_regla)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prenomina_semanal (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        empresa_id INT NOT NULL REFERENCES empresas(id),
        anio INT NOT NULL CHECK (anio BETWEEN 2024 AND 2100),
        semana_seah INT NOT NULL CHECK (semana_seah BETWEEN 1 AND 53),
        fecha_inicio DATE NOT NULL,
        fecha_fin DATE NOT NULL,
        regla_id INT NOT NULL REFERENCES prenomina_reglas_semanales(id),
        estatus VARCHAR(20) NOT NULL DEFAULT 'EN_REVISION' CHECK (
            estatus IN ('BORRADOR', 'EN_REVISION', 'AUTORIZADA', 'PAGABLE', 'EXPORTADA', 'RECIBIDA')
        ),
        total_trabajadores INT NOT NULL DEFAULT 0,
        total_imss_merqry NUMERIC(14,2) NOT NULL DEFAULT 0,
        total_especial_contabilidad NUMERIC(14,2) NOT NULL DEFAULT 0,
        total_general NUMERIC(14,2) NOT NULL DEFAULT 0,
        hash_cierre_inmutable VARCHAR(64),
        generado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
        autorizado_por_usuario_id UUID REFERENCES usuarios(id),
        autorizado_en TIMESTAMPTZ,
        cerrado_inmutable_en TIMESTAMPTZ,
        creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (empresa_id, anio, semana_seah),
        CHECK (fecha_fin >= fecha_inicio)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS prenomina_semanal_detalle (
        id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
        prenomina_semanal_id UUID NOT NULL REFERENCES prenomina_semanal(id) ON DELETE CASCADE,
        persona_id UUID NOT NULL REFERENCES personas(id),
        relacion_laboral_id UUID NOT NULL REFERENCES relaciones_laborales(id),
        numero_empleado VARCHAR(30) NOT NULL,
        circuito_pago VARCHAR(30) NOT NULL CHECK (
            circuito_pago IN ('IMSS_MERQRY', 'ESPECIAL_CONTABILIDAD')
        ),
        dias_trabajados INT NOT NULL DEFAULT 0,
        cajas_ls NUMERIC(10,2) NOT NULL DEFAULT 0,
        cajas_domingo NUMERIC(10,2) NOT NULL DEFAULT 0,
        cajas_merma NUMERIC(10,2) NOT NULL DEFAULT 0,
        porcentaje_merma_semanal NUMERIC(5,2) NOT NULL DEFAULT 0,
        alerta_merma BOOLEAN NOT NULL DEFAULT FALSE,
        pago_ls NUMERIC(12,2) NOT NULL DEFAULT 0,
        pago_domingo_base NUMERIC(12,2) NOT NULL DEFAULT 0,
        pago_domingo_excedente NUMERIC(12,2) NOT NULL DEFAULT 0,
        subtotal_destajo NUMERIC(12,2) NOT NULL DEFAULT 0,
        ajuste_minimo_semanal NUMERIC(12,2) NOT NULL DEFAULT 0,
        total_pagar NUMERIC(12,2) NOT NULL DEFAULT 0,
        UNIQUE (prenomina_semanal_id, relacion_laboral_id)
    )
    """,
    """
    INSERT INTO prenomina_reglas_semanales (
        empresa_id, cultivo_id, nombre_regla, tarifa_caja_ls, domingo_umbral_cajas,
        domingo_tarifa_base, domingo_tarifa_excedente, minimo_semanal_garantizado,
        dias_minimos_para_garantia, alerta_merma_pct, activa
    )
    SELECT e.id, NULL, 'SEAH Estándar Semanal 2026 (' || e.clave || ')',
           28.00, 10.00, 28.00, 40.00, 2350.00, 1, 7.00, TRUE
    FROM empresas e
    ON CONFLICT (empresa_id, nombre_regla) DO NOTHING
    """,
    """
    INSERT INTO permisos (codigo, modulo, descripcion) VALUES
        ('campo.cosecha.cerrar',       'cosecha_tablet', 'Ejecutar cierres operativos por unidad o cierre global'),
        ('campo.cosecha.revisar',      'cosecha_tablet', 'Revisar y autorizar capturas en oficina'),
        ('campo.culturales.capturar',  'cosecha_tablet', 'Capturar labores culturales individuales diarias'),
        ('campo.movilidad.gestionar',  'cosecha_tablet', 'Registrar movilidad de personas y traslados de cajas por separado'),
        ('prenomina.calcular',         'prenomina',      'Generar y revisar prenómina semanal L-S + Domingo + mínimo'),
        ('prenomina.autorizar_cerrar', 'prenomina',      'Autorizar, volver pagable y cerrar inmutablemente la prenómina semanal')
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
            'campo.cosecha.cerrar', 'campo.cosecha.revisar', 'campo.culturales.capturar',
            'campo.movilidad.gestionar', 'prenomina.calcular', 'prenomina.autorizar_cerrar'
        ))
        OR (r.codigo = 'JEFE_RH' AND p.codigo IN (
            'campo.cosecha.revisar', 'prenomina.calcular', 'prenomina.autorizar_cerrar'
        ))
        OR (r.codigo = 'SUPERVISOR_CAMPO' AND p.codigo IN (
            'campo.cosecha.cerrar', 'campo.culturales.capturar', 'campo.movilidad.gestionar'
        ))
        OR (r.codigo = 'PESADOR_CAMPO' AND p.codigo IN (
            'campo.culturales.capturar', 'campo.movilidad.gestionar'
        ))
        OR (r.codigo = 'CONTABILIDAD' AND p.codigo IN ('prenomina.calcular'))
    )
    ON CONFLICT DO NOTHING
    """,
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for tbl in [
        "prenomina_semanal_detalle",
        "prenomina_semanal",
        "prenomina_reglas_semanales",
        "campo_traslados_cajas",
        "campo_movilidad_personas",
        "campo_culturales_diarios",
        "campo_capturas_cosecha",
        "campo_cierres_operativos",
        "campo_autorizaciones_operativas",
    ]:
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
