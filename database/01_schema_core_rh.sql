CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE departamentos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(20) UNIQUE NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    activo BOOLEAN DEFAULT TRUE
);

CREATE TABLE tabulador_niveles (
    id SERIAL PRIMARY KEY,
    nivel_numero INT UNIQUE NOT NULL CHECK (nivel_numero BETWEEN 1 AND 4),
    nombre_nivel VARCHAR(80) NOT NULL,
    tipo_pago_default VARCHAR(30) NOT NULL CHECK (tipo_pago_default IN ('JORNAL', 'DESTAJO', 'MIXTO', 'FIJO_MENSUAL')),
    salario_minimo_diario NUMERIC(10,2) NOT NULL,
    salario_maximo_diario NUMERIC(10,2) NOT NULL,
    aplica_bono_productividad BOOLEAN DEFAULT FALSE,
    descripcion_reglas TEXT
);

CREATE TABLE puestos (
    id SERIAL PRIMARY KEY,
    departamento_id INT NOT NULL REFERENCES departamentos(id),
    tabulador_id INT NOT NULL REFERENCES tabulador_niveles(id),
    codigo_puesto VARCHAR(30) UNIQUE NOT NULL,
    titulo VARCHAR(120) NOT NULL,
    objetivo_puesto TEXT NOT NULL,
    responsabilidades JSONB NOT NULL,
    requisitos_perfil JSONB NOT NULL,
    kpis_evaluacion JSONB NOT NULL,
    checklist_onboarding JSONB NOT NULL,
    vacantes_abiertas INT DEFAULT 0 CHECK (vacantes_abiertas >= 0),
    publicar_en_landing BOOLEAN DEFAULT FALSE,
    activo BOOLEAN DEFAULT TRUE,
    creado_en TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE baterias_evaluacion (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(40) UNIQUE NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    tipo VARCHAR(30) NOT NULL CHECK (tipo IN ('PSICOMETRICA', 'TECNICA', 'HABILIDAD_VISUAL')),
    nivel_aplicable INT NOT NULL REFERENCES tabulador_niveles(nivel_numero),
    instrucciones TEXT NOT NULL,
    tiempo_limite_minutos INT DEFAULT 30,
    configuracion_preguntas JSONB NOT NULL,
    algoritmo_calificacion VARCHAR(50) NOT NULL,
    activo BOOLEAN DEFAULT TRUE
);

CREATE TABLE puesto_baterias (
    puesto_id INT NOT NULL REFERENCES puestos(id) ON DELETE CASCADE,
    bateria_id INT NOT NULL REFERENCES baterias_evaluacion(id) ON DELETE CASCADE,
    peso_porcentual NUMERIC(5,2) NOT NULL CHECK (peso_porcentual > 0 AND peso_porcentual <= 100),
    puntaje_minimo_aprobatorio NUMERIC(5,2) DEFAULT 70.00,
    PRIMARY KEY (puesto_id, bateria_id)
);

CREATE TABLE candidatos (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    puesto_id INT NOT NULL REFERENCES puestos(id),
    curp VARCHAR(18) NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    apellido_paterno VARCHAR(100) NOT NULL,
    apellido_materno VARCHAR(100),
    telefono VARCHAR(20) NOT NULL,
    email VARCHAR(150),
    fecha_nacimiento DATE NOT NULL,
    municipio_residencia VARCHAR(100),
    ruta_transporte_requerida VARCHAR(100),
    cv_url TEXT,
    ine_url TEXT,
    estatus VARCHAR(30) DEFAULT 'POSTULADO' CHECK (
        estatus IN ('POSTULADO', 'EN_EVALUACION', 'APROBADO_RH', 'ENTREVISTA', 'CONTRATADO', 'RECHAZADO', 'LISTA_NEGRA')
    ),
    score_global NUMERIC(5,2) DEFAULT 0,
    es_reingreso BOOLEAN DEFAULT FALSE,
    alerta_historial_kpi TEXT,
    creado_en TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_candidatos_curp ON candidatos(curp);

CREATE TABLE resultados_evaluaciones (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    candidato_id UUID NOT NULL REFERENCES candidatos(id) ON DELETE CASCADE,
    bateria_id INT NOT NULL REFERENCES baterias_evaluacion(id),
    respuestas_json JSONB NOT NULL,
    puntaje_obtenido NUMERIC(5,2) NOT NULL,
    interpretacion_automatica JSONB NOT NULL,
    tiempo_utilizado_segundos INT,
    completado_en TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (candidato_id, bateria_id)
);

CREATE TABLE empleados (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    numero_empleado VARCHAR(20) UNIQUE NOT NULL,
    merqry_employee_id VARCHAR(50) UNIQUE,
    candidato_origen_id UUID REFERENCES candidatos(id),
    puesto_id INT NOT NULL REFERENCES puestos(id),
    curp VARCHAR(18) UNIQUE NOT NULL,
    rfc VARCHAR(13) UNIQUE,
    nss VARCHAR(11) UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    apellido_paterno VARCHAR(100) NOT NULL,
    apellido_materno VARCHAR(100),
    fecha_ingreso DATE NOT NULL,
    fecha_baja DATE,
    tipo_contrato VARCHAR(30) CHECK (tipo_contrato IN ('TEMPORADA', 'INDETERMINADO', 'PRUEBA')),
    salario_diario_pactado NUMERIC(10,2) NOT NULL,
    esquema_pago VARCHAR(30) NOT NULL CHECK (esquema_pago IN ('JORNAL', 'DESTAJO', 'MIXTO', 'FIJO_MENSUAL')),
    cuenta_bancaria_clabe VARCHAR(18),
    banco VARCHAR(60),
    induccion_inocuidad_completada BOOLEAN DEFAULT FALSE,
    fecha_induccion_inocuidad DATE,
    codigo_qr_hash VARCHAR(64) UNIQUE NOT NULL,
    estatus VARCHAR(20) DEFAULT 'ACTIVO' CHECK (estatus IN ('ACTIVO', 'INCAPACIDAD', 'BAJA', 'SUSPENDIDO')),
    creado_en TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE acuses_digitales (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    empleado_id UUID NOT NULL REFERENCES empleados(id),
    tipo_acuse VARCHAR(50) NOT NULL,
    titulo_documento VARCHAR(150) NOT NULL,
    contenido_snapshot TEXT NOT NULL,
    items_entregados JSONB,
    firma_digital_base64 TEXT NOT NULL,
    ip_dispositivo VARCHAR(45),
    firmado_en TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE cultivos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(20) UNIQUE NOT NULL,
    nombre VARCHAR(60) NOT NULL,
    unidad_cosecha_default VARCHAR(30) NOT NULL,
    peso_neto_caja_kg NUMERIC(6,3) NOT NULL,
    activo BOOLEAN DEFAULT TRUE
);

CREATE TABLE ranchos (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(20) UNIQUE NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    ubicacion VARCHAR(150),
    superficie_total_ha NUMERIC(8,2) NOT NULL,
    activo BOOLEAN DEFAULT TRUE
);

CREATE TABLE lotes_produccion (
    id SERIAL PRIMARY KEY,
    rancho_id INT NOT NULL REFERENCES ranchos(id),
    cultivo_id INT NOT NULL REFERENCES cultivos(id),
    codigo_lote VARCHAR(40) UNIQUE NOT NULL,
    nombre_sector VARCHAR(80) NOT NULL,
    variedad VARCHAR(80) NOT NULL,
    superficie_ha NUMERIC(8,4) NOT NULL,
    total_surcos INT NOT NULL CHECK (total_surcos > 0),
    metros_lineales_totales NUMERIC(10,2) NOT NULL,
    fecha_plantacion DATE NOT NULL,
    ciclo_agricola VARCHAR(30) NOT NULL,
    estatus_fitosanitario VARCHAR(30) DEFAULT 'LIBRE_CORTE' CHECK (
        estatus_fitosanitario IN ('LIBRE_CORTE', 'BLOQUEADO_INTERVALO_SEGURIDAD', 'CUARENTENA', 'CERRADO')
    ),
    fecha_liberacion_corte TIMESTAMPTZ,
    activo BOOLEAN DEFAULT TRUE
);

CREATE TABLE catalogo_labores (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(30) UNIQUE NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    categoria VARCHAR(30) NOT NULL CHECK (categoria IN ('COSECHA', 'LABOR_CULTURAL', 'EMPAQUE', 'APOYO')),
    unidad_medida VARCHAR(30) NOT NULL,
    activo BOOLEAN DEFAULT TRUE
);

CREATE TABLE reglas_pago_tarifas (
    id SERIAL PRIMARY KEY,
    nombre_regla VARCHAR(120) NOT NULL,
    cultivo_id INT REFERENCES cultivos(id),
    labor_id INT NOT NULL REFERENCES catalogo_labores(id),
    modalidad_pago VARCHAR(30) NOT NULL CHECK (modalidad_pago IN ('JORNAL_PURO', 'DESTAJO_PURO', 'MIXTO_GARANTIA')),
    tarifa_jornal_base NUMERIC(10,2) DEFAULT 0,
    tarifa_por_unidad NUMERIC(10,2) DEFAULT 0,
    meta_minima_unidades NUMERIC(8,2) DEFAULT 0,
    tarifa_excedente_unidad NUMERIC(10,2) DEFAULT 0,
    porcentaje_rezaga_maximo NUMERIC(5,2) DEFAULT 5.00,
    bono_calidad_por_unidad NUMERIC(10,2) DEFAULT 0,
    fecha_inicio_vigencia DATE NOT NULL,
    fecha_fin_vigencia DATE,
    activa BOOLEAN DEFAULT TRUE,
    creado_por VARCHAR(100) NOT NULL,
    creado_en TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE jornadas_diarias (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fecha DATE NOT NULL,
    empleado_id UUID NOT NULL REFERENCES empleados(id),
    supervisor_id UUID NOT NULL REFERENCES empleados(id),
    rancho_id INT NOT NULL REFERENCES ranchos(id),
    hora_entrada TIMESTAMPTZ NOT NULL,
    hora_salida TIMESTAMPTZ,
    estatus_asistencia VARCHAR(20) DEFAULT 'PRESENTE' CHECK (
        estatus_asistencia IN ('PRESENTE', 'RETARDO', 'FALTA', 'INCAPACIDAD', 'PERMISO')
    ),
    sincronizado_offline BOOLEAN DEFAULT FALSE,
    dispositivo_id VARCHAR(80),
    UNIQUE (fecha, empleado_id)
);

CREATE TABLE registros_labores_culturales (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    jornada_id UUID NOT NULL REFERENCES jornadas_diarias(id),
    empleado_id UUID NOT NULL REFERENCES empleados(id),
    lote_id INT NOT NULL REFERENCES lotes_produccion(id),
    labor_id INT NOT NULL REFERENCES catalogo_labores(id),
    regla_pago_id INT NOT NULL REFERENCES reglas_pago_tarifas(id),
    surcos_trabajados NUMERIC(6,2) DEFAULT 0,
    metros_lineales NUMERIC(8,2) DEFAULT 0,
    porcentaje_avance_lote NUMERIC(5,2) DEFAULT 0,
    calificacion_calidad_supervisor INT CHECK (calificacion_calidad_supervisor BETWEEN 1 AND 5),
    observaciones TEXT,
    registrado_en TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE registros_cosecha (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    codigo_trazabilidad_caja VARCHAR(64) UNIQUE NOT NULL,
    jornada_id UUID NOT NULL REFERENCES jornadas_diarias(id),
    empleado_id UUID NOT NULL REFERENCES empleados(id),
    lote_id INT NOT NULL REFERENCES lotes_produccion(id),
    cultivo_id INT NOT NULL REFERENCES cultivos(id),
    regla_pago_id INT NOT NULL REFERENCES reglas_pago_tarifas(id),
    cantidad_cajas NUMERIC(6,2) NOT NULL DEFAULT 1 CHECK (cantidad_cajas > 0),
    peso_kg_calculado NUMERIC(8,3) NOT NULL,
    calidad_fruta VARCHAR(25) NOT NULL CHECK (calidad_fruta IN ('EXPORTACION', 'NACIONAL', 'PROCESO_REZAGA')),
    cosechado_en TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_cosecha_fecha_emp ON registros_cosecha(empleado_id, cosechado_en);
CREATE INDEX idx_cosecha_lote ON registros_cosecha(lote_id, cosechado_en);

CREATE TABLE prenomina_diaria (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fecha DATE NOT NULL,
    empleado_id UUID NOT NULL REFERENCES empleados(id),
    total_cajas_exportacion NUMERIC(8,2) DEFAULT 0,
    total_cajas_rezaga NUMERIC(8,2) DEFAULT 0,
    porcentaje_rezaga NUMERIC(5,2) DEFAULT 0,
    unidades_labor_cultural NUMERIC(8,2) DEFAULT 0,
    pago_jornal_base NUMERIC(10,2) DEFAULT 0,
    pago_destajo NUMERIC(10,2) DEFAULT 0,
    pago_bono_calidad NUMERIC(10,2) DEFAULT 0,
    total_percepcion_dia NUMERIC(10,2) GENERATED ALWAYS AS (pago_jornal_base + pago_destajo + pago_bono_calidad) STORED,
    estatus_cierre VARCHAR(20) DEFAULT 'BORRADOR' CHECK (estatus_cierre IN ('BORRADOR', 'VALIDADO_SUPERVISOR', 'APROBADO_RH', 'EXPORTADO_MERQRY')),
    lote_exportacion_merqry VARCHAR(50),
    calculado_en TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (fecha, empleado_id)
);

CREATE OR REPLACE VIEW vw_kpi_rendimiento_trabajador AS
SELECT 
    e.id AS empleado_id,
    e.numero_empleado,
    e.curp,
    e.nombre || ' ' || e.apellido_paterno AS nombre_completo,
    p.titulo AS puesto,
    COUNT(DISTINCT j.fecha) AS dias_trabajados,
    COALESCE(SUM(rc.cantidad_cajas), 0) AS total_cajas_cosechadas,
    ROUND(COALESCE(SUM(rc.cantidad_cajas) / NULLIF(COUNT(DISTINCT j.fecha), 0), 0), 2) AS promedio_cajas_dia,
    ROUND(
        COALESCE(
            SUM(CASE WHEN rc.calidad_fruta = 'EXPORTACION' THEN rc.cantidad_cajas ELSE 0 END) * 100.0 / 
            NULLIF(SUM(rc.cantidad_cajas), 0), 
        100), 2
    ) AS porcentaje_calidad_exportacion,
    CASE 
        WHEN COUNT(DISTINCT j.fecha) >= 15 
             AND (SUM(CASE WHEN rc.calidad_fruta = 'EXPORTACION' THEN rc.cantidad_cajas ELSE 0 END) * 100.0 / NULLIF(SUM(rc.cantidad_cajas), 1)) >= 95
        THEN 'RECONTRATACION_PRIORITARIA'
        WHEN COUNT(DISTINCT j.fecha) >= 5 THEN 'ESTANDAR'
        ELSE 'EVALUACION_PENDIENTE'
    END AS clasificacion_recontratacion
FROM empleados e
JOIN puestos p ON e.puesto_id = p.id
LEFT JOIN jornadas_diarias j ON e.id = j.empleado_id AND j.estatus_asistencia IN ('PRESENTE', 'RETARDO')
LEFT JOIN registros_cosecha rc ON e.id = rc.empleado_id
GROUP BY e.id, e.numero_empleado, e.curp, e.nombre, e.apellido_paterno, p.titulo;

INSERT INTO cultivos (codigo, nombre, unidad_cosecha_default, peso_neto_caja_kg) VALUES
('FRAMB', 'Frambuesa', 'CLAMSHELL_12X6OZ', 2.040),
('ARAND', 'Arándano', 'CLAMSHELL_12X6OZ', 2.040),
('FRESA', 'Fresa', 'CAJA_8X1LB', 3.630);

INSERT INTO departamentos (codigo, nombre) VALUES
('DIR', 'Dirección General'),
('PROD', 'Producción Agrícola'),
('TEC', 'Área Técnica y Nutrición'),
('INOC', 'Inocuidad y Calidad'),
('RH', 'Recursos Humanos'),
('INV', 'Inventarios y Costos'),
('LOG', 'Logística y Exportación');

INSERT INTO tabulador_niveles (nivel_numero, nombre_nivel, tipo_pago_default, salario_minimo_diario, salario_maximo_diario, aplica_bono_productividad, descripcion_reglas) VALUES
(1, 'Nivel 1: Operativo Campo y Empaque', 'MIXTO', 320.00, 650.00, TRUE, 'Jornal base garantizado + destajo por caja/surco + bono semanal por calidad <3% rezaga'),
(2, 'Nivel 2: Supervisión y Control Calidad', 'FIJO_MENSUAL', 450.00, 750.00, TRUE, 'Salario fijo semanal + bono por cumplimiento de meta de cuadrilla y cero rechazos inocuidad'),
(3, 'Nivel 3: Técnico Especializado y Admin', 'FIJO_MENSUAL', 700.00, 1400.00, TRUE, 'Sueldo nominal por banda (Jr/Pleno/Sr) + bono trimestral por KPIs de área'),
(4, 'Nivel 4: Gerencia y Dirección', 'FIJO_MENSUAL', 1500.00, 3500.00, TRUE, 'Sueldo ejecutivo + bono anual ligado a EBITDA por cultivo');

INSERT INTO catalogo_labores (codigo, nombre, categoria, unidad_medida) VALUES
('COSECHA', 'Corte / Cosecha de Fruta', 'COSECHA', 'CAJA'),
('PODA', 'Poda de Formación / Saneamiento', 'LABOR_CULTURAL', 'SURCO'),
('DESHIJE', 'Deshije y Raleo de Brotes', 'LABOR_CULTURAL', 'SURCO'),
('TUTOREO', 'Tutoreo y Amarrado de Caña', 'LABOR_CULTURAL', 'METRO_LINEAL'),
('DESHIERBE', 'Deshierbe Manual de Cama', 'LABOR_CULTURAL', 'METRO_LINEAL');

INSERT INTO reglas_pago_tarifas (nombre_regla, cultivo_id, labor_id, modalidad_pago, tarifa_jornal_base, tarifa_por_unidad, meta_minima_unidades, tarifa_excedente_unidad, porcentaje_rezaga_maximo, bono_calidad_por_unidad, fecha_inicio_vigencia, creado_por) VALUES
('Cosecha Frambuesa Mixta 2026', 1, 1, 'MIXTO_GARANTIA', 330.00, 0.00, 14.00, 24.00, 3.00, 2.00, '2026-01-01', 'SYSTEM_INIT'),
('Cosecha Arándano Destajo 2026', 2, 1, 'DESTAJO_PURO', 0.00, 28.00, 0.00, 28.00, 2.50, 2.50, '2026-01-01', 'SYSTEM_INIT'),
('Cosecha Fresa Mixta 2026', 3, 1, 'MIXTO_GARANTIA', 330.00, 0.00, 18.00, 19.00, 4.00, 1.50, '2026-01-01', 'SYSTEM_INIT'),
('Poda General Jornal 2026', NULL, 2, 'JORNAL_PURO', 340.00, 0.00, 6.00, 0.00, 0.00, 0.00, '2026-01-01', 'SYSTEM_INIT');
