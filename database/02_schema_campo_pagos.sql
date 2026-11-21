-- ============================================================================
-- 02_schema_campo_pagos.sql
-- Evolucion estructural de campo, cultivos, tecnologia de invernadero,
-- variedades/cohortes y densidades de plantacion (preparado para Opcion B:
-- Fase 0 -> Fase 1 -> Fase 3A Trasplante Multi-Camion -> Fase 2 -> Fase 3B)
-- ============================================================================

-- 1. Enriquecimiento de cultivos con parametros comerciales/operativos reales
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

-- 2. Empresa propietaria en ranchos (puente hacia jerarquia de 7 niveles en Fase 1)
ALTER TABLE ranchos
    ADD COLUMN IF NOT EXISTS empresa_clave VARCHAR(10) NOT NULL DEFAULT 'NFA'
        CHECK (empresa_clave IN ('NFA', 'BIO'));

-- 3. Catalogo de variedades y cohortes por cultivo
-- Nota tecnica: presentacion_planta_default registra la unidad documental/fisica
-- esperada al arribo (PLANTS, CANES, GRADE_A, SINGLES, CHAROLA, MACETA,
-- RAIZ_DESNUDA, CEPELLON) sin aplicar ningun factor de conversion implicito.
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

CREATE INDEX IF NOT EXISTS idx_variedades_cultivo_id ON variedades_cultivo(cultivo_id);

-- 4. Soporte de estructura, tecnologia, contenedores y origen de diseno en lotes_produccion
ALTER TABLE lotes_produccion
    ADD COLUMN IF NOT EXISTS empresa_clave VARCHAR(10) NOT NULL DEFAULT 'NFA'
        CHECK (empresa_clave IN ('NFA', 'BIO')),
    ADD COLUMN IF NOT EXISTS tipo_estructura VARCHAR(40) NOT NULL DEFAULT 'BATICENITAL'
        CHECK (tipo_estructura IN (
            'BATICENITAL',
            'AUSTERO',
            'MEDIA_TECNOLOGIA',
            'ALTA_TECNOLOGIA',
            'NAVE_ADAPTADA',
            'MACRO_TUNEL',
            'CAMPO_ABIERTO',
            'VIVERO'
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

CREATE INDEX IF NOT EXISTS idx_lotes_empresa_cultivo ON lotes_produccion(empresa_clave, cultivo_id);

-- 5. Configuracion de densidades de plantacion y umbrales de trasplante/resiembra
-- Invariante de dominio (campo): los valores no confirmados con direccion tecnica
-- permanecen en NULL hasta validacion explicita (cero suposiciones silenciosas).
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
            'PLANTAS_POR_METRO_LINEAL',
            'PLANTAS_POR_CAMA',
            'PLANTAS_POR_HA',
            'CANAS_POR_METRO_LINEAL',
            'MACETAS_POR_METRO_LINEAL'
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

CREATE INDEX IF NOT EXISTS idx_lotes_densidades_lote ON lotes_densidades_config(lote_id, vigente);

-- 6. Indice de unicidad para idempotencia de seeds en reglas_pago_tarifas
CREATE UNIQUE INDEX IF NOT EXISTS uq_reglas_pago_nombre ON reglas_pago_tarifas (nombre_regla);
