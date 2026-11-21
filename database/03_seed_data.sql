-- ============================================================================
-- 03_seed_data.sql
-- Seeds iniciales reales de Fase 0 para PostgreSQL 16 (idempotentes)
-- Integra datos confirmados desde documentos locales reales (Orden Mastronardi
-- #260100 firmada 02/11/2026, Manual Integral Berries, GROWER_MODULOS_CATALOGO,
-- Guia AzraBlue Fall Creek, Forecast Azra Blue, Requerimientos 2.7 ha y Fresa).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Cultivos base (NFA: Frambuesa y Fresa | BIO: Arandano)
-- ----------------------------------------------------------------------------
INSERT INTO cultivos (
    codigo, nombre, empresa_clave, unidad_cosecha_default, unidades_por_caja,
    peso_neto_caja_kg, peso_real_caja_kg, merma_maxima_permitida_pct,
    cajas_por_tarima, permite_cosecha_domingo, activo
) VALUES
    ('FRAMB', 'Frambuesa', 'NFA', 'CLAMSHELL_12X6OZ', 12, 2.040, 2.140, 10.00, 200, TRUE,  TRUE),
    ('ARAND', 'Arándano',  'BIO', 'CLAMSHELL_12X6OZ', 12, 2.040, 2.140,  8.00, 192, FALSE, TRUE),
    ('FRESA', 'Fresa',     'NFA', 'CAJA_8X1LB',        8, 3.630, 3.750, 10.00, 120, FALSE, TRUE)
ON CONFLICT (codigo) DO UPDATE SET
    nombre                     = EXCLUDED.nombre,
    empresa_clave              = EXCLUDED.empresa_clave,
    unidad_cosecha_default     = EXCLUDED.unidad_cosecha_default,
    unidades_por_caja          = EXCLUDED.unidades_por_caja,
    peso_neto_caja_kg          = EXCLUDED.peso_neto_caja_kg,
    peso_real_caja_kg          = EXCLUDED.peso_real_caja_kg,
    merma_maxima_permitida_pct = EXCLUDED.merma_maxima_permitida_pct,
    cajas_por_tarima           = EXCLUDED.cajas_por_tarima,
    permite_cosecha_domingo    = EXCLUDED.permite_cosecha_domingo,
    activo                     = EXCLUDED.activo;

-- ----------------------------------------------------------------------------
-- 2. Departamentos, Tabulador, Catalogo de Labores y Reglas de Pago
-- ----------------------------------------------------------------------------
INSERT INTO departamentos (codigo, nombre, activo) VALUES
    ('DIR',  'Dirección General', TRUE),
    ('PROD', 'Producción Agrícola', TRUE),
    ('TEC',  'Área Técnica y Nutrición', TRUE),
    ('INOC', 'Inocuidad y Calidad', TRUE),
    ('RH',   'Recursos Humanos', TRUE),
    ('INV',  'Inventarios y Costos', TRUE),
    ('LOG',  'Logística y Exportación', TRUE)
ON CONFLICT (codigo) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    activo = EXCLUDED.activo;

INSERT INTO tabulador_niveles (
    nivel_numero, nombre_nivel, tipo_pago_default, salario_minimo_diario,
    salario_maximo_diario, aplica_bono_productividad, descripcion_reglas
) VALUES
    (1, 'Nivel 1: Operativo Campo y Empaque', 'MIXTO', 320.00, 650.00, TRUE,
        'Jornal base garantizado + destajo por caja/surco + bono por calidad'),
    (2, 'Nivel 2: Supervisión y Control Calidad', 'FIJO_MENSUAL', 450.00, 750.00, TRUE,
        'Salario fijo semanal + bono por cumplimiento de meta de cuadrilla y cero rechazos inocuidad'),
    (3, 'Nivel 3: Técnico Especializado y Admin', 'FIJO_MENSUAL', 700.00, 1400.00, TRUE,
        'Sueldo nominal por banda (Jr/Pleno/Sr) + bono trimestral por KPIs de área'),
    (4, 'Nivel 4: Gerencia y Dirección', 'FIJO_MENSUAL', 1500.00, 3500.00, TRUE,
        'Sueldo ejecutivo + bono anual ligado a rentabilidad por cultivo')
ON CONFLICT (nivel_numero) DO UPDATE SET
    nombre_nivel              = EXCLUDED.nombre_nivel,
    tipo_pago_default         = EXCLUDED.tipo_pago_default,
    salario_minimo_diario     = EXCLUDED.salario_minimo_diario,
    salario_maximo_diario     = EXCLUDED.salario_maximo_diario,
    aplica_bono_productividad = EXCLUDED.aplica_bono_productividad,
    descripcion_reglas        = EXCLUDED.descripcion_reglas;

INSERT INTO catalogo_labores (codigo, nombre, categoria, unidad_medida, activo) VALUES
    ('COSECHA',    'Corte / Cosecha de Fruta',           'COSECHA',        'CAJA',         TRUE),
    ('TRASPLANTE', 'Trasplante de Planta en Modulo',     'LABOR_CULTURAL', 'PLANTA',       TRUE),
    ('PODA',       'Poda de Formación / Saneamiento',    'LABOR_CULTURAL', 'SURCO',        TRUE),
    ('DESHIJE',    'Deshije y Raleo de Brotes',          'LABOR_CULTURAL', 'SURCO',        TRUE),
    ('TUTOREO',    'Tutoreo y Amarrado de Caña',         'LABOR_CULTURAL', 'METRO_LINEAL', TRUE),
    ('DESHIERBE',  'Deshierbe Manual de Cama',           'LABOR_CULTURAL', 'METRO_LINEAL', TRUE)
ON CONFLICT (codigo) DO UPDATE SET
    nombre        = EXCLUDED.nombre,
    categoria     = EXCLUDED.categoria,
    unidad_medida = EXCLUDED.unidad_medida,
    activo        = EXCLUDED.activo;

INSERT INTO reglas_pago_tarifas (
    nombre_regla, cultivo_id, labor_id, modalidad_pago, tarifa_jornal_base,
    tarifa_por_unidad, meta_minima_unidades, tarifa_excedente_unidad,
    porcentaje_rezaga_maximo, bono_calidad_por_unidad, fecha_inicio_vigencia, creado_por
)
SELECT
    v.nombre_regla,
    c.id AS cultivo_id,
    l.id AS labor_id,
    v.modalidad_pago,
    v.tarifa_jornal_base,
    v.tarifa_por_unidad,
    v.meta_minima_unidades,
    v.tarifa_excedente_unidad,
    v.porcentaje_rezaga_maximo,
    v.bono_calidad_por_unidad,
    DATE '2026-01-01',
    'SYSTEM_INIT'
FROM (VALUES
    ('Cosecha Frambuesa Mixta 2026', 'FRAMB', 'COSECHA',    'MIXTO_GARANTIA', 330.00,  0.00, 14.00, 24.00, 3.00, 2.00),
    ('Cosecha Arándano Destajo 2026', 'ARAND', 'COSECHA',   'DESTAJO_PURO',     0.00, 28.00,  0.00, 28.00, 2.50, 2.50),
    ('Cosecha Fresa Mixta 2026',      'FRESA', 'COSECHA',   'MIXTO_GARANTIA', 330.00,  0.00, 18.00, 19.00, 4.00, 1.50),
    ('Poda General Jornal 2026',       NULL,   'PODA',      'JORNAL_PURO',    340.00,  0.00,  6.00,  0.00, 0.00, 0.00),
    ('Trasplante General Jornal 2026', NULL,   'TRASPLANTE','JORNAL_PURO',    340.00,  0.00,  0.00,  0.00, 0.00, 0.00)
) AS v(nombre_regla, cultivo_cod, labor_cod, modalidad_pago, tarifa_jornal_base,
       tarifa_por_unidad, meta_minima_unidades, tarifa_excedente_unidad,
       porcentaje_rezaga_maximo, bono_calidad_por_unidad)
JOIN catalogo_labores l ON l.codigo = v.labor_cod
LEFT JOIN cultivos c ON c.codigo = v.cultivo_cod
ON CONFLICT (nombre_regla) DO UPDATE SET
    modalidad_pago           = EXCLUDED.modalidad_pago,
    tarifa_jornal_base       = EXCLUDED.tarifa_jornal_base,
    tarifa_por_unidad        = EXCLUDED.tarifa_por_unidad,
    meta_minima_unidades     = EXCLUDED.meta_minima_unidades,
    tarifa_excedente_unidad  = EXCLUDED.tarifa_excedente_unidad,
    porcentaje_rezaga_maximo = EXCLUDED.porcentaje_rezaga_maximo,
    bono_calidad_por_unidad  = EXCLUDED.bono_calidad_por_unidad,
    activa                   = TRUE;

-- ----------------------------------------------------------------------------
-- 3. Ranchos base por empresa (NFA y BIO — Actopan, Hidalgo)
-- ----------------------------------------------------------------------------
INSERT INTO ranchos (codigo, nombre, empresa_clave, ubicacion, superficie_total_ha, activo) VALUES
    ('NFA-PRINCIPAL', 'Predio Principal NFA (Natural Fruits of America)', 'NFA', 'Km 3.5 Camino Cañada Chica, Actopan, Hidalgo, MX', 13.78, TRUE),
    ('BIO-PRINCIPAL', 'Predio Principal BIO (Bio-Orgánicos Saludables)',  'BIO', 'Actopan, Hidalgo, MX', 8.30, TRUE)
ON CONFLICT (codigo) DO UPDATE SET
    nombre              = EXCLUDED.nombre,
    empresa_clave       = EXCLUDED.empresa_clave,
    ubicacion           = EXCLUDED.ubicacion,
    superficie_total_ha = EXCLUDED.superficie_total_ha,
    activo              = EXCLUDED.activo;

-- ----------------------------------------------------------------------------
-- 4. Variedades y cohortes (distinguiendo confirmado_tecnico TRUE vs FALSE)
-- ----------------------------------------------------------------------------
INSERT INTO variedades_cultivo (
    cultivo_id, codigo, nombre, cohorte, presentacion_planta_default,
    codigo_genetico, casa_genetica, confirmado_tecnico, fuente_documental, notas
)
SELECT
    c.id, v.codigo, v.nombre, v.cohorte, v.presentacion,
    v.cod_gen, v.casa_gen, v.confirmado, v.fuente, v.notas
FROM (VALUES
    ('FRAMB', 'FRAMB-DJ-LC', 'Diamond Jubilee (DJ) — Long Cane', 'LONG_CANE', 'CANES',
        'DJ', 'Mastronardi / BerryWorld', TRUE,
        '260100_Natural_Fruits_of_America_DJ_LC_-_Nov (2).pdf (firmado 02/11/2026) + NAT-PR-PRO-004',
        'Orden #260100 confirmada: 10.2 ha, 208,000 plantas Long Cane ($3.50 USD/planta). Confirmar en campo si el arribo separa Grade A vs Singles sin conversion implicita.'),
    ('FRAMB', 'FRAMB-DJ-PC', 'Diamond Jubilee (DJ) — Primocaña', 'PRIMOCANA', NULL,
        'DJ', 'Mastronardi / BerryWorld', TRUE,
        'NAT-TRASPLANTE CON DESFASES FRAMBUESA_PROPUESTA_REVISION_2026-11-09.xlsx + NAT-PR-PRO-004',
        'Cohorte Primocana (rebrote posterior a ciclo Long Cane de variedad DJ). Separada de Long Cane para curvas y planeacion.'),
    ('ARAND', 'ARAND-AZRABLUE', 'AzraBlue', 'PERENNE', 'MACETA',
        'FCM14-031', 'Fall Creek', TRUE,
        'Guia_de_arandano_para_Brenda.pdf + Forecast azra blue.xlsx + GROWER_MODULOS_CATALOGO_v0_1.xlsx',
        'Variedad confirmada para los 3 modulos BIO (bolsa elevada 30 L fibra de coco, 28 perforaciones). Cero requerimiento de frio.'),
    ('ARAND', 'ARAND-SEKOYA-PEND', 'Sekoya Pop (Por confirmar si aplica)', 'PERENNE', NULL,
        NULL, 'Fall Creek / Sekoya', FALSE,
        'Handoff_Campo_Arandano_Cosecha_RH_2026-11-18.md',
        'Mencionada como posible en handoff 18/11/2026; pendiente confirmar con Luis si entra en algun bloque BIO.'),
    ('FRESA', 'FRESA-ALBION-HIST', 'Albion (Histórico M21/M22 — confirmar vigente)', 'TEMPORAL', 'RAIZ_DESNUDA',
        NULL, 'UC Davis / Team Fresh', FALSE,
        'BIO_2024_COSTOS_FRESA_FINAL.xlsx (hoja PLANTA CF1)',
        'Historico 2023-2024: 54,000 plantas raiz desnuda en M21 y 54,000 en M22. Confirmar con Luis si continua en ciclo 2026-2027.'),
    ('FRESA', 'FRESA-FRONTERA-HIST', 'Frontera (Histórico M21/M22 — confirmar vigente)', 'TEMPORAL', 'RAIZ_DESNUDA',
        NULL, 'UC Davis / Team Fresh', FALSE,
        'BIO_2024_COSTOS_FRESA_FINAL.xlsx (hoja PLANTA CF1)',
        'Historico 2023-2024: 54,000 plantas raiz desnuda en M21 y 54,000 en M22. Confirmar con Luis si continua en ciclo 2026-2027.'),
    ('FRESA', 'FRESA-SAYULITA-HIST', 'Sayulita (Histórico cepellón — confirmar vigente)', 'TEMPORAL', 'CEPELLON',
        NULL, 'Planasa', FALSE,
        'BIO_2024_COSTOS_FRESA_FINAL.xlsx (hoja PLANTA CF1)',
        'Historico en cepellon Planasa. Confirmar con Luis si sigue activa en algun modulo.')
) AS v(cultivo_cod, codigo, nombre, cohorte, presentacion, cod_gen, casa_gen, confirmado, fuente, notas)
JOIN cultivos c ON c.codigo = v.cultivo_cod
ON CONFLICT (codigo) DO UPDATE SET
    nombre                      = EXCLUDED.nombre,
    cohorte                     = EXCLUDED.cohorte,
    presentacion_planta_default = EXCLUDED.presentacion_planta_default,
    codigo_genetico             = EXCLUDED.codigo_genetico,
    casa_genetica               = EXCLUDED.casa_genetica,
    confirmado_tecnico          = EXCLUDED.confirmado_tecnico,
    fuente_documental           = EXCLUDED.fuente_documental,
    notas                       = EXCLUDED.notas;

-- ----------------------------------------------------------------------------
-- 5. Lotes fisicos reales del predio (17 activos + 2 excluidos inactivos)
--    Geometria M1-M11 confirmada por Manual Integral de Operacion Berries y
--    GROWER_MODULOS_CATALOGO_v0_1.xlsx:
--      - M1..M8:  7,680 m2 (0.7680 ha), 40 lineas, 3,040 m lineales,
--                 174 macetas/linea (83 Norte + 91 Sur) = 6,960 macetas (7L), 13,920 canas.
--      - M9..M11: 6,912 m2 (0.6912 ha), 36 lineas, 2,736 m lineales,
--                 174 macetas/linea (83 Norte + 91 Sur) = 6,264 macetas (7L), 12,528 canas.
--      - M1.1:    2.7672 ha (~27,000 m2), baticenital tuneles 11.5 m, 65 lineas,
--                 26,010 macetas (hoja 1.1 A) vs 26,520 (sustrato nfa 2) -> por confirmar.
--      - M21,M22: 1.3000 ha (~13,000 m2; ref 93.96x136.5 m), media tecnologia, canaletas 45 cm.
--      - BIO 1.2, 2.1, 2.2: 2.7672 ha (~27,000 m2), naves adaptadas de tomate,
--                 tuneles 11.5 m (1.2) y 10.0 m (2.1, 2.2), bolsas 30 L AzraBlue.
-- ----------------------------------------------------------------------------
INSERT INTO lotes_produccion (
    rancho_id, cultivo_id, empresa_clave, codigo_lote, nombre_sector, variedad,
    variedad_id, superficie_ha, superficie_m2, total_surcos, metros_lineales_totales,
    macetas_por_linea, macetas_norte, macetas_sur, total_macetas, contenedor_tipo,
    tipo_estructura, nivel_tecnologia, origen_diseno, ancho_tunel_m,
    fecha_plantacion, ciclo_agricola, estatus_fitosanitario, activo, notas_estructura
)
SELECT
    r.id AS rancho_id,
    c.id AS cultivo_id,
    v.empresa_clave,
    v.codigo_lote,
    v.nombre_sector,
    v.variedad_txt,
    vc.id AS variedad_id,
    v.superficie_ha,
    v.superficie_m2,
    v.total_surcos,
    v.metros_lineales,
    v.macetas_linea,
    v.macetas_norte,
    v.macetas_sur,
    v.total_macetas,
    v.contenedor_tipo,
    v.tipo_estructura,
    v.nivel_tecnologia,
    v.origen_diseno,
    v.ancho_tunel_m,
    DATE '2026-01-15',
    v.ciclo_agricola,
    v.estatus_fitosanitario,
    v.activo,
    v.notas_estructura
FROM (VALUES
    -- NFA / Frambuesa: Modulos 1 al 8 (baticenitales, 0.7680 ha, 40 lineas, 3,040 m, 6,960 macetas 7L, 13,920 canas)
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M01','Módulo 1', 'Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.7680, 7680.00, 40, 3040.00,174,83,91, 6960,'MACETA_7L_INVECO_FTP025','BATICENITAL','MEDIA_ALTA','BATICENITAL_BERRIES',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Baticenital 1-10 confirmado: 40 lineas, 3,040 m, 174 macetas/linea (83 N / 91 S) = 6,960 macetas / 13,920 canas.'),
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M02','Módulo 2', 'Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.7680, 7680.00, 40, 3040.00,174,83,91, 6960,'MACETA_7L_INVECO_FTP025','BATICENITAL','MEDIA_ALTA','BATICENITAL_BERRIES',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Baticenital 1-10 confirmado: 40 lineas, 3,040 m, 174 macetas/linea (83 N / 91 S) = 6,960 macetas / 13,920 canas.'),
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M03','Módulo 3', 'Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.7680, 7680.00, 40, 3040.00,174,83,91, 6960,'MACETA_7L_INVECO_FTP025','BATICENITAL','MEDIA_ALTA','BATICENITAL_BERRIES',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Baticenital 1-10 confirmado: 40 lineas, 3,040 m, 174 macetas/linea (83 N / 91 S) = 6,960 macetas / 13,920 canas.'),
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M04','Módulo 4', 'Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.7680, 7680.00, 40, 3040.00,174,83,91, 6960,'MACETA_7L_INVECO_FTP025','BATICENITAL','MEDIA_ALTA','BATICENITAL_BERRIES',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Baticenital 1-10 confirmado: 40 lineas, 3,040 m, 174 macetas/linea (83 N / 91 S) = 6,960 macetas / 13,920 canas.'),
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M05','Módulo 5', 'Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.7680, 7680.00, 40, 3040.00,174,83,91, 6960,'MACETA_7L_INVECO_FTP025','BATICENITAL','MEDIA_ALTA','BATICENITAL_BERRIES',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Baticenital 1-10 confirmado: 40 lineas, 3,040 m, 174 macetas/linea (83 N / 91 S) = 6,960 macetas / 13,920 canas.'),
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M06','Módulo 6', 'Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.7680, 7680.00, 40, 3040.00,174,83,91, 6960,'MACETA_7L_INVECO_FTP025','BATICENITAL','MEDIA_ALTA','BATICENITAL_BERRIES',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Baticenital 1-10 confirmado: 40 lineas, 3,040 m, 174 macetas/linea (83 N / 91 S) = 6,960 macetas / 13,920 canas.'),
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M07','Módulo 7', 'Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.7680, 7680.00, 40, 3040.00,174,83,91, 6960,'MACETA_7L_INVECO_FTP025','BATICENITAL','MEDIA_ALTA','BATICENITAL_BERRIES',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Baticenital 1-10 confirmado: 40 lineas, 3,040 m, 174 macetas/linea (83 N / 91 S) = 6,960 macetas / 13,920 canas.'),
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M08','Módulo 8', 'Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.7680, 7680.00, 40, 3040.00,174,83,91, 6960,'MACETA_7L_INVECO_FTP025','BATICENITAL','MEDIA_ALTA','BATICENITAL_BERRIES',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Baticenital 1-10 confirmado: 40 lineas, 3,040 m, 174 macetas/linea (83 N / 91 S) = 6,960 macetas / 13,920 canas.'),

    -- NFA / Frambuesa: Modulos 9 y 10 (baticenitales, 0.6912 ha, 36 lineas, 2,736 m, 6,264 macetas 7L, 12,528 canas)
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M09','Módulo 9', 'Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.6912, 6912.00, 36, 2736.00,174,83,91, 6264,'MACETA_7L_INVECO_FTP025','BATICENITAL','MEDIA_ALTA','BATICENITAL_BERRIES',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Baticenital 1-10 confirmado: 36 lineas, 2,736 m, 174 macetas/linea (83 N / 91 S) = 6,264 macetas / 12,528 canas.'),
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M10','Módulo 10','Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.6912, 6912.00, 36, 2736.00,174,83,91, 6264,'MACETA_7L_INVECO_FTP025','BATICENITAL','MEDIA_ALTA','BATICENITAL_BERRIES',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Baticenital 1-10 confirmado: 36 lineas, 2,736 m, 174 macetas/linea (83 N / 91 S) = 6,264 macetas / 12,528 canas.'),

    -- NFA / Frambuesa: Modulo 11 (diseno estructural mas austero, 0.6912 ha, 36 lineas, 2,736 m, 6,264 macetas 7L, 12,528 canas)
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M11','Módulo 11','Diamond Jubilee (DJ)','FRAMB-DJ-LC',0.6912, 6912.00, 36, 2736.00,174,83,91, 6264,'MACETA_7L_INVECO_FTP025','AUSTERO',    'BAJA',      'AUSTERO_BERRIES',    NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Estructura mas austera que M1-10: 36 lineas, 2,736 m, 6,264 macetas / 12,528 canas.'),

    -- NFA / Frambuesa: Modulo 1.1 (~2.7672 ha / ~27,000 m2, baticenital tuneles 11.5 m, 65 lineas; macetas 26,010 vs 26,520 por cerrar)
    ('NFA-PRINCIPAL','FRAMB','NFA','NFA-FRAMB-M1.1','Módulo 1.1','Diamond Jubilee (DJ)','FRAMB-DJ-LC',2.7672,27672.00, 65,10950.00,204,NULL,NULL,26010,'MACETA_7L_INVECO_FTP025','BATICENITAL','ALTA','ADAPTADO_TOMATE',11.50,'2026-2027','LIBRE_CORTE',TRUE, 'Nave baticenital (~27,000 m2) tuneles 11.5 m, 65 lineas (204/170 macetas/linea, 78,030 goteros). Confirmar con Luis 26,010 vs 26,520 macetas (52,020 vs 53,040 plantas) y metros lineales exactos.'),

    -- NFA / Fresa: Modulos 21 y 22 (~1.3000 ha / ~13,000 m2 c/u; ref 93.96x136.5 m, media tecnologia, canaletas 45 cm)
    ('NFA-PRINCIPAL','FRESA','NFA','NFA-FRESA-M21','Módulo 21','Albion / Frontera (Por confirmar ciclo 26-27)','FRESA-ALBION-HIST',1.3000,13000.00, 60, 5200.00,NULL,NULL,NULL,NULL,'GROWBAG_18L_CANALETA_45CM','MEDIA_TECNOLOGIA','MEDIA','MEDIA_TEC_FRESA',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Estructura media tecnologia Fresa (~13,000 m2; ref 93.96x136.5 m). Historico 108,000 plantas (54k Albion + 54k Frontera). Confirmar variedad y camas/metros vigentes.'),
    ('NFA-PRINCIPAL','FRESA','NFA','NFA-FRESA-M22','Módulo 22','Albion / Frontera (Por confirmar ciclo 26-27)','FRESA-ALBION-HIST',1.3000,13000.00, 60, 5200.00,NULL,NULL,NULL,NULL,'GROWBAG_18L_CANALETA_45CM','MEDIA_TECNOLOGIA','MEDIA','MEDIA_TEC_FRESA',NULL,'2026-2027','LIBRE_CORTE',TRUE, 'Estructura media tecnologia Fresa (~13,000 m2; ref 93.96x136.5 m). Historico 108,000 plantas (54k Albion + 54k Frontera). Confirmar variedad y camas/metros vigentes.'),

    -- BIO / Arandano: Modulos 1.2 (tuneles 11.5 m), 2.1 y 2.2 (tuneles 10.0 m), ~2.7672 ha / ~27,000 m2 c/u
    ('BIO-PRINCIPAL','ARAND','BIO','BIO-ARAND-M1.2','Módulo 1.2','AzraBlue (FCM14-031)','ARAND-AZRABLUE',2.7672,27672.00, 75,10950.00,150,NULL,NULL,20250,'BOLSA_30L_COCO_28PERF','NAVE_ADAPTADA','ALTA',      'ADAPTADO_TOMATE',11.50,'2026-2027','LIBRE_CORTE',TRUE, 'Nave origen tomate (~27,000 m2) adaptada a Arandano AzraBlue; tuneles 11.5 m, bolsas 30 L coco (28 perf.). Confirmar plantas exactas (20,250 vs 22,500) y nivel alta/media-alta.'),
    ('BIO-PRINCIPAL','ARAND','BIO','BIO-ARAND-M2.1','Módulo 2.1','AzraBlue (FCM14-031)','ARAND-AZRABLUE',2.7672,27672.00, 75,10950.00,150,NULL,NULL,20250,'BOLSA_30L_COCO_28PERF','NAVE_ADAPTADA','MEDIA_ALTA','ADAPTADO_TOMATE',10.00,'2026-2027','LIBRE_CORTE',TRUE, 'Nave origen tomate (~27,000 m2) adaptada a Arandano AzraBlue; tuneles 10.0 m, trasplante S26. Confirmar plantas exactas (20,250 vs 15,750/22,500) y si existe Sekoya Pop.'),
    ('BIO-PRINCIPAL','ARAND','BIO','BIO-ARAND-M2.2','Módulo 2.2','AzraBlue (FCM14-031)','ARAND-AZRABLUE',2.7672,27672.00, 75,10950.00,150,NULL,NULL,20250,'BOLSA_30L_COCO_28PERF','NAVE_ADAPTADA','MEDIA_ALTA','ADAPTADO_TOMATE',10.00,'2026-2027','LIBRE_CORTE',TRUE, 'Nave origen tomate (~27,000 m2) adaptada a Arandano AzraBlue; tuneles 10.0 m, trasplante S29. Confirmar plantas exactas y superficie activa (5.8 ha vs 8.1/8.3 ha).'),

    -- Excluidos / Inactivos documentados: bloque inferior "Modulo 7" y vivero en plan
    ('NFA-PRINCIPAL','FRAMB','NFA','REF-MOD7-INF',   'Bloque Inferior Módulo 7 (Inactivo)','Sin asignar',NULL,0.5000,5000.00, 1, 1.00,NULL,NULL,NULL,NULL,NULL,'AUSTERO','BAJA', 'EXCLUSION_LAYOUT',NULL,'2026-2027','CERRADO',FALSE,'Omitido/inactivo deliberadamente por definicion de Fase 0.'),
    ('NFA-PRINCIPAL','FRAMB','NFA','REF-VIVERO-PLAN','Vivero en Plan (Inactivo)',          'Sin asignar',NULL,0.2500,2500.00, 1, 1.00,NULL,NULL,NULL,NULL,NULL,'VIVERO', 'MEDIA','EXCLUSION_PLAN',  NULL,'2026-2027','CERRADO',FALSE,'Vivero en plan dejado inactivo deliberadamente en Fase 0.')
) AS v(rancho_cod, cultivo_cod, empresa_clave, codigo_lote, nombre_sector, variedad_txt,
       variedad_cod, superficie_ha, superficie_m2, total_surcos, metros_lineales,
       macetas_linea, macetas_norte, macetas_sur, total_macetas, contenedor_tipo,
       tipo_estructura, nivel_tecnologia, origen_diseno, ancho_tunel_m,
       ciclo_agricola, estatus_fitosanitario, activo, notas_estructura)
JOIN ranchos r ON r.codigo = v.rancho_cod
JOIN cultivos c ON c.codigo = v.cultivo_cod
LEFT JOIN variedades_cultivo vc ON vc.codigo = v.variedad_cod
ON CONFLICT (codigo_lote) DO UPDATE SET
    rancho_id               = EXCLUDED.rancho_id,
    cultivo_id              = EXCLUDED.cultivo_id,
    empresa_clave           = EXCLUDED.empresa_clave,
    nombre_sector           = EXCLUDED.nombre_sector,
    variedad                = EXCLUDED.variedad,
    variedad_id             = EXCLUDED.variedad_id,
    superficie_ha           = EXCLUDED.superficie_ha,
    superficie_m2           = EXCLUDED.superficie_m2,
    total_surcos            = EXCLUDED.total_surcos,
    metros_lineales_totales = EXCLUDED.metros_lineales_totales,
    macetas_por_linea       = EXCLUDED.macetas_por_linea,
    macetas_norte           = EXCLUDED.macetas_norte,
    macetas_sur             = EXCLUDED.macetas_sur,
    total_macetas           = EXCLUDED.total_macetas,
    contenedor_tipo         = EXCLUDED.contenedor_tipo,
    tipo_estructura         = EXCLUDED.tipo_estructura,
    nivel_tecnologia        = EXCLUDED.nivel_tecnologia,
    origen_diseno           = EXCLUDED.origen_diseno,
    ancho_tunel_m           = EXCLUDED.ancho_tunel_m,
    activo                  = EXCLUDED.activo,
    notas_estructura        = EXCLUDED.notas_estructura;

-- ----------------------------------------------------------------------------
-- 5b. Configuracion de densidades por lote (confirmado_tecnico = TRUE solo donde
--     la geometria/plantas proviene de documento validado; umbrales de merma,
--     supervivencia y resiembra quedan en NULL hasta validacion explicita con Luis)
-- ----------------------------------------------------------------------------
INSERT INTO lotes_densidades_config (
    lote_id, variedad_id, ciclo_agricola, presentacion_planta, unidad_densidad,
    densidad_objetivo, plantas_por_contenedor, plantas_estimadas_lote,
    umbral_merma_trasplante_pct, umbral_supervivencia_min_pct, umbral_resiembra_pct,
    confirmado_tecnico, fuente_confirmacion, notas
)
SELECT
    l.id,
    l.variedad_id,
    l.ciclo_agricola,
    CASE
        WHEN l.codigo_lote LIKE 'NFA-FRAMB-%' THEN 'CANES'
        WHEN l.codigo_lote LIKE 'BIO-ARAND-%' THEN 'MACETA'
        WHEN l.codigo_lote LIKE 'NFA-FRESA-%' THEN 'RAIZ_DESNUDA'
        ELSE NULL
    END AS presentacion_planta,
    CASE
        WHEN l.codigo_lote LIKE 'NFA-FRAMB-M0%' OR l.codigo_lote IN ('NFA-FRAMB-M10','NFA-FRAMB-M11')
            THEN 'CANAS_POR_METRO_LINEAL'
        WHEN l.codigo_lote LIKE 'BIO-ARAND-%'
            THEN 'PLANTAS_POR_HA'
        ELSE 'PLANTAS_POR_METRO_LINEAL'
    END AS unidad_densidad,
    CASE
        WHEN l.codigo_lote LIKE 'NFA-FRAMB-M0%' OR l.codigo_lote IN ('NFA-FRAMB-M10','NFA-FRAMB-M11')
            THEN ROUND((l.total_macetas * 2.0) / NULLIF(l.metros_lineales_totales, 0), 3)
        WHEN l.codigo_lote LIKE 'BIO-ARAND-%'
            THEN 7500.000
        ELSE NULL
    END AS densidad_objetivo,
    CASE
        WHEN l.codigo_lote LIKE 'NFA-FRAMB-%' THEN 2.00
        WHEN l.codigo_lote LIKE 'BIO-ARAND-%' THEN 1.00
        ELSE NULL
    END AS plantas_por_contenedor,
    CASE
        WHEN l.codigo_lote LIKE 'NFA-FRAMB-M0%' OR l.codigo_lote IN ('NFA-FRAMB-M10','NFA-FRAMB-M11')
            THEN l.total_macetas * 2
        WHEN l.codigo_lote = 'NFA-FRAMB-M1.1'
            THEN 52020
        WHEN l.codigo_lote LIKE 'BIO-ARAND-%'
            THEN 20250
        ELSE NULL
    END AS plantas_estimadas_lote,
    NULL AS umbral_merma_trasplante_pct,
    NULL AS umbral_supervivencia_min_pct,
    NULL AS umbral_resiembra_pct,
    CASE
        WHEN l.codigo_lote LIKE 'NFA-FRAMB-M0%' OR l.codigo_lote IN ('NFA-FRAMB-M10','NFA-FRAMB-M11')
            THEN TRUE
        ELSE FALSE
    END AS confirmado_tecnico,
    CASE
        WHEN l.codigo_lote LIKE 'NFA-FRAMB-M0%' OR l.codigo_lote IN ('NFA-FRAMB-M10','NFA-FRAMB-M11')
            THEN 'Manual Integral de Operacion Berries + GROWER_MODULOS_CATALOGO_v0_1.xlsx + sustrato nfa 2.xlsx + Orden MPL #260100'
        WHEN l.codigo_lote = 'NFA-FRAMB-M1.1'
            THEN '1. Requerimientos frambuesa para mod 2.7.xlsx (52,020) vs sustrato nfa 2.xlsx / NAT-TRASPLANTE (53,000-53,040) — conciliar con Luis'
        WHEN l.codigo_lote LIKE 'BIO-ARAND-%'
            THEN 'GROWER_MODULOS_CATALOGO_v0_1.xlsx (7,500 pl/ha = 20,250/mod) vs 2. Requerimientos arandano.xlsx (8,333 pl/ha) — conciliar con Luis'
        ELSE 'BIO_2024_COSTOS_FRESA_FINAL.xlsx (historico 108,000 pl/mod Albion+Frontera) — confirmar ciclo 2026-2027 con Luis'
    END AS fuente_confirmacion,
    CASE
        WHEN l.codigo_lote LIKE 'NFA-FRAMB-M0%' OR l.codigo_lote IN ('NFA-FRAMB-M10','NFA-FRAMB-M11')
            THEN 'Estructura y plantas/modulo confirmadas (4.579 canas/m lineal, 2 canas/maceta 7L). Pendiente con Luis: umbrales de merma/supervivencia/resiembra y si arribo separa Grade A vs Singles.'
        ELSE 'Pendiente confirmar con Luis: densidad final, metros lineales exactos, presentacion sin conversion implicita y umbrales de merma/supervivencia/resiembra.'
    END AS notas
FROM lotes_produccion l
WHERE l.activo = TRUE
ON CONFLICT (lote_id, ciclo_agricola) DO UPDATE SET
    variedad_id          = EXCLUDED.variedad_id,
    presentacion_planta  = EXCLUDED.presentacion_planta,
    unidad_densidad      = EXCLUDED.unidad_densidad,
    densidad_objetivo    = EXCLUDED.densidad_objetivo,
    plantas_por_contenedor = EXCLUDED.plantas_por_contenedor,
    plantas_estimadas_lote = EXCLUDED.plantas_estimadas_lote,
    confirmado_tecnico   = EXCLUDED.confirmado_tecnico,
    fuente_confirmacion  = EXCLUDED.fuente_confirmacion,
    notas                = EXCLUDED.notas,
    actualizado_en       = NOW();

-- ----------------------------------------------------------------------------
-- 6. Puestos, Baterias Psicometricas y Relacion Puesto-Bateria
-- ----------------------------------------------------------------------------
INSERT INTO puestos (
    departamento_id, tabulador_id, codigo_puesto, titulo, objetivo_puesto,
    responsabilidades, requisitos_perfil, kpis_evaluacion, checklist_onboarding,
    vacantes_abiertas, publicar_en_landing, activo
)
SELECT
    d.id, t.id, v.codigo_puesto, v.titulo, v.objetivo,
    v.responsabilidades::jsonb, v.requisitos::jsonb, v.kpis::jsonb, v.checklist::jsonb,
    v.vacantes_abiertas, v.publicar_en_landing, TRUE
FROM (VALUES
    ('PROD', 1, 'COSECHADOR', 'Cosechador / Operador de Campo',
        'Ejecutar cosecha, trasplante y labores culturales cumpliendo estandares de inocuidad BPA y calidad de exportacion.',
        '["Corte selectivo segun madurez y calidad", "Trasplante y manejo cuidadoso de planta", "Cumplimiento estricto de inocuidad BPA"]',
        '["Disponibilidad de horario en campo", "Atencion a detalle y trabajo en equipo"]',
        '["Cajas validas por jornada", "Porcentaje de merma dentro de limite", "Cero incidencias de inocuidad"]',
        '["F05 Ficha de alta", "F07 Acuse reglamento", "F08 Politica de pago", "Induccion BPA e inocuidad"]',
        25, TRUE),
    ('PROD', 2, 'SUPERVISOR_CAMPO', 'Supervisor de Campo',
        'Coordinar cuadrillas de trasplante y cosecha, validar calidad en modulo y garantizar disciplina operativa e inocuidad.',
        '["Asignacion diaria de cuadrillas en modulos asignados", "Verificacion de trazabilidad y calidad", "Cierre diario de captura en tablet"]',
        '["Experiencia en supervision agricola de berries", "Liderazgo y control operativo"]',
        '["Cumplimiento de meta diaria de modulo", "Cierre oportuno sin discrepancias", "Cumplimiento BPA"]',
        '["F05 Ficha de alta", "Induccion liderazgo y BPA", "Asignacion de credenciales tablet"]',
        4, TRUE),
    ('PROD', 2, 'PESADOR_CAMPO', 'Pesador / Capturista de Modulo',
        'Registrar cajas, clamshells y recepcion de bins en tablet de campo con confirmacion del trabajador.',
        '["Pesaje y verificacion de calidad en estacion", "Captura fiel en tablet con confirmacion NIP"]',
        '["Manejo basico de tablet", "Precision numerica y honestidad"]',
        '["Exactitud de cuadre contra empaque", "Cero capturas sin confirmacion"]',
        '["F05 Ficha de alta", "Capacitacion Tablet Campo", "Induccion BPA"]',
        3, TRUE),
    ('TEC', 3, 'ING_TECNICO', 'Ingeniero Tecnico Fitosanitario',
        'Administrar monitoreo tecnico, fertirriego y aplicaciones fitosanitarias respetando estrictamente PHI y REI.',
        '["Autorizacion y registro de aplicaciones fitosanitarias", "Control de recetas y mediciones de riego"]',
        '["Ingenieria Agronoma o afin", "Conocimiento de berries e inocuidad"]',
        '["Cero violaciones de PHI/REI", "Sanidad vegetal en modulos"]',
        '["F05 Ficha de alta", "Acreditacion tecnica", "Induccion inocuidad"]',
        1, FALSE)
) AS v(depto_cod, nivel_num, codigo_puesto, titulo, objetivo,
       responsabilidades, requisitos, kpis, checklist, vacantes_abiertas, publicar_en_landing)
JOIN departamentos d ON d.codigo = v.depto_cod
JOIN tabulador_niveles t ON t.nivel_numero = v.nivel_num
ON CONFLICT (codigo_puesto) DO UPDATE SET
    titulo              = EXCLUDED.titulo,
    objetivo_puesto     = EXCLUDED.objetivo_puesto,
    vacantes_abiertas   = EXCLUDED.vacantes_abiertas,
    publicar_en_landing = EXCLUDED.publicar_en_landing,
    activo              = TRUE;

INSERT INTO baterias_evaluacion (
    codigo, nombre, tipo, nivel_aplicable, instrucciones,
    tiempo_limite_minutos, configuracion_preguntas, algoritmo_calificacion, activo
) VALUES
    (
        'ZAVIC_OP',
        'Evaluación ZAVIC Operativa Campo',
        'PSICOMETRICA',
        1,
        'Selecciona la opción que mejor refleje tu manera de actuar en el trabajo diario.',
        20,
        '[
            {"id":"z1","pregunta":"Si notas que un compañero no se lavó las manos antes de entrar al módulo, ¿qué haces?","opciones":[{"texto":"Le recuerdo la regla de inocuidad de inmediato","dimension":"apego_normas","puntos":90},{"texto":"Aviso al supervisor para que lo atienda","dimension":"legalidad","puntos":85},{"texto":"No digo nada para evitar problemas","dimension":"apego_normas","puntos":20}]},
            {"id":"z2","pregunta":"Cuando el supervisor asigna una meta de calidad y cajas, tú:","opciones":[{"texto":"Cuido la calidad aunque requiera atención extra","dimension":"compromiso","puntos":90},{"texto":"Sigo exactamente las instrucciones del proceso","dimension":"legalidad","puntos":85},{"texto":"Entrego rápido sin revisar fruta dañada","dimension":"moralidad","puntos":25}]},
            {"id":"z3","pregunta":"Si encuentras herramienta o fruta mal registrada en tu estación:","opciones":[{"texto":"Reporto el error de inmediato con honestidad","dimension":"moralidad","puntos":95},{"texto":"Lo corrijo y aviso al pesador","dimension":"legalidad","puntos":85},{"texto":"Lo dejo pasar","dimension":"moralidad","puntos":15}]},
            {"id":"z4","pregunta":"Ante un cambio de módulo o tarea urgente durante el turno:","opciones":[{"texto":"Apoyo al equipo siguiendo la instrucción","dimension":"compromiso","puntos":90},{"texto":"Pido confirmación del supervisor y procedo","dimension":"apego_normas","puntos":85},{"texto":"Me niego porque no era mi surco inicial","dimension":"compromiso","puntos":20}]}
        ]'::jsonb,
        'ZAVIC_OP',
        TRUE
    ),
    (
        'CLEAVER_SUP',
        'Evaluación Cleaver Supervisión Operativa',
        'PSICOMETRICA',
        2,
        'Elige la opción que mejor describa tu estilo de liderazgo y seguimiento.',
        25,
        '[
            {"id":"c1","pregunta":"Al coordinar una cuadrilla en pico de trabajo, priorizas:","opciones":[{"texto":"Tomar decisiones firmes y verificar resultados","mas":"D","menos":"S"},{"texto":"Seguir controles y estándares sin omitir pasos","mas":"C","menos":"I"},{"texto":"Mantener el ambiente tranquilo aunque baje el ritmo","mas":"S","menos":"D"}]},
            {"id":"c2","pregunta":"Cuando ocurre una desviación en recepción de planta o cosecha:","opciones":[{"texto":"Analizo causa raíz, documento y corrijo de inmediato","mas":"C","menos":"I"},{"texto":"Asumo el mando y reorganizo al equipo en minutos","mas":"D","menos":"S"},{"texto":"Espero instrucciones sin intervenir","mas":"S","menos":"D"}]}
        ]'::jsonb,
        'CLEAVER_SUP',
        TRUE
    )
ON CONFLICT (codigo) DO UPDATE SET
    nombre                  = EXCLUDED.nombre,
    configuracion_preguntas = EXCLUDED.configuracion_preguntas,
    activo                  = TRUE;

INSERT INTO puesto_baterias (puesto_id, bateria_id, peso_porcentual, puntaje_minimo_aprobatorio)
SELECT p.id, b.id, v.peso, v.minimo
FROM (VALUES
    ('COSECHADOR',       'ZAVIC_OP',    100.00, 70.00),
    ('PESADOR_CAMPO',    'ZAVIC_OP',    100.00, 70.00),
    ('SUPERVISOR_CAMPO', 'CLEAVER_SUP', 100.00, 70.00)
) AS v(puesto_cod, bat_cod, peso, minimo)
JOIN puestos p ON p.codigo_puesto = v.puesto_cod
JOIN baterias_evaluacion b ON b.codigo = v.bat_cod
ON CONFLICT (puesto_id, bateria_id) DO UPDATE SET
    peso_porcentual            = EXCLUDED.peso_porcentual,
    puntaje_minimo_aprobatorio = EXCLUDED.puntaje_minimo_aprobatorio;

-- ----------------------------------------------------------------------------
-- 7. Empleados iniciales base (EMP-1001 Supervisor, EMP-2001 Cosechador,
--    EMP-1002 Ingeniero Tecnico) con nomenclatura merqry_employee_id
-- ----------------------------------------------------------------------------
INSERT INTO empleados (
    numero_empleado, merqry_employee_id, puesto_id, curp, rfc, nss,
    nombre, apellido_paterno, apellido_materno, fecha_ingreso, tipo_contrato,
    salario_diario_pactado, esquema_pago, induccion_inocuidad_completada,
    fecha_induccion_inocuidad, codigo_qr_hash, estatus
)
SELECT
    v.num_emp, v.merqry_id, p.id, v.curp, v.rfc, v.nss,
    v.nombre, v.ap_pat, v.ap_mat, DATE '2026-01-05', v.tipo_contrato,
    v.salario, v.esquema_pago, TRUE, DATE '2026-01-05', v.qr_hash, 'ACTIVO'
FROM (VALUES
    ('EMP-1001','MRQ-1001','SUPERVISOR_CAMPO','SUPC900101HHG00101','SUPC900101AAA','11900100001','Carlos','Mendoza','Ríos','INDETERMINADO',550.00,'FIJO_MENSUAL','QR-EMP-1001'),
    ('EMP-2001','MRQ-2001','COSECHADOR',      'COSL950515MHG00202','COSL950515BBB','11950500002','Lucía', 'Hernández','Cruz','TEMPORADA',  330.00,'MIXTO',       'QR-EMP-2001'),
    ('EMP-1002','MRQ-1002','ING_TECNICO',     'INGT880320HHG00303','INGT880320CCC','11880300003','Luis',  'Ramírez','Vega','INDETERMINADO',950.00,'FIJO_MENSUAL','QR-EMP-1002')
) AS v(num_emp, merqry_id, puesto_cod, curp, rfc, nss, nombre, ap_pat, ap_mat,
       tipo_contrato, salario, esquema_pago, qr_hash)
JOIN puestos p ON p.codigo_puesto = v.puesto_cod
ON CONFLICT (numero_empleado) DO UPDATE SET
    merqry_employee_id             = EXCLUDED.merqry_employee_id,
    puesto_id                      = EXCLUDED.puesto_id,
    induccion_inocuidad_completada = TRUE,
    estatus                        = 'ACTIVO';

-- ============================================================================
-- BLOQUE DOCUMENTADO: CONFIRMADO VS PENDIENTE DE VALIDAR CON LUIS (FASE 1 / 3A)
-- ============================================================================
-- CONFIRMADO EN DOCUMENTOS LOCALES:
-- 1. Frambuesa NFA: Variedad Diamond Jubilee (DJ), Orden MPL #260100 firmada el
--    02/11/2026 (10.2 ha, 208,000 plantas Long Cane, $3.50 USD/planta, devolucion
--    obligatoria de bins/cajas plasticas). Geometria M1-M8 (40 lineas, 3,040 m,
--    174 macetas/linea [83 N / 91 S] = 6,960 macetas 7L INVECO FTP-025, 13,920 canas)
--    y M9-M11 (36 lineas, 2,736 m, 6,264 macetas, 12,528 canas). Total M1-M11 = 148,944.
-- 2. Arandano BIO: Variedad AzraBlue (Fall Creek FCM14-031) en bolsas elevadas 30 L
--    fibra de coco (28 perf.: 16 sup., 12 inf.), 60,750 plantas totales en 3 modulos.
-- 3. Fresa NFA (M21/M22): Invernaderos media tecnologia (~13,000 m2; ref 93.96x136.5 m)
--    con canaletas 45 cm y Growbag 18L; historico 2023-24: Albion + Frontera (108k/mod).
--
-- PENDIENTE DE CONFIRMAR CON LUIS ANTES DE FASE 1 / FASE 3A:
-- 1. Frambuesa M1.1 y saldo 208,000 plantas: conciliar 26,010 macetas (52,020 plantas,
--    hoja 1.1 A) vs 26,520 macetas (53,000-53,040 plantas, sustrato nfa 2 / NAT-TRASPLANTE)
--    y destino de las ~6,056 plantas restantes frente a las 208,000 contratadas (10 camiones
--    de 20,800). Confirmar si al arribo se separan Grade A y Singles (sin conversion implicita).
-- 2. Arandano BIO (M1.2, M2.1, M2.2): confirmar distribucion exacta por modulo (20,250 parejo
--    a 7,500 pl/ha vs 22,500/22,500/15,750 a 8,333 pl/ha), superficie activa (5.8 ha Hortifrut
--    vs 8.1/8.3 ha), si aplica Sekoya Pop, y peso oficial de caja (2.00 kg planeacion vs 2.040/2.140).
-- 3. Fresa NFA (M21, M22): confirmar variedades vigentes 2026-2027 (Albion/Frontera/Sayulita u otra),
--    presentacion de arribo (RAIZ_DESNUDA vs CEPELLON), numero exacto de camas/surcos y densidad.
-- 4. Umbrales tecnicos de trasplante (lotes_densidades_config): definir umbral_merma_trasplante_pct
--    (historico 2022-23 fue 4.36%-9.43% distinguiendo 1a merma rota vs 2a sin brotacion),
--    umbral_supervivencia_min_pct y umbral_resiembra_pct.
-- 5. Clasificacion definitiva MEDIA_ALTA vs ALTA en naves reconvertidas de tomate (1.1, 1.2, 2.1, 2.2).
-- ============================================================================
