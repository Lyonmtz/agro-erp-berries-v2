-- ============================================================================
-- 08_schema_fase2_rh_merqry.sql
-- Fase 2: RH Completo (Plazas Autorizadas, Perfiles Versionados, Cobertura,
-- Vacantes, Ranking 60/25/15, Dictamenes, Expediente 16 Estados, UPDATE_READY
-- con Excepciones Temporales y Bloqueo Automatico, Responsivas, Contratos,
-- Beneficiarios Art. 501, Bajas/Finiquitos LFT 2026) + Staging/Conciliacion
-- Merqry Estrictamente SOLO LECTURA y Separacion IMSS vs Especial.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. RECLUTAMIENTO CON GOBERNANZA PRE-VACANTE (PLAZAS -> COBERTURA -> VACANTE)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS plazas_autorizadas (
    id SERIAL PRIMARY KEY,
    empresa_id INT NOT NULL REFERENCES empresas(id),
    sucursal_id INT NOT NULL REFERENCES sucursales(id),
    unidad_operativa_id INT REFERENCES unidades_operativas(id),
    puesto_id INT NOT NULL REFERENCES puestos(id),
    codigo_plaza VARCHAR(50) UNIQUE NOT NULL,
    headcount_autorizado INT NOT NULL CHECK (headcount_autorizado > 0),
    headcount_ocupado INT NOT NULL DEFAULT 0 CHECK (headcount_ocupado >= 0),
    estatus VARCHAR(20) NOT NULL DEFAULT 'ACTIVA' CHECK (
        estatus IN ('ACTIVA', 'CONGELADA', 'CANCELADA')
    ),
    autorizado_por_usuario_id UUID REFERENCES usuarios(id),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (headcount_ocupado <= headcount_autorizado)
);

CREATE TABLE IF NOT EXISTS perfiles_puesto_versiones (
    id SERIAL PRIMARY KEY,
    empresa_id INT NOT NULL REFERENCES empresas(id),
    puesto_id INT NOT NULL REFERENCES puestos(id),
    version_numero INT NOT NULL CHECK (version_numero >= 1),
    titulo_perfil VARCHAR(150) NOT NULL,
    objetivo TEXT NOT NULL,
    requisitos_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    competencias_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    vigente BOOLEAN NOT NULL DEFAULT TRUE,
    aprobado_por_usuario_id UUID REFERENCES usuarios(id),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, puesto_id, version_numero)
);

CREATE TABLE IF NOT EXISTS solicitudes_cobertura (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plaza_autorizada_id INT NOT NULL REFERENCES plazas_autorizadas(id),
    perfil_version_id INT NOT NULL REFERENCES perfiles_puesto_versiones(id),
    empresa_id INT NOT NULL REFERENCES empresas(id),
    sucursal_id INT NOT NULL REFERENCES sucursales(id),
    unidad_operativa_id INT REFERENCES unidades_operativas(id),
    cantidad_solicitada INT NOT NULL CHECK (cantidad_solicitada > 0),
    tipo_cobertura VARCHAR(25) NOT NULL CHECK (
        tipo_cobertura IN ('NUEVA_PLAZA', 'REEMPLAZO', 'TEMPORADA')
    ),
    justificacion TEXT NOT NULL,
    estatus VARCHAR(25) NOT NULL DEFAULT 'PENDIENTE' CHECK (
        estatus IN ('PENDIENTE', 'APROBADA', 'RECHAZADA', 'CANCELADA')
    ),
    solicitado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS aprobaciones_cobertura (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    solicitud_cobertura_id UUID NOT NULL REFERENCES solicitudes_cobertura(id) ON DELETE CASCADE,
    nivel_autorizacion SMALLINT NOT NULL CHECK (nivel_autorizacion BETWEEN 1 AND 4),
    decision VARCHAR(20) NOT NULL CHECK (decision IN ('APROBADA', 'RECHAZADA')),
    comentarios TEXT,
    aprobado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
    decidido_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS vacantes (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    solicitud_cobertura_id UUID UNIQUE NOT NULL REFERENCES solicitudes_cobertura(id),
    plaza_autorizada_id INT NOT NULL REFERENCES plazas_autorizadas(id),
    perfil_version_id INT NOT NULL REFERENCES perfiles_puesto_versiones(id),
    empresa_id INT NOT NULL REFERENCES empresas(id),
    sucursal_id INT NOT NULL REFERENCES sucursales(id),
    unidad_operativa_id INT REFERENCES unidades_operativas(id),
    codigo_vacante VARCHAR(50) UNIQUE NOT NULL,
    canal_tipo VARCHAR(20) NOT NULL DEFAULT 'COSECHA' CHECK (
        canal_tipo IN ('COSECHA', 'GENERAL')
    ),
    cantidad_posiciones INT NOT NULL CHECK (cantidad_posiciones > 0),
    estatus VARCHAR(20) NOT NULL DEFAULT 'ABIERTA' CHECK (
        estatus IN ('ABIERTA', 'PAUSADA', 'CERRADA', 'CANCELADA')
    ),
    creado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS publicaciones_vacante (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vacante_id UUID NOT NULL REFERENCES vacantes(id) ON DELETE CASCADE,
    canal VARCHAR(30) NOT NULL CHECK (
        canal IN ('PORTAL_PUBLICO', 'WHATSAPP', 'FERIA_EMPLEO', 'REFERIDO', 'BOLSA_LOCAL', 'INTERNO')
    ),
    fecha_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    fecha_fin DATE,
    activa BOOLEAN NOT NULL DEFAULT TRUE,
    creado_por_usuario_id UUID REFERENCES usuarios(id),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS postulaciones_rh (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    vacante_id UUID NOT NULL REFERENCES vacantes(id) ON DELETE CASCADE,
    empresa_id INT NOT NULL REFERENCES empresas(id),
    curp VARCHAR(18) NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    apellido_paterno VARCHAR(100) NOT NULL,
    apellido_materno VARCHAR(100),
    telefono VARCHAR(25) NOT NULL,
    categoria_candidato VARCHAR(20) NOT NULL DEFAULT 'EXTERNO' CHECK (
        categoria_candidato IN ('EXTERNO', 'REINGRESO', 'INTERNO')
    ),
    alerta_reingreso JSONB NOT NULL DEFAULT '{}'::jsonb,
    score_evaluacion NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (score_evaluacion BETWEEN 0 AND 100),
    score_entrevista NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (score_entrevista BETWEEN 0 AND 100),
    score_experiencia NUMERIC(5,2) NOT NULL DEFAULT 0 CHECK (score_experiencia BETWEEN 0 AND 100),
    ranking_ponderado_60_25_15 NUMERIC(5,2) GENERATED ALWAYS AS (
        ROUND((score_evaluacion * 0.60) + (score_entrevista * 0.25) + (score_experiencia * 0.15), 2)
    ) STORED,
    estatus VARCHAR(25) NOT NULL DEFAULT 'POSTULADO' CHECK (
        estatus IN ('POSTULADO', 'EVALUADO', 'DICTAMINADO', 'TRASPASADO_PERSONAL', 'RECHAZADO')
    ),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (vacante_id, curp)
);

CREATE TABLE IF NOT EXISTS dictamenes_ingreso_reingreso (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    postulacion_id UUID UNIQUE NOT NULL REFERENCES postulaciones_rh(id) ON DELETE CASCADE,
    empresa_id INT NOT NULL REFERENCES empresas(id),
    decision VARCHAR(25) NOT NULL CHECK (
        decision IN ('APROBADO_INGRESO', 'APROBADO_REINGRESO', 'RECHAZADO', 'LISTA_NEGRA')
    ),
    justificacion TEXT NOT NULL,
    dictaminado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
    traspasado_a_relacion_id UUID REFERENCES relaciones_laborales(id),
    dictaminado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 2. ADMINISTRACION DE PERSONAL: EXPEDIENTE 16 ESTADOS, UPDATE_READY,
--    RESPONSIVAS, CONTRATOS, BENEFICIARIOS ART. 501 Y FINIQUITOS LFT 2026
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS expedientes_personal (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    relacion_laboral_id UUID UNIQUE NOT NULL REFERENCES relaciones_laborales(id) ON DELETE CASCADE,
    persona_id UUID NOT NULL REFERENCES personas(id),
    empresa_id INT NOT NULL REFERENCES empresas(id),
    sucursal_id INT REFERENCES sucursales(id),
    unidad_operativa_id INT REFERENCES unidades_operativas(id),
    estatus VARCHAR(30) NOT NULL DEFAULT 'BORRADOR' CHECK (
        estatus IN (
            'BORRADOR', 'PREALTA', 'DOCUMENTOS_PENDIENTES', 'DOCUMENTOS_CARGADOS',
            'DOCUMENTOS_OBSERVADOS', 'DOCUMENTOS_VALIDADOS', 'CONTRATO_GENERADO',
            'CONTRATO_FIRMADO', 'CAPACITACION_PENDIENTE', 'CAPACITACION_COMPLETA',
            'LISTO_PARA_TRABAJAR', 'LISTO_MERQRY', 'LISTO_PRENOMINA',
            'ACTIVO', 'BAJA', 'ARCHIVADO'
        )
    ),
    capacitacion_impartida BOOLEAN NOT NULL DEFAULT FALSE,
    capacitacion_validada BOOLEAN NOT NULL DEFAULT FALSE,
    alta_interna_completa BOOLEAN NOT NULL DEFAULT FALSE,
    alta_imss_confirmada BOOLEAN NOT NULL DEFAULT FALSE,
    epp_critico_entregado BOOLEAN NOT NULL DEFAULT FALSE,
    bloqueado_por_excepcion_vencida BOOLEAN NOT NULL DEFAULT FALSE,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    actualizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Invariante: no puede estar validada la capacitacion si no fue impartida
    CHECK (NOT capacitacion_validada OR capacitacion_impartida)
);

CREATE TABLE IF NOT EXISTS update_ready_excepciones (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    expediente_id UUID NOT NULL REFERENCES expedientes_personal(id) ON DELETE CASCADE,
    empresa_id INT NOT NULL REFERENCES empresas(id),
    nivel_accion VARCHAR(25) NOT NULL CHECK (
        nivel_accion IN ('VALIDACION_RAPIDA', 'VALIDACION_CRITICA', 'EXCEPCION_TEMPORAL')
    ),
    requisito_omitido VARCHAR(80) NOT NULL,
    motivo TEXT NOT NULL,
    responsable_usuario_id UUID NOT NULL REFERENCES usuarios(id),
    autorizado_por_usuario_id UUID NOT NULL REFERENCES usuarios(id),
    fecha_limite DATE,
    estatus VARCHAR(25) NOT NULL DEFAULT 'VIGENTE' CHECK (
        estatus IN ('VIGENTE', 'RESUELTA', 'VENCIDA_BLOQUEADA', 'CANCELADA')
    ),
    resuelta_en TIMESTAMPTZ,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (nivel_accion <> 'EXCEPCION_TEMPORAL' OR fecha_limite IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS responsivas_personal (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    relacion_laboral_id UUID NOT NULL REFERENCES relaciones_laborales(id) ON DELETE CASCADE,
    empresa_id INT NOT NULL REFERENCES empresas(id),
    tipo_responsiva VARCHAR(20) NOT NULL CHECK (
        tipo_responsiva IN ('UNIFORME', 'EPP', 'HERRAMIENTA', 'EQUIPO', 'VEHICULO', 'FONDO')
    ),
    es_critico_operacion BOOLEAN NOT NULL DEFAULT FALSE,
    descripcion_items JSONB NOT NULL,
    descuento_autorizado_explicitamente BOOLEAN NOT NULL DEFAULT FALSE,
    entregado_por_usuario_id UUID REFERENCES usuarios(id),
    firmado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contratos_laborales (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    relacion_laboral_id UUID NOT NULL REFERENCES relaciones_laborales(id) ON DELETE CASCADE,
    empresa_id INT NOT NULL REFERENCES empresas(id),
    tipo_contrato VARCHAR(30) NOT NULL CHECK (
        tipo_contrato IN ('TEMPORADA', 'INDETERMINADO', 'OBRA_DETERMINADA', 'CAPACITACION_INICIAL')
    ),
    salario_diario NUMERIC(10,2) NOT NULL CHECK (salario_diario > 0),
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE,
    estatus VARCHAR(20) NOT NULL DEFAULT 'BORRADOR' CHECK (
        estatus IN ('BORRADOR', 'VALIDADO', 'FIRMADO', 'TERMINADO', 'CANCELADO')
    ),
    -- Regla legal estricta: prohibida renuncia anticipada pre-firmada
    incluye_renuncia_anticipada BOOLEAN NOT NULL DEFAULT FALSE CHECK (incluye_renuncia_anticipada = FALSE),
    hash_documento VARCHAR(64),
    validado_por_usuario_id UUID REFERENCES usuarios(id),
    validado_en TIMESTAMPTZ,
    firmado_en TIMESTAMPTZ,
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS beneficiarios_art501 (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    relacion_laboral_id UUID NOT NULL REFERENCES relaciones_laborales(id) ON DELETE CASCADE,
    empresa_id INT NOT NULL REFERENCES empresas(id),
    nombre_completo VARCHAR(150) NOT NULL,
    parentesco VARCHAR(50) NOT NULL,
    porcentaje_asignado NUMERIC(5,2) NOT NULL CHECK (porcentaje_asignado > 0 AND porcentaje_asignado <= 100),
    telefono_contacto VARCHAR(25),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS bajas_finiquitos_lft (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    relacion_laboral_id UUID NOT NULL REFERENCES relaciones_laborales(id),
    empresa_id INT NOT NULL REFERENCES empresas(id),
    circuito_pago VARCHAR(30) NOT NULL CHECK (
        circuito_pago IN ('IMSS_MERQRY', 'ESPECIAL_CONTABILIDAD')
    ),
    fecha_ingreso DATE NOT NULL,
    fecha_baja DATE NOT NULL,
    motivo_baja VARCHAR(40) NOT NULL CHECK (
        motivo_baja IN ('RENUNCIA_VOLUNTARIA', 'TERMINO_TEMPORADA', 'DESPIDO_JUSTIFICADO', 'DESPIDO_INJUSTIFICADO', 'MUTUO_ACUERDO')
    ),
    salario_diario NUMERIC(10,2) NOT NULL CHECK (salario_diario > 0),
    dias_trabajados_anio INT NOT NULL CHECK (dias_trabajados_anio >= 0),
    aguinaldo_proporcional NUMERIC(12,2) NOT NULL DEFAULT 0,
    vacaciones_proporcionales NUMERIC(12,2) NOT NULL DEFAULT 0,
    prima_vacacional NUMERIC(12,2) NOT NULL DEFAULT 0,
    salarios_pendientes NUMERIC(12,2) NOT NULL DEFAULT 0,
    prima_antiguedad NUMERIC(12,2) NOT NULL DEFAULT 0,
    indemnizacion_constitucional NUMERIC(12,2) NOT NULL DEFAULT 0,
    deducciones_autorizadas NUMERIC(12,2) NOT NULL DEFAULT 0,
    total_neto_finiquito NUMERIC(12,2) NOT NULL,
    desglose_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    estatus VARCHAR(20) NOT NULL DEFAULT 'BORRADOR' CHECK (
        estatus IN ('BORRADOR', 'AUTORIZADO', 'PAGADO', 'CANCELADO')
    ),
    calculado_por_usuario_id UUID REFERENCES usuarios(id),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK (fecha_baja >= fecha_ingreso)
);

-- ----------------------------------------------------------------------------
-- 3. STAGING Y CONCILIACION MERQRY (ESTRICTAMENTE SOLO LECTURA HACIA MERQRY)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS merqry_staging_empleados (
    id BIGSERIAL PRIMARY KEY,
    empresa_id INT NOT NULL REFERENCES empresas(id),
    merqry_employee_id VARCHAR(50) NOT NULL,
    curp VARCHAR(18),
    nombre_completo VARCHAR(180) NOT NULL,
    puesto_nominal_merqry VARCHAR(120),
    estatus_merqry VARCHAR(30) NOT NULL DEFAULT 'ALTA',
    salario_diario_imss NUMERIC(10,2),
    fuente_lectura VARCHAR(60) NOT NULL DEFAULT 'READONLY_SNAPSHOT',
    sincronizado_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, merqry_employee_id)
);

CREATE TABLE IF NOT EXISTS merqry_exports_nomina (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    empresa_id INT NOT NULL REFERENCES empresas(id),
    circuito_destino VARCHAR(30) NOT NULL CHECK (
        circuito_destino IN ('IMSS_MERQRY', 'ESPECIAL_CONTABILIDAD')
    ),
    periodo_label VARCHAR(40) NOT NULL,
    total_registros INT NOT NULL DEFAULT 0,
    payload_export JSONB NOT NULL,
    generado_por_usuario_id UUID REFERENCES usuarios(id),
    creado_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ----------------------------------------------------------------------------
-- 4. PERMISOS FASE 2 Y ASIGNACION A ROLES
-- ----------------------------------------------------------------------------
INSERT INTO permisos (codigo, modulo, descripcion) VALUES
    ('rh.plazas.gestionar',       'reclutamiento', 'Crear y administrar plazas autorizadas y versiones de perfil'),
    ('rh.cobertura.solicitar',    'reclutamiento', 'Crear solicitudes de cobertura sobre plazas autorizadas'),
    ('rh.cobertura.aprobar',      'reclutamiento', 'Aprobar o rechazar solicitudes de cobertura (L3+)'),
    ('rh.vacantes.gestionar',     'reclutamiento', 'Crear vacantes, publicaciones, evaluar ranking 60/25/15 y dictaminar'),
    ('rh.expediente.gestionar',   'personal',      'Administrar expediente 16 estados, responsivas, contratos y beneficiarios'),
    ('rh.update_ready.autorizar', 'personal',      'Autorizar validaciones y excepciones temporales UPDATE_READY'),
    ('rh.finiquitos.calcular',    'personal',      'Calcular y registrar bajas/finiquitos LFT 2026'),
    ('merqry.leer_conciliar',     'merqry_sync',   'Leer staging Merqry solo lectura, conciliar y generar exports separados')
ON CONFLICT (codigo) DO UPDATE SET
    modulo      = EXCLUDED.modulo,
    descripcion = EXCLUDED.descripcion;

INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM roles r
JOIN permisos p ON (
    r.codigo IN ('DIRECCION_GENERAL', 'ADMIN_SISTEMA')
    OR (r.codigo = 'JEFE_RH' AND p.codigo IN (
        'rh.plazas.gestionar', 'rh.cobertura.solicitar', 'rh.cobertura.aprobar',
        'rh.vacantes.gestionar', 'rh.expediente.gestionar', 'rh.update_ready.autorizar',
        'rh.finiquitos.calcular', 'merqry.leer_conciliar'
    ))
    OR (r.codigo = 'GERENTE_OPERACIONES' AND p.codigo IN (
        'rh.cobertura.solicitar', 'rh.cobertura.aprobar', 'rh.update_ready.autorizar'
    ))
    OR (r.codigo = 'AUXILIAR_RH' AND p.codigo IN (
        'rh.vacantes.gestionar', 'rh.expediente.gestionar'
    ))
    OR (r.codigo = 'CONTABILIDAD' AND p.codigo IN (
        'rh.finiquitos.calcular', 'merqry.leer_conciliar'
    ))
)
ON CONFLICT DO NOTHING;
