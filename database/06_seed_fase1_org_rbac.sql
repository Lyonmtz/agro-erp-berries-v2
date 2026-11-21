-- ============================================================================
-- 06_seed_fase1_org_rbac.sql
-- Seeds iniciales idempotentes de Fase 1:
-- Empresas NFA/BIO, Sucursales (1 matriz/empresa) + Funciones, Unidades
-- Operativas, Areas, Localizaciones Fisicas, Tipos de Documento, Roles (L1-L4),
-- Permisos, Usuarios con alcance real y Backfill de Identidad desde empleados.
-- ============================================================================

-- 1. Empresas (razon social oficial verificada en contratos y rrhh-automation-system)
INSERT INTO empresas (clave, razon_social, nombre_comercial, tipo_persona, activa) VALUES
    ('NFA', 'Natural Fruits of America, S.P.R. de R.L. de C.V.', 'Natural Fruits of America', 'MORAL', TRUE),
    ('BIO', 'Bio-Orgánicos Saludables, S.P.R. de R.L. de C.V.',  'Bio-Orgánicos Saludables',  'MORAL', TRUE)
ON CONFLICT (clave) DO UPDATE SET
    razon_social     = EXCLUDED.razon_social,
    nombre_comercial = EXCLUDED.nombre_comercial,
    activa           = TRUE;

-- 2. Sucursales (exactamente 1 matriz por empresa)
INSERT INTO sucursales (
    empresa_id, clave, nombre, naturaleza_sucursal, es_matriz, direccion, municipio, estado, codigo_postal, activa
)
SELECT
    e.id, v.clave, v.nombre, v.nat, v.es_matriz, v.dir, v.mun, v.edo, v.cp, TRUE
FROM (VALUES
    ('NFA', 'NFA-MATRIZ', 'Matriz Operativa NFA — Actopan / Pachuca', 'MATRIZ', TRUE,
        'Km 3.5 Camino Cañada Chica, Actopan / Blvd. Minero 1802 Int. 1D, Pachuca', 'Actopan', 'Hidalgo', '42039'),
    ('BIO', 'BIO-MATRIZ', 'Matriz Operativa BIO — Actopan', 'MATRIZ', TRUE,
        'Predio Principal Bio-Orgánicos, Actopan, Hidalgo', 'Actopan', 'Hidalgo', '42500')
) AS v(emp_clave, clave, nombre, nat, es_matriz, dir, mun, edo, cp)
JOIN empresas e ON e.clave = v.emp_clave
ON CONFLICT (empresa_id, clave) DO UPDATE SET
    nombre              = EXCLUDED.nombre,
    naturaleza_sucursal = EXCLUDED.naturaleza_sucursal,
    es_matriz           = EXCLUDED.es_matriz,
    direccion           = EXCLUDED.direccion,
    activa              = TRUE;

-- 3. Funciones habilitadas por sucursal
INSERT INTO sucursal_funciones (sucursal_id, funcion, activa)
SELECT s.id, f.funcion, TRUE
FROM sucursales s
JOIN empresas e ON e.id = s.empresa_id
CROSS JOIN (VALUES
    ('produccion'), ('rh'), ('empaque'), ('inocuidad'), ('almacen'),
    ('contabilidad'), ('comercializacion'), ('postcosecha'), ('calidad'),
    ('mantenimiento'), ('villas'), ('comedor'), ('transporte'),
    ('compras'), ('direccion'), ('sistemas'), ('tecnico'), ('nomina')
) AS f(funcion)
WHERE (e.clave = 'NFA' AND s.clave = 'NFA-MATRIZ')
   OR (e.clave = 'BIO' AND s.clave = 'BIO-MATRIZ' AND f.funcion IN (
       'produccion', 'rh', 'inocuidad', 'almacen', 'contabilidad',
       'comercializacion', 'calidad', 'tecnico', 'nomina', 'direccion'
   ))
ON CONFLICT (sucursal_id, funcion) DO UPDATE SET activa = TRUE;

-- Vincular ranchos de Fase 0 a empresas y sucursales matriz
UPDATE ranchos r
   SET empresa_id  = e.id,
       sucursal_id = s.id
  FROM empresas e
  JOIN sucursales s ON s.empresa_id = e.id AND s.es_matriz = TRUE
 WHERE r.empresa_clave = e.clave
   AND (r.empresa_id IS NULL OR r.sucursal_id IS NULL);

-- 4. Unidades Operativas
INSERT INTO unidades_operativas (empresa_id, sucursal_id, clave, nombre, tipo_unidad, rancho_id, activa)
SELECT e.id, s.id, v.clave, v.nombre, v.tipo_unidad, r.id, TRUE
FROM (VALUES
    ('NFA', 'NFA-MATRIZ', 'NFA-UO-FRAMB',   'Unidad Frambuesa NFA (M1–M11 y M1.1)', 'BLOQUE_MODULOS', 'NFA-PRINCIPAL'),
    ('NFA', 'NFA-MATRIZ', 'NFA-UO-FRESA',   'Unidad Fresa NFA (M21–M22)',           'BLOQUE_MODULOS', 'NFA-PRINCIPAL'),
    ('NFA', 'NFA-MATRIZ', 'NFA-UO-EMPAQUE', 'Empaque, Cuarto Frío y Postcosecha NFA','EMPAQUE',       'NFA-PRINCIPAL'),
    ('BIO', 'BIO-MATRIZ', 'BIO-UO-ARAND',   'Unidad Arándano BIO (M1.2, M2.1, M2.2)','BLOQUE_MODULOS','BIO-PRINCIPAL')
) AS v(emp_clave, suc_clave, clave, nombre, tipo_unidad, rancho_cod)
JOIN empresas e ON e.clave = v.emp_clave
JOIN sucursales s ON s.empresa_id = e.id AND s.clave = v.suc_clave
LEFT JOIN ranchos r ON r.codigo = v.rancho_cod
ON CONFLICT (empresa_id, clave) DO UPDATE SET
    nombre      = EXCLUDED.nombre,
    tipo_unidad = EXCLUDED.tipo_unidad,
    rancho_id   = EXCLUDED.rancho_id,
    activa      = TRUE;

-- Vincular lotes_produccion de Fase 0 a empresa_id y unidad_operativa_id
UPDATE lotes_produccion l
   SET empresa_id = e.id,
       unidad_operativa_id = uo.id
  FROM empresas e
  JOIN cultivos c ON TRUE
  JOIN unidades_operativas uo ON uo.empresa_id = e.id
 WHERE l.empresa_clave = e.clave
   AND l.cultivo_id = c.id
   AND (
       (c.codigo = 'FRAMB' AND uo.clave = 'NFA-UO-FRAMB')
       OR (c.codigo = 'FRESA' AND uo.clave = 'NFA-UO-FRESA')
       OR (c.codigo = 'ARAND' AND uo.clave = 'BIO-UO-ARAND')
   )
   AND (l.empresa_id IS NULL OR l.unidad_operativa_id IS NULL);

-- 5. Areas por empresa vinculadas a departamentos
INSERT INTO areas (empresa_id, sucursal_id, unidad_operativa_id, departamento_id, clave, nombre, activa)
SELECT e.id, s.id, uo.id, d.id, v.clave, v.nombre, TRUE
FROM (VALUES
    ('NFA', 'NFA-MATRIZ', 'NFA-UO-FRAMB',   'PROD', 'NFA-AREA-PROD-FRAMB', 'Producción Frambuesa NFA'),
    ('NFA', 'NFA-MATRIZ', 'NFA-UO-FRESA',   'PROD', 'NFA-AREA-PROD-FRESA', 'Producción Fresa NFA'),
    ('NFA', 'NFA-MATRIZ', 'NFA-UO-EMPAQUE', 'LOG',  'NFA-AREA-EMPAQUE',    'Empaque y Postcosecha NFA'),
    ('NFA', 'NFA-MATRIZ', NULL,             'RH',   'NFA-AREA-RH',         'Recursos Humanos NFA'),
    ('NFA', 'NFA-MATRIZ', NULL,             'TEC',  'NFA-AREA-TEC',        'Área Técnica e Inocuidad NFA'),
    ('BIO', 'BIO-MATRIZ', 'BIO-UO-ARAND',   'PROD', 'BIO-AREA-PROD-ARAND', 'Producción Arándano BIO'),
    ('BIO', 'BIO-MATRIZ', NULL,             'RH',   'BIO-AREA-RH',         'Recursos Humanos BIO')
) AS v(emp_clave, suc_clave, uo_clave, dep_cod, clave, nombre)
JOIN empresas e ON e.clave = v.emp_clave
JOIN sucursales s ON s.empresa_id = e.id AND s.clave = v.suc_clave
LEFT JOIN unidades_operativas uo ON uo.empresa_id = e.id AND uo.clave = v.uo_clave
LEFT JOIN departamentos d ON d.codigo = v.dep_cod
ON CONFLICT (empresa_id, clave) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    activa = TRUE;

-- 6. Localizaciones fisicas: 17 lotes activos + infraestructura critica (camara fria, empaque, comedor)
INSERT INTO localizaciones_fisicas (
    empresa_id, sucursal_id, unidad_operativa_id, lote_id, clave, nombre, tipo_localizacion, activa
)
SELECT
    l.empresa_id,
    uo.sucursal_id,
    l.unidad_operativa_id,
    l.id,
    'LOC-' || l.codigo_lote,
    l.nombre_sector,
    CASE
        WHEN l.tipo_estructura = 'MACRO_TUNEL' THEN 'macrotunel'
        ELSE 'invernadero'
    END,
    TRUE
FROM lotes_produccion l
JOIN unidades_operativas uo ON uo.id = l.unidad_operativa_id
WHERE l.activo = TRUE
ON CONFLICT (empresa_id, clave) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    lote_id = EXCLUDED.lote_id,
    activa = TRUE;

INSERT INTO localizaciones_fisicas (
    empresa_id, sucursal_id, unidad_operativa_id, clave, nombre, tipo_localizacion, activa
)
SELECT e.id, s.id, uo.id, v.clave, v.nombre, v.tipo, TRUE
FROM (VALUES
    ('NFA', 'NFA-MATRIZ', 'NFA-UO-EMPAQUE', 'LOC-NFA-CAMARA-FRIA-01', 'Cámara Fría Principal NFA', 'camara_fria'),
    ('NFA', 'NFA-MATRIZ', 'NFA-UO-EMPAQUE', 'LOC-NFA-LINEA-EMP-01',   'Línea de Empaque Berries NFA', 'linea_empaque'),
    ('NFA', 'NFA-MATRIZ', 'NFA-UO-FRAMB',   'LOC-NFA-COMEDOR-01',     'Comedor Operativo NFA', 'comedor'),
    ('BIO', 'BIO-MATRIZ', 'BIO-UO-ARAND',   'LOC-BIO-BOMBAS-01',      'Cuarto de Bombas Arándano BIO', 'cuarto_bombas')
) AS v(emp_clave, suc_clave, uo_clave, clave, nombre, tipo)
JOIN empresas e ON e.clave = v.emp_clave
JOIN sucursales s ON s.empresa_id = e.id AND s.clave = v.suc_clave
JOIN unidades_operativas uo ON uo.empresa_id = e.id AND uo.clave = v.uo_clave
ON CONFLICT (empresa_id, clave) DO UPDATE SET
    nombre = EXCLUDED.nombre,
    activa = TRUE;

-- 7. Catalogo de tipos de documento (incluye bloqueo legal a RENUNCIA_ANTICIPADA)
INSERT INTO catalogo_tipos_documento (
    codigo, nombre, categoria, requiere_vigencia, bloquea_operacion, prohibido_legal, activo
) VALUES
    ('INE',                  'Identificación Oficial Vigente (INE)',   'IDENTIDAD',  TRUE,  TRUE,  FALSE, TRUE),
    ('CURP',                 'Constancia CURP',                        'IDENTIDAD',  FALSE, TRUE,  FALSE, TRUE),
    ('RFC_CSF',              'Constancia de Situación Fiscal (RFC)',   'FISCAL',     FALSE, FALSE, FALSE, TRUE),
    ('NSS_IMSS',             'Número de Seguridad Social (IMSS)',      'LABORAL',    FALSE, FALSE, FALSE, TRUE),
    ('CONTRATO_LABORAL',     'Contrato Individual de Trabajo',         'LABORAL',    TRUE,  TRUE,  FALSE, TRUE),
    ('ACUSE_REGLAMENTO',     'Acuse de Reglamento Interior y Pago',    'LABORAL',    FALSE, TRUE,  FALSE, TRUE),
    ('RESPONSIVA_EPP',       'Responsiva de EPP / Herramienta',        'OPERATIVO',  FALSE, TRUE,  FALSE, TRUE),
    ('CARTA_VILLAS',         'Carta de Hospedaje y Reglamento Villas', 'OPERATIVO',  FALSE, FALSE, FALSE, TRUE),
    ('CERTIFICADO_BPA',      'Constancia de Inducción Inocuidad BPA',  'INOCUIDAD',  TRUE,  TRUE,  FALSE, TRUE),
    ('CONTRATO_COMERCIAL',   'Contrato Comercial / Adéndum',           'COMERCIAL',  TRUE,  FALSE, FALSE, TRUE),
    ('RENUNCIA_ANTICIPADA',  'Renuncia Anticipada Pre-firmada (PROHIBIDA)', 'LABORAL', FALSE, FALSE, TRUE, TRUE)
ON CONFLICT (codigo) DO UPDATE SET
    nombre            = EXCLUDED.nombre,
    prohibido_legal   = EXCLUDED.prohibido_legal,
    bloquea_operacion = EXCLUDED.bloquea_operacion,
    activo            = TRUE;

-- 8. Roles (4 niveles de autorizacion L1-L4) y Permisos granulares
INSERT INTO roles (codigo, nombre, nivel_autorizacion, descripcion, activo) VALUES
    ('DIRECCION_GENERAL',   'Dirección General',                  4, 'Autoridad ejecutiva L4 sobre NFA y BIO', TRUE),
    ('ADMIN_SISTEMA',       'Administrador del Sistema',          4, 'Administración de seguridad, catálogos y auditoría', TRUE),
    ('GERENTE_OPERACIONES', 'Gerente de Operaciones / Agrícola',  3, 'Gestión operativa integral multi-unidad', TRUE),
    ('JEFE_RH',             'Jefe de Recursos Humanos',           3, 'Contratación, expedientes, identidad y ETL RH', TRUE),
    ('AUXILIAR_RH',         'Auxiliar de Recursos Humanos',       2, 'Captura y revisión documental RH', TRUE),
    ('SUPERVISOR_CAMPO',    'Supervisor de Campo',                2, 'Operación en unidad asignada y funciones temporales', TRUE),
    ('PESADOR_CAMPO',       'Pesador / Capturista de Módulo',     1, 'Captura de cosecha/recepción en unidad asignada', TRUE),
    ('TECNICO_INOCUIDAD',   'Ingeniero Técnico / Inocuidad',      2, 'Aplicaciones fitosanitarias, PHI/REI e inocuidad', TRUE),
    ('CONTABILIDAD',        'Contabilidad y Costos',              3, 'Consulta de nómina especial, CxC y costeo Merqry solo lectura', TRUE)
ON CONFLICT (codigo) DO UPDATE SET
    nombre             = EXCLUDED.nombre,
    nivel_autorizacion = EXCLUDED.nivel_autorizacion,
    descripcion        = EXCLUDED.descripcion,
    activo             = TRUE;

INSERT INTO permisos (codigo, modulo, descripcion) VALUES
    ('org.leer',                  'core_org',      'Consultar jerarquía organizacional dentro del alcance'),
    ('org.escribir',              'core_org',      'Crear/actualizar sucursales, unidades, áreas y localizaciones'),
    ('auth.gestionar',            'auth_usuarios', 'Crear usuarios y asignar roles/alcances'),
    ('auth.nip.gestionar',        'auth_usuarios', 'Establecer NIPs hasheados de personal'),
    ('auth.nip.verificar',        'auth_usuarios', 'Verificar NIP de confirmación en campo/oficina'),
    ('documentos.leer',           'documentos',    'Consultar documentos de entidades y códigos alternativos'),
    ('documentos.escribir',       'documentos',    'Registrar documentos de entidades y códigos alternativos'),
    ('documentos.validar',        'documentos',    'Validar o rechazar documentos cargados'),
    ('identidad.leer',            'identidad',     'Consultar personas y relaciones laborales en alcance'),
    ('identidad.escribir',        'identidad',     'Dar de alta personas y relaciones laborales'),
    ('identidad.funcion_temporal','identidad',     'Asignar/cerrar funciones operativas temporales sin tocar puesto nominal'),
    ('identidad.etl',             'identidad',     'Ejecutar importación ETL auditable y revisar cuarentena'),
    ('campo.cosecha.registrar',   'cosecha',       'Registrar cosecha y captura operativa en campo'),
    ('rh.candidatos.leer',        'reclutamiento', 'Consultar candidatos y evaluaciones'),
    ('rh.contratar',              'personal',      'Formalizar contrataciones y relaciones laborales'),
    ('rh.prenomina.leer',         'prenomina',     'Consultar prenómina'),
    ('direccion.dashboard.leer',  'direccion_bi',  'Consultar tablero ejecutivo y rentabilidad'),
    ('auditoria.leer',            'auditoria',     'Consultar bitácora universal de auditoría')
ON CONFLICT (codigo) DO UPDATE SET
    modulo      = EXCLUDED.modulo,
    descripcion = EXCLUDED.descripcion;

-- Matriz roles_permisos
INSERT INTO roles_permisos (rol_id, permiso_id)
SELECT r.id, p.id
FROM roles r
JOIN permisos p ON (
    r.codigo IN ('DIRECCION_GENERAL', 'ADMIN_SISTEMA')
    OR (r.codigo = 'GERENTE_OPERACIONES' AND p.codigo IN (
        'org.leer', 'org.escribir', 'auth.nip.verificar', 'documentos.leer', 'documentos.escribir',
        'identidad.leer', 'identidad.funcion_temporal', 'campo.cosecha.registrar', 'rh.prenomina.leer', 'direccion.dashboard.leer'
    ))
    OR (r.codigo = 'JEFE_RH' AND p.codigo IN (
        'org.leer', 'auth.nip.gestionar', 'auth.nip.verificar',
        'documentos.leer', 'documentos.escribir', 'documentos.validar',
        'identidad.leer', 'identidad.escribir', 'identidad.funcion_temporal', 'identidad.etl',
        'rh.candidatos.leer', 'rh.contratar', 'rh.prenomina.leer', 'auditoria.leer'
    ))
    OR (r.codigo = 'AUXILIAR_RH' AND p.codigo IN (
        'org.leer', 'documentos.leer', 'documentos.escribir',
        'identidad.leer', 'identidad.escribir', 'rh.candidatos.leer'
    ))
    OR (r.codigo = 'SUPERVISOR_CAMPO' AND p.codigo IN (
        'org.leer', 'auth.nip.verificar', 'documentos.leer',
        'identidad.leer', 'identidad.funcion_temporal', 'campo.cosecha.registrar'
    ))
    OR (r.codigo = 'PESADOR_CAMPO' AND p.codigo IN (
        'org.leer', 'auth.nip.verificar', 'campo.cosecha.registrar'
    ))
    OR (r.codigo = 'TECNICO_INOCUIDAD' AND p.codigo IN (
        'org.leer', 'documentos.leer', 'documentos.escribir', 'documentos.validar'
    ))
    OR (r.codigo = 'CONTABILIDAD' AND p.codigo IN (
        'org.leer', 'documentos.leer', 'rh.prenomina.leer', 'direccion.dashboard.leer'
    ))
)
ON CONFLICT DO NOTHING;

-- 9. Backfill idempotente de empleados iniciales (Fase 0) -> personas + relaciones_laborales + codigos_alternativos
INSERT INTO personas (
    curp, rfc, nss, nombre, apellido_paterno, apellido_materno, clave_interna_qr, activo
)
SELECT
    e.curp, e.rfc, e.nss, e.nombre, e.apellido_paterno, e.apellido_materno, e.codigo_qr_hash, TRUE
FROM empleados e
WHERE e.numero_empleado IN ('EMP-1001', 'EMP-2001', 'EMP-1002')
ON CONFLICT (curp) DO UPDATE SET
    nombre           = EXCLUDED.nombre,
    apellido_paterno = EXCLUDED.apellido_paterno,
    apellido_materno = EXCLUDED.apellido_materno,
    actualizado_en   = NOW();

INSERT INTO relaciones_laborales (
    persona_id, empresa_id, sucursal_id, unidad_operativa_id, empleado_legacy_id,
    numero_empleado, merqry_employee_id, circuito_pago, puesto_nominal_id, fecha_ingreso, estatus
)
SELECT
    p.id,
    emp.id,
    s.id,
    uo.id,
    e.id,
    e.numero_empleado,
    e.merqry_employee_id,
    'IMSS_MERQRY',
    e.puesto_id,
    e.fecha_ingreso,
    'ACTIVO'
FROM empleados e
JOIN personas p ON p.curp = e.curp
JOIN empresas emp ON emp.clave = 'NFA'
JOIN sucursales s ON s.empresa_id = emp.id AND s.es_matriz = TRUE
JOIN unidades_operativas uo ON uo.empresa_id = emp.id AND uo.clave = 'NFA-UO-FRAMB'
WHERE e.numero_empleado IN ('EMP-1001', 'EMP-2001', 'EMP-1002')
ON CONFLICT (empresa_id, numero_empleado) DO UPDATE SET
    merqry_employee_id = EXCLUDED.merqry_employee_id,
    puesto_nominal_id  = EXCLUDED.puesto_nominal_id,
    actualizado_en     = NOW();

INSERT INTO codigos_alternativos (tipo_entidad, id_entidad, sistema_origen, codigo_externo, descripcion)
SELECT 'PERSONA', p.id::text, 'INTERNO_QR', p.clave_interna_qr, 'Clave QR interna canónica'
FROM personas p
ON CONFLICT (sistema_origen, tipo_entidad, codigo_externo) DO NOTHING;

INSERT INTO codigos_alternativos (tipo_entidad, id_entidad, sistema_origen, codigo_externo, descripcion)
SELECT 'RELACION_LABORAL', rl.id::text, 'MERQRY', rl.merqry_employee_id, 'Identificador Merqry (solo lectura)'
FROM relaciones_laborales rl
WHERE rl.merqry_employee_id IS NOT NULL
ON CONFLICT (sistema_origen, tipo_entidad, codigo_externo) DO NOTHING;

-- 10. Usuarios iniciales con passwords hasheados con bcrypt (via pgcrypto crypt/bf)
INSERT INTO usuarios (username, email, nombre_completo, password_hash, persona_id, activo)
SELECT
    v.username,
    v.email,
    v.nombre,
    crypt(v.raw_pwd, gen_salt('bf', 10)),
    p.id,
    TRUE
FROM (VALUES
    ('admin.dir', 'direccion@nfamexico.com',  'Dirección General NFA/BIO',    'AdminBerries2026!', NULL),
    ('rh.nfa',    'rh.nfa@nfamexico.com',     'Jefatura RH NFA',              'RhNfa2026!',        NULL),
    ('sup.framb', 'sup.framb@nfamexico.com',  'Carlos Mendoza Ríos (Framb)',  'SupFramb2026!',     'SUPC900101HHG00101'),
    ('sup.bio',   'sup.bio@bioorganicos.mx',  'Supervisor Arándano BIO',      'SupBio2026!',       NULL)
) AS v(username, email, nombre, raw_pwd, persona_curp)
LEFT JOIN personas p ON p.curp = v.persona_curp
ON CONFLICT (username) DO NOTHING;

-- Asignacion de roles con alcances diferenciados (global vs empresa NFA vs unidad NFA-UO-FRAMB vs BIO-UO-ARAND)
INSERT INTO usuarios_roles (usuario_id, rol_id, empresa_id, sucursal_id, unidad_operativa_id, alcance_global, activo)
SELECT u.id, r.id, NULL, NULL, NULL, TRUE, TRUE
FROM usuarios u
JOIN roles r ON r.codigo = 'DIRECCION_GENERAL'
WHERE u.username = 'admin.dir'
  AND NOT EXISTS (
      SELECT 1 FROM usuarios_roles ur WHERE ur.usuario_id = u.id AND ur.rol_id = r.id
  );

INSERT INTO usuarios_roles (usuario_id, rol_id, empresa_id, sucursal_id, unidad_operativa_id, alcance_global, activo)
SELECT u.id, r.id, e.id, NULL, NULL, FALSE, TRUE
FROM usuarios u
JOIN roles r ON r.codigo = 'JEFE_RH'
JOIN empresas e ON e.clave = 'NFA'
WHERE u.username = 'rh.nfa'
  AND NOT EXISTS (
      SELECT 1 FROM usuarios_roles ur WHERE ur.usuario_id = u.id AND ur.rol_id = r.id AND ur.empresa_id = e.id
  );

INSERT INTO usuarios_roles (usuario_id, rol_id, empresa_id, sucursal_id, unidad_operativa_id, alcance_global, activo)
SELECT u.id, r.id, e.id, s.id, uo.id, FALSE, TRUE
FROM usuarios u
JOIN roles r ON r.codigo = 'SUPERVISOR_CAMPO'
JOIN empresas e ON e.clave = 'NFA'
JOIN sucursales s ON s.empresa_id = e.id AND s.es_matriz = TRUE
JOIN unidades_operativas uo ON uo.empresa_id = e.id AND uo.clave = 'NFA-UO-FRAMB'
WHERE u.username = 'sup.framb'
  AND NOT EXISTS (
      SELECT 1 FROM usuarios_roles ur WHERE ur.usuario_id = u.id AND ur.rol_id = r.id AND ur.unidad_operativa_id = uo.id
  );

INSERT INTO usuarios_roles (usuario_id, rol_id, empresa_id, sucursal_id, unidad_operativa_id, alcance_global, activo)
SELECT u.id, r.id, e.id, s.id, uo.id, FALSE, TRUE
FROM usuarios u
JOIN roles r ON r.codigo = 'SUPERVISOR_CAMPO'
JOIN empresas e ON e.clave = 'BIO'
JOIN sucursales s ON s.empresa_id = e.id AND s.es_matriz = TRUE
JOIN unidades_operativas uo ON uo.empresa_id = e.id AND uo.clave = 'BIO-UO-ARAND'
WHERE u.username = 'sup.bio'
  AND NOT EXISTS (
      SELECT 1 FROM usuarios_roles ur WHERE ur.usuario_id = u.id AND ur.rol_id = r.id AND ur.unidad_operativa_id = uo.id
  );
