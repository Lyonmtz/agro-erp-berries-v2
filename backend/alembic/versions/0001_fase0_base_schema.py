"""Fase 0 baseline: extensiones, metadatos de entorno, estructura de lotes, variedades/densidades y correccion PHI/rentabilidad.

Revision ID: 0001_fase0_base
Revises:
Create Date: 2026-11-20 23:55:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001_fase0_base"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')

    op.execute(
        """
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
        """
    )

    op.execute(
        """
        ALTER TABLE cultivos
            ADD COLUMN IF NOT EXISTS empresa_clave VARCHAR(10) NOT NULL DEFAULT 'NFA'
                CHECK (empresa_clave IN ('NFA', 'BIO')),
            ADD COLUMN IF NOT EXISTS unidades_por_caja INT NOT NULL DEFAULT 12
                CHECK (unidades_por_caja > 0),
            ADD COLUMN IF NOT EXISTS peso_real_caja_kg NUMERIC(6,3) NOT NULL DEFAULT 2.140
                CHECK (peso_real_caja_kg > 0),
            ADD COLUMN IF NOT EXISTS merma_maxima_permitida_pct NUMERIC(5,2) NOT NULL DEFAULT 10.00
                CHECK (merma_maxima_permitida_pct >= 0 AND merma_maxima_permitida_pct <= 100),
            ADD COLUMN IF NOT EXISTS cajas_por_tarima INT NOT NULL DEFAULT 200
                CHECK (cajas_por_tarima > 0),
            ADD COLUMN IF NOT EXISTS permite_cosecha_domingo BOOLEAN NOT NULL DEFAULT FALSE;
        """
    )

    op.execute(
        """
        ALTER TABLE ranchos
            ADD COLUMN IF NOT EXISTS empresa_clave VARCHAR(10) NOT NULL DEFAULT 'NFA'
                CHECK (empresa_clave IN ('NFA', 'BIO'));
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS variedades_cultivo (
            id SERIAL PRIMARY KEY,
            cultivo_id INT NOT NULL REFERENCES cultivos(id),
            codigo VARCHAR(40) UNIQUE NOT NULL,
            nombre VARCHAR(100) NOT NULL,
            cohorte VARCHAR(30) NOT NULL CHECK (
                cohorte IN ('PRIMOCANA', 'LONG_CANE', 'PERENNE', 'TEMPORAL', 'POR_CONFIRMAR')
            ),
            presentacion_planta_default VARCHAR(30) CHECK (
                presentacion_planta_default IS NULL
                OR presentacion_planta_default IN (
                    'PLANTS', 'CANES', 'GRADE_A', 'SINGLES',
                    'CHAROLA', 'MACETA', 'RAIZ_DESNUDA', 'CEPELLON'
                )
            ),
            codigo_genetico VARCHAR(40),
            casa_genetica VARCHAR(80),
            confirmado_tecnico BOOLEAN NOT NULL DEFAULT FALSE,
            fuente_documental TEXT,
            notas TEXT,
            activo BOOLEAN NOT NULL DEFAULT TRUE,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute(
        """
        ALTER TABLE lotes_produccion
            ADD COLUMN IF NOT EXISTS empresa_clave VARCHAR(10) NOT NULL DEFAULT 'NFA'
                CHECK (empresa_clave IN ('NFA', 'BIO')),
            ADD COLUMN IF NOT EXISTS tipo_estructura VARCHAR(40) NOT NULL DEFAULT 'BATICENITAL'
                CHECK (tipo_estructura IN (
                    'BATICENITAL', 'AUSTERO', 'MEDIA_TECNOLOGIA', 'ALTA_TECNOLOGIA',
                    'NAVE_ADAPTADA', 'MACRO_TUNEL', 'CAMPO_ABIERTO', 'VIVERO'
                )),
            ADD COLUMN IF NOT EXISTS nivel_tecnologia VARCHAR(30) NOT NULL DEFAULT 'MEDIA'
                CHECK (nivel_tecnologia IN ('BAJA', 'MEDIA', 'MEDIA_ALTA', 'ALTA')),
            ADD COLUMN IF NOT EXISTS origen_diseno VARCHAR(60) NOT NULL DEFAULT 'BATICENITAL_BERRIES',
            ADD COLUMN IF NOT EXISTS ancho_tunel_m NUMERIC(5,2)
                CHECK (ancho_tunel_m IS NULL OR ancho_tunel_m > 0),
            ADD COLUMN IF NOT EXISTS superficie_m2 NUMERIC(10,2)
                CHECK (superficie_m2 IS NULL OR superficie_m2 > 0),
            ADD COLUMN IF NOT EXISTS numero_tuneles INT
                CHECK (numero_tuneles IS NULL OR numero_tuneles > 0),
            ADD COLUMN IF NOT EXISTS macetas_por_linea INT
                CHECK (macetas_por_linea IS NULL OR macetas_por_linea > 0),
            ADD COLUMN IF NOT EXISTS macetas_norte INT
                CHECK (macetas_norte IS NULL OR macetas_norte >= 0),
            ADD COLUMN IF NOT EXISTS macetas_sur INT
                CHECK (macetas_sur IS NULL OR macetas_sur >= 0),
            ADD COLUMN IF NOT EXISTS total_macetas INT
                CHECK (total_macetas IS NULL OR total_macetas > 0),
            ADD COLUMN IF NOT EXISTS contenedor_tipo VARCHAR(60),
            ADD COLUMN IF NOT EXISTS variedad_id INT REFERENCES variedades_cultivo(id),
            ADD COLUMN IF NOT EXISTS notas_estructura TEXT;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS lotes_densidades_config (
            id SERIAL PRIMARY KEY,
            lote_id INT NOT NULL REFERENCES lotes_produccion(id) ON DELETE CASCADE,
            variedad_id INT REFERENCES variedades_cultivo(id),
            ciclo_agricola VARCHAR(30) NOT NULL,
            presentacion_planta VARCHAR(30) CHECK (
                presentacion_planta IS NULL
                OR presentacion_planta IN (
                    'PLANTS', 'CANES', 'GRADE_A', 'SINGLES',
                    'CHAROLA', 'MACETA', 'RAIZ_DESNUDA', 'CEPELLON'
                )
            ),
            unidad_densidad VARCHAR(35) NOT NULL DEFAULT 'PLANTAS_POR_METRO_LINEAL' CHECK (
                unidad_densidad IN (
                    'PLANTAS_POR_METRO_LINEAL', 'PLANTAS_POR_CAMA', 'PLANTAS_POR_HA',
                    'CANAS_POR_METRO_LINEAL', 'MACETAS_POR_METRO_LINEAL'
                )
            ),
            densidad_objetivo NUMERIC(10,3)
                CHECK (densidad_objetivo IS NULL OR densidad_objetivo > 0),
            plantas_por_contenedor NUMERIC(5,2)
                CHECK (plantas_por_contenedor IS NULL OR plantas_por_contenedor > 0),
            plantas_estimadas_lote INT
                CHECK (plantas_estimadas_lote IS NULL OR plantas_estimadas_lote > 0),
            umbral_merma_trasplante_pct NUMERIC(5,2)
                CHECK (umbral_merma_trasplante_pct IS NULL OR (umbral_merma_trasplante_pct >= 0 AND umbral_merma_trasplante_pct <= 100)),
            umbral_supervivencia_min_pct NUMERIC(5,2)
                CHECK (umbral_supervivencia_min_pct IS NULL OR (umbral_supervivencia_min_pct >= 0 AND umbral_supervivencia_min_pct <= 100)),
            umbral_resiembra_pct NUMERIC(5,2)
                CHECK (umbral_resiembra_pct IS NULL OR (umbral_resiembra_pct >= 0 AND umbral_resiembra_pct <= 100)),
            confirmado_tecnico BOOLEAN NOT NULL DEFAULT FALSE,
            fuente_confirmacion TEXT,
            vigente BOOLEAN NOT NULL DEFAULT TRUE,
            notas TEXT,
            creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (lote_id, ciclo_agricola)
        );
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_bloquear_lote_por_aplicacion()
        RETURNS TRIGGER AS $$
        DECLARE
            v_dias INT;
        BEGIN
            SELECT dias_intervalo_seguridad
              INTO v_dias
              FROM insumos_agricolas
             WHERE id = NEW.insumo_id;

            IF COALESCE(v_dias, 0) > 0 THEN
                UPDATE lotes_produccion
                   SET estatus_fitosanitario = 'BLOQUEADO_INTERVALO_SEGURIDAD',
                       fecha_liberacion_corte = GREATEST(
                           COALESCE(fecha_liberacion_corte, NEW.fecha_aplicacion),
                           NEW.fecha_aplicacion + (v_dias || ' days')::INTERVAL
                       )
                 WHERE id = NEW.lote_id;
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS lotes_densidades_config;")
    op.execute("ALTER TABLE lotes_produccion DROP COLUMN IF EXISTS variedad_id;")
    op.execute("DROP TABLE IF EXISTS variedades_cultivo;")
