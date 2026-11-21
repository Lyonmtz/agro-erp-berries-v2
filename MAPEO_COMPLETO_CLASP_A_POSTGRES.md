# MAPEO COMPLETO: SEAH LEGADO (`/mnt/c/clasp_project`) + `rrhh-automation-system` + `campo` → AGRO-ERP BERRIES V2 (`PostgreSQL + FastAPI + Frontend Modular`)

> **Fecha de análisis inicial:** 2026-11-20 | **Actualización de cruce multi-repositorio:** 2026-11-20  
> **Repositorio de trabajo:** `~/agro-erp-berries-v2` (clonado limpiamente desde `~/agro-erp-berries`, commit base `8adbf68`, rama `main`, sin remoto `origin` — listo para conectar a GitHub).  
> **Fuentes auditadas (4 repositorios / fuentes):**
> 1. `~/agro-erp-berries-v2` — 17 archivos (Docker, 4 scripts SQL, backend FastAPI, 2 servicios Python, 1 SPA HTML).
> 2. `/mnt/c/clasp_project` — 2 archivos backend JS (`SEAH_Backend.js` de 16,765 líneas / 1.1 MB y `SEAH_Migraciones.js` de 121 líneas; 0 `.gs` locales porque `clasp` traduce `.gs → .js`), **57 archivos `.html`** (37 rutas activas en `PAGINAS_SISTEMA` + 20 copias legacy/duplicadas/públicas) y **22 archivos `.md`** de arquitectura, bitácora, handoff y decisiones confirmadas del Product Owner.
> 3. `~/ref_rrhh_automation` (`https://github.com/Lyonmtz/rrhh-automation-system`) — 264 archivos en `main` (backend Node/TypeScript/Express, frontend React 19/Vite 8/TS/Tailwind, **22 migraciones PostgreSQL `sql/001`..`022`**, Docker MySQL 5.7.44 solo lectura para análisis de **Merqry**, documentación de arquitectura/costeo/RH-documentos/nomenclatura-QR/seguridad) + ramas remotas `origin/campo/document-preparation-v13-20261108` (PR3, 70 archivos) y `origin/docs/aprendizaje-proyectos-20261020`.
> 4. `~/ref_campo` (`https://github.com/Lyonmtz/campo`) — gobernanza arquitectónica en `main` (`README.md`, `ARCHITECTURE.md`, `SOURCES.md`) + rama `origin/respaldo/handoff-campo-20261110` (`HANDOFF_CAMPO_INTEGRAL_2026-11-10.md`) + rama `origin/respaldo/captura-trasplante-20261110` (150+ archivos del laboratorio V2 de programación de llegadas, recepción por camión/bin, captura de trasplante multi-camión, cierre persona-día y revisión de conflictos/fencing).
>
> **Nota de estandarización de nombre (`Merqry`):** En `/mnt/c/clasp_project` aparece escrito como `Merqury` y en otros documentos como `Mercury` o `MerQry`. Según la norma explícita de `rrhh-automation-system`, el nombre oficial del ERP central es **`Merqry`**; en secciones previas de mapeo legado se conserva `Merqury` solo cuando cita identificadores existentes en `clasp_project`.

---

## 1. Estado del Repositorio Clonado (`~/agro-erp-berries-v2`)

El directorio original `~/agro-erp-berries` no tenía repositorio Git inicializado. Se ejecutó sin alterar ninguno de sus archivos fuente:
1. Inicialización en `~/agro-erp-berries` (`git init -b main`, exclusión local de `__pycache__/`, `*.pyc`, `.env` vía `.git/info/exclude`, commit base `8adbf68`: *"Commit base inicial de agro-erp-berries"* con los 17 archivos originales).
2. Clonado completo a `~/agro-erp-berries-v2`.
3. Eliminación del remoto local `origin` en `~/agro-erp-berries-v2` para dejarlo listo para conectar a un nuevo repositorio en GitHub:

```bash
cd ~/agro-erp-berries-v2
git remote add origin https://github.com/<TU_USUARIO>/<TU_REPO_V2>.git
git add MAPEO_COMPLETO_CLASP_A_POSTGRES.md
git commit -m "docs: agregar mapeo completo de migracion CLASP a PostgreSQL/FastAPI"
git push -u origin main
```

---

## 2. Auditoría de lo que YA Existe y Funciona en `~/agro-erp-berries-v2`

### 2.1 Infraestructura (`docker-compose.yml`, `backend/Dockerfile`, `backend/requirements.txt`)
- **Base de datos:** `postgres:16-alpine` (puerto host `5433 -> 5432`, DB `agro_berries_erp`, TZ `America/Mexico_City`, inicialización desde `./database:/docker-entrypoint-initdb.d`).
- **Backend:** `python:3.12-slim` con FastAPI `0.115.0`, Uvicorn `0.30.6`, SQLAlchemy Async `2.0.35`, `asyncpg 0.29.0`, Pydantic `2.9.2`, `python-jose`, `passlib[bcrypt]`, `qrcode[pil]`, `openpyxl`.
- **Conexión DB (`backend/app/core/database.py`):** Engine asyncpg con pool (`pool_size=20, max_overflow=10`) y dependencia `get_db()`.

### 2.2 Esquemas SQL Existentes y Hallazgos Críticos (Defectos a Corregir en Fase 0)

| Archivo SQL | Contenido real encontrado | Estado | Hallazgos críticos / bloqueantes |
|---|---|---|---|
| `database/01_schema_core_rh.sql` (327 líneas) | Define **18 tablas** (`departamentos`, `tabulador_niveles`, `puestos`, `baterias_evaluacion`, `puesto_baterias`, `candidatos`, `resultados_evaluaciones`, `empleados`, `acuses_digitales`, `cultivos`, `ranchos`, `lotes_produccion`, `catalogo_labores`, `reglas_pago_tarifas`, `jornadas_diarias`, `registros_labores_culturales`, `registros_cosecha`, `prenomina_diaria`), **1 vista** (`vw_kpi_rendimiento_trabajador`) y seeds de `cultivos`, `departamentos`, `tabulador_niveles`, `catalogo_labores`, `reglas_pago_tarifas`. | ⚠️ Casi funcional | **Línea 327 contiene basura de shell:** `echo "✅ Scripts SQL guardados correctamente"`. En una creación limpia de volumen PostgreSQL hará fallar la ejecución del script. |
| `database/02_schema_campo_pagos.sql` (324 líneas) | **CORRUPTO:** Contiene código Python concatenado (`database.py + psicometria_service.py + pagos_service.py + main.py + docker compose up -d --build`). | ❌ Roto | No contiene SQL. Sus tablas ya estaban dentro de `01_schema_core_rh.sql`. Al correr `docker-entrypoint-initdb.d`, PostgreSQL abortará el init. |
| `database/03_seed_data.sql` (324 líneas) | **CORRUPTO:** Copia idéntica del mismo código Python concatenado que `02_schema_campo_pagos.sql`. | ❌ Roto | Faltan los `INSERT` seed de `ranchos`, `lotes_produccion`, `puestos`, `baterias_evaluacion`, `puesto_baterias` y `empleados` iniciales (`EMP-1001`, `EMP-2001`) que `frontend/index.html` asume existentes. |
| `database/04_schema_tec_inv_log.sql` (44 líneas) | Define **2 tablas** (`insumos_agricolas`, `aplicaciones_fitosanitarias`), función/trigger `fn_bloquear_lote_por_aplicacion` / `trg_bloqueo_fitosanitario`, y vista `vw_direccion_rentabilidad_cultivo`. | ⚠️ Roto por sintaxis y lógica | 1) **Línea 29:** `(v_dias \vert{}\vert{} ' days')::INTERVAL` tiene escape LaTeX `\vert{}\vert{}` en lugar del operador SQL `||`.<br>2) `vw_direccion_rentabilidad_cultivo` suma **toda** `prenomina_diaria` en cada cultivo sin filtrar por `cultivo_id`, duplicando el gasto de mano de obra en los 3 cultivos. |

### 2.3 Backend FastAPI Actual (`backend/app/main.py` y `backend/app/services/`)

Actualmente existen **11 endpoints** implementados con SQL crudo (`sqlalchemy.text`) directamente en `main.py` (las carpetas `backend/app/models/`, `backend/app/schemas/` y `backend/app/api/v1/` están vacías):

| Método y Ruta | Función | Qué hace hoy | Brechas / Bugs detectados |
|---|---|---|---|
| `GET /api/v1/health` | `health_check` | Cuenta filas de `cultivos`. | OK. |
| `GET /api/v1/catalogos/operacion` | `catalogos_operacion` | Lista `lotes_produccion` y `empleados` activos. | Sin filtro por empresa (`NFA`/`BIO`), módulo ni rol. |
| `GET /api/v1/public/vacantes` | `listar_vacantes` | Lista `puestos` con `publicar_en_landing = TRUE`. | No filtra `vacantes_abiertas > 0` ni distingue vacante formal con requisición/evidencia. |
| `GET /api/v1/public/puesto/{puesto_id}/bateria` | `obtener_bateria_puesto` | Devuelve 1 batería asociada al puesto (`LIMIT 1`). | En SEAH un puesto exige múltiples evaluaciones (`PSICOMETRICA`, `CONFIANZA`, `ENTREVISTA`, `PRUEBA_CAMPO` / `REQUISITO_PUESTO`). |
| `POST /api/v1/public/postular` | `postular` | Registra candidato en `candidatos` y busca reingreso por CURP en `vw_kpi_rendimiento_trabajador`. | Solo busca por CURP en empleados actuales (no teléfono/nombre ni ranking histórico de 301 cosechadores); no guarda logística (hospedaje/transporte/grupo) ni talla/experiencia. |
| `POST /api/v1/public/evaluar` | `evaluar_candidato` | Ejecuta `MotorPsicometrico` (`ZAVIC_OP`, `CLEAVER_SUP`, genérico) y guarda en `resultados_evaluaciones`. | No valida `bat is None` (500 si no existe `bateria_id`); no pondera evaluación+experiencia+capacidad (60/25/15). |
| `GET /api/v1/rh/candidatos` | `listar_candidatos_rh` | Lista todos los candidatos con título de puesto. | Sin filtros de etapa/empresa/vacante ni paginación; sin autenticación. |
| `POST /api/v1/rh/contratar` | `contratar_candidato` | Inserta en `empleados` y marca `candidatos.estatus = 'CONTRATADO'`. | 1) No valida `cand is None` ni que haya aprobado evaluaciones obligatorias (viola **D8**).<br>2) Recibe `firma_acuse_base64` pero **nunca inserta en `acuses_digitales`**.<br>3) Marca `induccion_inocuidad_completada = TRUE` automáticamente sin registro real.<br>4) No soporta reingreso conservando identidad (viola **D6**). |
| `GET /api/v1/rh/prenomina` | `consultar_prenomina` | Consulta `prenomina_diaria` ordenada por fecha desc. | Es solo diaria; en SEAH la prenómina es **conciliación semanal** (L–S + Domingo escalonado + mínimo semanal garantizado $2,350 + comida/hospedaje informativos + cierre nombrado + auditoría). |
| `POST /api/v1/campo/cosecha` | `registrar_cosecha_tablet` | Valida empleado activo + inducción BPA + lote `LIBRE_CORTE`, crea `jornadas_diarias`, inserta `registros_cosecha`, recalcula con `MotorPagosCampo` y hace upsert en `prenomina_diaria`. | 1) **Bug lógico L123:** guarda `calc["total_cajas"]` (exp+nac+rez) en la columna `total_cajas_exportacion`.<br>2) No valida autorización operativa de destajo (`SOLO_COMPUTO` vs `EN_REVISION`), ni cruce contra asignación diaria, ni NIP del cosechador, ni modo offline/idempotencia.<br>3) No soporta domingo con tarifa escalonada ni múltiples presentaciones/clamshells. |
| `GET /api/v1/direccion/dashboard` | `dashboard_direccion` | Devuelve `vw_direccion_rentabilidad_cultivo` y `vw_kpi_rendimiento_trabajador`. | Sin separación por empresa (`NFA` vs `BIO`), sin riesgos abiertos (`desviaciones_riesgo`), sin permisos pendientes, sin confidencialidad de bajas proyectadas (**D16**) ni RBAC. |

**Servicios Python existentes:**
- `backend/app/services/psicometria_service.py` (`MotorPsicometrico`): soporta `ZAVIC_OP`, `CLEAVER_SUP` y evaluación por porcentaje genérico (`>=75%`). Buena base reutilizable para ampliar con la política de evaluaciones de SEAH.
- `backend/app/services/pagos_service.py` (`MotorPagosCampo`): calcula `JORNAL_PURO`, `DESTAJO_PURO`, `MIXTO_GARANTIA` y bono por rezaga diaria. Debe extenderse con las reglas semanales reales de SEAH (umbral semanal, mínimo garantizado semanal, domingo escalonado, puestos sueldo fijo vs destajo, autorización operativa previa).

### 2.4 Frontend Actual (`frontend/index.html`)
- SPA en un solo archivo (`218 líneas`, Tailwind CDN + Alpine.js 3 CDN) con `API = 'http://localhost:8000/api/v1'`.
- 4 vistas básicas: **Portal Empleo**, **Tablet Campo**, **RH y Merqry**, **Dirección BI**.
- Sin autenticación/login, sin control de roles, sin soporte offline (`IndexedDB`/Service Worker), sin separación Reclutamiento vs Administración de Personal, y genera `numero_empleado` aleatorio (`EMP-3000..9000`) en lugar de exigir el número real de Merqury/checador.

---

## 3. Inventario Maestro del Sistema Legado (`/mnt/c/clasp_project`)

### 3.1 Decisiones Funcionales Confirmadas del Product Owner (Invariantes para v2)
Extraídas de `SEAH_DECISIONES_FUNCIONALES_CONFIRMADAS.md` y `PRESERVED_PRODUCT_DECISIONS.md` (no modificar sin autorización de Dirección):

| ID | Decisión Confirmada | Impacto directo en PostgreSQL / FastAPI / Frontend |
|---|---|---|
| **D1** | **Reclutamiento y Administración de Personal son etapas/pantallas separadas.** | Dos routers/servicios y dos módulos UI distintos (no mezclar en una sola vista como ocurría en `personal_seah_v2.html`). |
| **D2** | **Reclutamiento termina en firma de contrato y entrega formal de expediente.** | Estado formal de traspaso (`TRASPASADO_A_ADMIN`) auditado y validado antes de activar en Administración de Personal. |
| **D3** | **Administración de Personal controla todo el ciclo laboral; Checador es externo (Merqury).** | **NO construir checador propio**; diseñar capa de integración/conciliación con Merqury (`merqury_employee_id`, imports/exports). |
| **D4** | **Comparten Ficha Maestra de Persona, pero nunca las mismas acciones/pantallas.** | Tabla única `personas` (identidad) separada de `postulaciones_reclutamiento` y `relaciones_laborales` (altas). |
| **D5** | **Una persona puede editarse en todo su ciclo con permisos y auditoría.** | Lista blanca de campos editables por rol + tabla `auditoria_universal` (antes/después) + notificación a Dirección en cambios sensibles. |
| **D6** | **Reingreso conserva identidad e historial y crea una NUEVA alta laboral.** | `personas` (1 registro único por CURP/identidad) → `1:N` `relaciones_laborales` (múltiples contratos/temporadas históricos). |
| **D7** | **Solo roles autorizados pueden dar baja o reactivar.** | Enforcement real en servidor (FastAPI `Depends(require_roles(...))`), no solo ocultar botones en UI. |
| **D8** | **No se puede contratar sin evaluaciones obligatorias y aptitud.** | Gate duro en `POST /api/v1/reclutamiento/{id}/contratar` verificando política por puesto y dictamen `APTO`. |
| **D9** | **`PADRON_MAESTRO` fue espejo operativo de transición (445 cols).** | En v2 se sustituye por el modelo normalizado (`personas` + `relaciones_laborales` + vista materializada/SQL de compatibilidad si se requiere exportar padrón). |
| **D10–D11** | **`personas` = identidad; `nomina_registro` = relación laboral y nómina.** | Mapeo directo a `personas` + `relaciones_laborales` + `historial_salarios`. |
| **D12–D13** | **Tablet consume activos y alimenta Prenómina; Prenómina es conciliación.** | Prenómina semanal concilia: Tablet (cajas pagables) + Reglas de pago + Rol/asistencia + Incrementos + Comida/Hospedaje (informativos) + Merqury. |
| **D14** | **Priorizar 3 flujos núcleo (Contratación, Planeación, Producción) antes de e-learning/DC3.** | Orden de fases del roadmap. |
| **D15** | **Formulario de cosecha separado del formulario de perfiles generales.** | Dos flujos públicos bajo `/portal-empleo` (`/cosecha` vs `/general`). |
| **D16** | **Alerta de bajas proyectadas es confidencial (solo `DIRECCION`).** | Endpoint y tarjeta exclusiva con `require_roles(["DIRECCION"])`. |
| **D17** | **Fresa pertenece a `NFA`, no a `BIO`.** | Catálogo real: `NFA` = Frambuesa (7.5 ha → 10.2 ha en 2027) + Fresa (2.6 ha); `BIO` = Tomate (10.8 ha en 2026) → Arándano (8.1 ha en 2027). |
| **D18** | **Prorrateo de costos de 3 capas (BIO por cultivo / NFA 75-25% por superficie / Admin grupo BIO-NFA).** | Guardar esquema de superficies vigentes por periodo y catálogo de cuentas; **NO activar cálculos automáticos de prorrateo hasta validación explícita de Dirección/Administración/Operación.** |

### 3.2 Mapa de los 57 Archivos HTML de `/mnt/c/clasp_project` (Activos vs Legacy)
- **37 rutas activas** en `PAGINAS_SISTEMA`: `menu_SEAH_v1` (`menu`), `personal_seah_v2` (`admin`), `tablet_campo` (`tablet`), `TabletGrower` (`growertablet`), `acuse_rrhh` (`acuse`), `control_comida` (`comida`), `prenomina` (`prenomina`), `organigramas` (`organigrama`), `configuracion_semanal` (`config`), `planeacion_grower` (`grower`), `solicitud_empleo` (`solicitud`), `programa_comercial` (`comercial`), `postcosecha` (`postcosecha`), `analisis_mo` (`analisismo`), `centro_control` (`centrocontrol`), `reporte_avance` (`reportes`), `consulta_cosechador` (`misresultados`), `cuadro_honor` (`cuadrohonor`), `rol_descansos` (`roldescansos`), `rol_semanal_personal` (`rolsemanal`), `administracion_cosecha` (`administracioncosecha`), `configuracion_comercial` (`configcomercial`), `costos_contables` (`costoscontables`), `configuracion_usuarios` (`configusuarios`), `direccion_inicio` (`direccioninicio`), `historial_grower` (`historialgrower`), `centro_ayuda` (`ayuda`), `auditoria_dinero` (`auditoria`), `matriz_permisos` (`matrizpermisos`), `dashboard_contratacion` (`contratacion`), más 6 páginas de capacitación (`capacitacion_tablet`, `capacitacion_tabletgrower`, `capacitacion_rrhh`, `capacitacion_comercial`, `capacitacion_grower`, `capacitacion_direccion`).
- **5 pantallas públicas/auxiliares fuera de `PAGINAS_SISTEMA`:** `trabaja_con_nosotros.html`, `solicitud_empleo_general.html`, `vacantes_evaluacion.html`, `configuracion_documentos.html`, `diag_padron.html`.
- **15 copias legacy/versionadas (NO migrar por separado; consolidar en la vista destino):** `menu.html`, `administracion_personal.html` (*marcado "NO EDITAR"*), `administracion_personal_NFA_BIO_v6.html`, `acuse_digital_RRHH_SEAH_v1.html`, `analisis_mo_SEAH_v2.html`, `centro_control_SEAH_v1.html`, `configuracion_semanal_SEAH_v1.html`, `control_comida_diario_SEAH_v1.html`, `organigramas_3_NFA_BIO_v1.html`, `planeacion_grower_SEAH_v1.html`, `postcosecha_SEAH_v1.html`, `prenomina_SEAH_v1.html`, `programa_comercial_SEAH_v1.html`, `reporte_avance_SEAH_v1.html`, `solicitud_empleo_SEAH_v2.html`, `tablet_campo_SEAH_v4.html`.

---

## 4. Mapeo Detallado CLASP → PostgreSQL, FastAPI y Frontend

---

### 4.1 Dominio 1: Multi-Empresa (`NFA` / `BIO`), Calendario SEAH/Mastronardi, Estructura Física y Contabilidad

#### Reglas de Negocio Legadas (`SEAH_Backend.js`)
1. **Empresas y Razones Sociales (`CONFIG_EMPRESAS`):** `NFA` (Natural) y `BIO`, cada una con `razon_social`, `representante_legal`, `acreditacion_personalidad`, `domicilio_fiscal`, `rfc_empresa`, `objeto_social`, `municipio` (requerido por Art. 501 LFT en Anexo de Beneficiarios).
2. **Cultivos y Superficies por Periodo (`CULTIVOS_CATALOGO`, `superficie_cultivo_historico`, D17):**
   - `2026`: BIO = Tomate `10.8 ha`; NFA = Frambuesa `7.5 ha` + Fresa `2.6 ha`.
   - `2027`: BIO = Arándano `8.1 ha` (migración desde Tomate); NFA = Frambuesa `10.2 ha` (`7.5 + 2.7 nuevas`) + Fresa `2.6 ha`.
   - Mercado: Fresa es 100% `NACIONAL`; Frambuesa y Arándano son `EXPORT_Y_NACIONAL`.
3. **Derivación de empresa por módulo (`empresaDeModulo_`):** Módulos con prefijo `B` (`B1`, `B2`, `B3`) = `BIO`; módulos numéricos `1..11` = `NFA` (nota pendiente: confirmar nomenclatura de módulos `21/22` de fresa reportados en ruta Gris).
4. **Calendario Semanal SEAH vs Mastronardi (`L22-L195`):**
   - `SEMANA_OFFSET_MASTRONARDI = 1` → `semana_mastronardi = semana_seah - 1`.
   - Ciclo Frambuesa Primocaña 2026: semanas `22..43`, inicio lunes `2026-05-25`.
   - Etapas: `INICIO` (22–26), `MEDIA` (27–31), `PICO` (32–37), `CIERRE` (38–43).
5. **Contabilidad y Prorrateo 3 Capas (`catalogo_cuentas_contables`, `captura_costos_contables`, D18):**
   - Categorías: `INGRESOS`, `DESCUENTOS`, `COSTO_PRODUCCION` (MO IMSS, GIP, GIE), `GASTO_VENTA`, `GASTO_ADMINISTRACION` (`prorratea_75_25`).
   - Captura mensual/por periodo desde auxiliares de Merqury, enlazada a `auditoria_dinero`.
   - Regla explícita **D18:** el motor de prorrateo (capa 1 BIO entre cultivos, capa 2 NFA Frambuesa/Fresa 75/25% según superficie vigente del periodo, capa 3 admin grupo BIO/NFA) queda **desactivado (feature flag)** hasta validación formal.

#### Mapeo a PostgreSQL (Nuevas tablas / Alteraciones)
- **`empresas` (NUEVA):** `id`, `clave` (`NFA`/`BIO` UNIQUE), `razon_social`, `rfc_empresa`, `representante_legal`, `acreditacion_personalidad`, `domicilio_fiscal`, `municipio`, `objeto_social`, `activo`, `actualizado_en`.
- **Alterar `cultivos` y `ranchos` / `lotes_produccion`:** agregar `empresa_id FK → empresas(id)`, `mercado` (`EXPORT_Y_NACIONAL` | `NACIONAL`), `codigo_modulo` (`1..11`, `B1..B3`), `fecha_trasplante` (por módulo, porque cada módulo arranca su curva en fecha propia).
- **`superficie_cultivo_periodo` (NUEVA):** `id`, `periodo` (ej. `'2026'`), `empresa_id FK`, `cultivo_id FK`, `superficie_ha`, `superficie_nueva_ha`, `en_produccion`, `notas`, `creado_en`, `UNIQUE(periodo, empresa_id, cultivo_id)`.
- **`calendario_ciclos_semanas` (NUEVA):** `id`, `ciclo_codigo`, `anio`, `semana_seah`, `semana_mastronardi`, `fecha_inicio`, `fecha_fin`, `etapa` (`INICIO`|`MEDIA`|`PICO`|`CIERRE`), `cultivo_id FK`.
- **`catalogo_cuentas_contables` (NUEVA):** `cuenta_codigo PK`, `descripcion`, `categoria`, `subgrupo` (`MO_IMSS`|`GIP`|`GIE`|`GV`|`GA`), `consideraciones`, `prorratea_75_25 BOOLEAN`, `activo`.
- **`captura_costos_contables` (NUEVA):** `id UUID`, `periodo` (`YYYY-MM` o semana), `cuenta_codigo FK`, `empresa_id FK`, `cultivo_id FK NULL`, `importe NUMERIC(14,2)`, `notas`, `capturado_por UUID`, `creado_en`, `actualizado_en`.

#### Servicios/Endpoints FastAPI y Frontend
- **Router `core_router.py` (`/api/v1/core/`):** CRUD `empresas`, `superficies`, `calendario/semana-actual`, `calendario/equivalencias`, `modulos`.
- **Router `contabilidad_router.py` (`/api/v1/contabilidad/`):** `GET/POST /cuentas`, `GET/POST /costos`, `GET /costos/resumen`.
- **Frontend:** Vistas `Configuración Empresas y Cultivos`, `Costos Contables` (reemplaza `costos_contables.html`) y selector global de `Empresa (NFA/BIO) + Cultivo + Semana SEAH`.

---

### 4.2 Dominio 2: Identidad Única, Reclutamiento, Administración de Personal, Expediente, Contratos, Acuses, Bajas, Finiquitos y Préstamos

#### Reglas de Negocio Legadas (`SEAH_Backend.js` + `SEAH_FUNCIONALIDAD_RH_CONSTRUIDA.md`)
1. **Separación estricta Reclutamiento vs Administración de Personal (D1, D2, D4):**
   - **Vacantes (`vacantes_requisicion`):** requieren evidencia obligatoria (`organigrama_ref` o `plantilla_autorizada_ref`) cuando `motivo != 'TEMPORADA'`, más flujo de autorización (`autorizarVacante`) y cobertura (`cantidad_solicitada` vs `cantidad_cubierta`).
   - **Portales públicos separados (D15):** `trabaja_con_nosotros` enruta a formulario de **Cosecha** (guarda detalle completo en `solicitud_cosecha_detalle` + logística hospedaje/transporte/grupo + ficha física talla/altura/peso/experiencia/capacidad cajas) vs formulario **General** para el resto de puestos.
   - **Pipeline Reclutamiento (`reclutamiento`):** etapas fijas `PROSPECTO → CONTACTADO → DOCUMENTOS_PENDIENTES → LISTO_PARA_CONTRATAR → CONTRATADO` (o `DESCARTADO`), con motivo obligatorio al retroceder y bitácora de contactos (`reclutamiento_bitacora`).
   - **Detección de reingreso y duplicados (`buscarHistorialPersona_`, `detectarDuplicadoPersona_`):** busca por **CURP, teléfono normalizado y nombre normalizado** contra `personas`, `reclutamiento` y `ranking_cosechadores_historico` (301 históricos), trayendo estrellas, clasificación y banderas críticas.
   - **Política de Evaluaciones por Puesto (`POLITICA_EVALUACION_POR_PUESTO`, D8):**
     - `COSECHADOR` y `PESADOR`: `PSICOMETRICA`, `CONFIANZA`, `ENTREVISTA`, `PRUEBA_CAMPO` (hasta 1 semana).
     - `SUPERVISOR`, `JEFE_MO`, `ADMINISTRATIVO`, `MANTENIMIENTO`, `CALIDAD`, `ALMACEN`, `COMERCIAL`, `DIRECCION`: `PSICOMETRICA`, `CONFIANZA`, `ENTREVISTA`, `REQUISITO_PUESTO`.
     - `STAFF` / `DEFAULT`: `PSICOMETRICA`, `CONFIANZA`, `ENTREVISTA`.
     - **Puntuación ponderada (`PESOS_PUNTUACION_PROSPECTO`):** `60%` promedio evaluaciones + `25%` años experiencia (tope 5 años = 100) + `15%` capacidad estimada cajas/día (tope 40 cajas = 100).
   - **Contratación y Traspaso Formal (D2, D6, D8):** exige (1) todas las evaluaciones aprobadas (`apto = TRUE`), (2) `numero_empleado` proveniente de Merqury/checador, (3) genera/reutiliza `personas` (conservando historial si es reingreso) y crea una **nueva** relación laboral en `relaciones_laborales` (`nomina_registro`), cerrando la postulación como `CONTRATADO` con referencia a `persona_id`.
2. **Expediente, Documentos Bloqueantes, Contratos y Acuse Digital:**
   - **Documentos bloqueantes (`DOCS_BLOQUEANTES`):** `INE`, `CURP`, `NSS`, `RFC`, `ACTA_NACIMIENTO` (+ `COMPROBANTE_DOMICILIO`, `CONTRATO`, `CUENTA_BANCARIA` para plan de bajas).
   - **Onboarding (`onboarding_checklist`):** formatos `F05` Ficha alta, `F06` Condiciones laborales, `F07` Acuse reglamento, `F08` Política pago, `F09` Acuse comida/hospedaje, `F10` Beneficiarios, `F12` Asignación puesto + inducciones (`induccion`, `bpa`, `seguridad`) → gate `listo_para_operar`.
   - **Contratos y Beneficiarios (Art. 501 LFT):** plantillas por puesto (`CONFIG_PLANTILLAS_CONTRATO`), flujo obligatorio `BORRADOR → VALIDADO → FIRMADO` (no se puede firmar un borrador sin validación previa de RH), soporte de firma en papel (PDF/foto) o digital (PNG), y tabla de beneficiarios con suma de porcentajes = 100%.
   - **Acuse Digital RRHH (`ACUSES_RRHH` + `ACUSES_RRHH_CASOS`):** checklist de 10 puntos RH, casos seleccionados (`A, B, F...` según perfil/modalidad/villas/comida), firma trabajador + firma quien explicó, validación RH (`GENERADO → FIRMADO → DIGITALIZADO → VALIDADO | RECHAZADO`) que actualiza automáticamente el checklist de onboarding.
   - **Edición controlada y borrado suave (D5, D7):** solo campos permitidos por rol, registro en auditoría + notificación por correo a Gerencia cuando edita un usuario distinto a Dirección; eliminación lógica (`eliminado_en`, `eliminado_por`, `motivo_eliminacion`) reversible desde papelera exclusiva de `DIRECCION`.
3. **Incrementos Salariales (`incrementos_salariales`):**
   - Flujo `SOLICITADO → AUTORIZADO → APLICADO` (o `RECHAZADO`). Al aplicar, actualiza `relaciones_laborales.salario_*` y dispara automáticamente `auditoria_dinero`.
4. **Bajas, Causales Legales LFT, Finiquitos 2026 y Cuadro de Baja:**
   - **Causales LFT (`CAUSALES_LEGALES_BAJA_`):** `RENUNCIA`, `DESPIDO_JUSTIFICADO` (Art. 47), `ABANDONO` (Art. 47 fracc. X, >3 faltas en 30 días), `DESPIDO_INJUSTIFICADO`, `RESCISION_POR_TRABAJADOR` (Art. 51/52 — misma indemnización que despido injustificado), `CONVENIO` (Art. 53 fracc. I), `FALLECIMIENTO`, `FIN_TEMPORADA`, `INCAPACIDAD_INHABILIDAD`.
   - **Motor de Finiquito 2026 (`PARAMS_FINIQUITO_2026`):**
     - `UMA_DIARIA = 117.66`, `SMG_GENERAL = 315.04`, `SMG_JORNALERO_AGRICOLA = 356.16`, `DIAS_AGUINALDO = 15`, `PRIMA_VACACIONAL = 25%`, `PRIMA_ANTIGUEDAD = 12 días/año` (topada a `2 × SMG_GENERAL`, NO UMA — criterio SCJN; en renuncia solo si antigüedad ≥ 15 años).
     - Tabla de vacaciones LFT Art. 76 (reforma 2022: 12, 14, 16, 18, 20, 22... hasta 32 días) evaluada al año en curso (`floor(antigüedad) + 1`).
     - Indemnización `90 días + 20 días/año` solo para `DESPIDO_INJUSTIFICADO` y `RESCISION_POR_TRABAJADOR`.
     - **ISR semanal SAT 2026 (11 tramos `TABLA_ISPT_SEMANAL_2026`):** aplica solo a modalidad `IMSS`; primeros `30 UMAs` de aguinaldo exentos (Art. 93 LISR).
     - Soporta `monto_negociado`, referencias `+15/+30/+45 días`, y presupuesto grupal (`calcularFiniquitoGrupal`, ej. 21 bajas BIO proyectadas).
   - **Seguimiento Legal y Cuadro de Baja (`bajas_seguimiento`):** controla estatus conflicto (`SIN_CONFLICTO`, `CONCILIACION_INTERNA`, `EN_CENTRO_CONCILIACION`, `CONSTANCIA_NO_CONCILIACION`, `EN_DEMANDA_TRIBUNAL`, `CERRADO`), fecha límite de conciliación (2 meses), y cruza finiquito + conflicto + documentos pendientes + préstamos con saldo para dictaminar `LISTO_PARA_CERRAR` vs `CON_PENDIENTES`.
5. **Préstamos de Personal (FO-CH-PP-NN-00 / BIO-SG-F-CPAP-38) y Créditos Externos:**
   - **Préstamo Empresa (`PRESTAMO_EMPRESA`):** elegibilidad exige `antigüedad ≥ 6 meses`, `sin otro préstamo vigente`, `desempeño excelente`, `presupuesto disponible` y validación de tope contra el cálculo de finiquito.
   - **Scoring oficial 80 puntos (`CALIFICACION_PRESTAMO_OPCIONES_`):** 8 criterios × 10 pts (`motivo`, `antigüedad`, `desempeño`, `historial préstamos`, `presupuesto`, `finiquito cubre importe`, `capacidad pago 5-10% mensual`, `puntualidad/asistencia`). Bandas: `>70 SATISFACTORIO`, `60-70 REVISABLE`, `<60 NO_ACEPTABLE`. Autorización exclusiva de Gerente General + folio de pagaré.
   - **Créditos Externos (`INFONAVIT`, `FONACOT`, `PENSION_ALIMENTICIA`):** bandera obligatoria `declarado_por_trabajador` y reporte `alerta_riesgo_credito_baja_temprana` (por defecto ≤ 30 días laborados con saldo activo).

#### Mapeo a PostgreSQL
- **Refactorizar `empleados` → separar identidad vs alta laboral (D4, D6, D10, D11):**
  - **`personas` (NUEVA — reemplaza parte identidad de `empleados`):** `id UUID PK`, `curp VARCHAR(18) UNIQUE NULL`, `rfc VARCHAR(13) UNIQUE NULL`, `nss VARCHAR(11) UNIQUE NULL`, `nombre`, `apellido_paterno`, `apellido_materno`, `fecha_nacimiento`, `sexo`, `telefono`, `telefono_emergencia`, `contacto_emergencia`, `domicilio`, `municipio`, `estado`, `talla`, `altura_cm`, `peso_kg`, `codigo_qr_hash UNIQUE`, `estatus_global` (`PROSPECTO`|`POSTULANTE`|`RECLUTADO`|`EN_PROCESO`|`CONTRATADO`|`ACTIVO`|`BAJA_PROYECTADA`|`CARTERA`|`DESCARTADO`|`BAJA`), `eliminado_en TIMESTAMPTZ`, `eliminado_por UUID`, `motivo_eliminacion`, `creado_en`, `actualizado_en`.
  - **`relaciones_laborales` (NUEVA — equivale a `nomina_registro`, permite N reingresos):** `id UUID PK`, `persona_id FK → personas(id)`, `empresa_id FK → empresas(id)`, `puesto_id FK → puestos(id)`, `numero_empleado VARCHAR(30) NOT NULL`, `clave_empleado`, `merqury_employee_id`, `checador_id`, `area`, `modulo_asignado`, `periodicidad`, `categoria_prenomina` (`FIJO`|`DESTAJO`), `esquema_pago`, `forma_pago`, `tipo_relacion_laboral`, `imss_estatus` (`IMSS`|`ESPECIAL`), `salario_diario`, `salario_diario_integrado`, `salario_semanal_actual`, `fecha_ingreso`, `fecha_baja`, `baja_proyectada BOOLEAN DEFAULT FALSE`, `fecha_baja_proyectada DATE`, `estatus_merqury`, `fecha_baja_merqury`, `tiposueldo_merqury`, `induccion_inocuidad_completada`, `fecha_induccion_inocuidad`, `estatus_conciliacion` (`ACTIVO_CONFIRMADO`|`PENDIENTE_CONCILIAR`|`BAJA`), `activa BOOLEAN`, `creado_en`. (Vista `vw_empleados_activos` mantiene compatibilidad con consultas actuales).
- **`vacantes_requisicion` (NUEVA):** columnas espejo de `VACANTES_HEADERS` con `empresa_id`, `cultivo_id`, `puesto_id`, `organigrama_ref`, `plantilla_autorizada_ref`, `cantidad_solicitada`, `cantidad_cubierta`, `estatus`, `solicitado_por`, `autorizado_por`.
- **`postulaciones_reclutamiento` (evolución de `candidatos`):** agrega `persona_id FK NULL`, `vacante_id FK`, `etapa`, `tipo_formulario` (`COSECHA`|`GENERAL`), `empresa_destino_id`, `cultivo_destino_id`, `semana_inicio`, `responsable_id`, `origen`, `reingreso_detectado`, `reingreso_ranking_json JSONB`, logística (`requiere_hospedaje`, `requiere_transporte`, `viene_en_grupo`, `personas_grupo`, `fecha_llegada_estimada`, `fecha_llegada_confirmada`), `anios_experiencia`, `ha_cosechado_antes`, `capacidad_estimada_cajas`, `detalle_solicitud_json JSONB`, `puntuacion`, `apto_evaluacion`, `traspasado_admin_en`.
- **`reclutamiento_bitacora` (NUEVA):** historial de llamadas/contactos por postulación.
- **`politica_evaluacion_puesto` (NUEVA) + ampliar `resultados_evaluaciones`:** soporta los 5 tipos (`PSICOMETRICA`, `CONFIANZA`, `ENTREVISTA`, `REQUISITO_PUESTO`, `PRUEBA_CAMPO`), `fecha_inicio`, `fecha_fin`, `evaluador_id`, `aprobado`, `vigente_hasta`.
- **`documentos_persona` (NUEVA):** `id UUID`, `persona_id FK`, `relacion_laboral_id FK NULL`, `tipo_documento`, `estatus`, `archivo_url` (local/S3/Drive), `firma_url`, `tipo_firma` (`PAPEL`|`DIGITAL`), `validado_por`, `fecha_validacion`.
- **`onboarding_checklist` (NUEVA):** checklist de documentos bloqueantes + formatos `F05..F12` + inducciones + `listo_para_operar`.
- **`plantillas_contrato` (NUEVA)** y **`beneficiarios_persona` (NUEVA, Art. 501 LFT)**.
- **Ampliar `acuses_digitales` + `acuses_digitales_casos` (NUEVA):** agregar `firma_explico_url`, `casos_ids`, `checklist_rh_completo`, `validado_por`, `estatus_documento` y detalle por caso (`A, B, F...`).
- **`incrementos_salariales` (NUEVA):** flujo `SOLICITADO → AUTORIZADO → APLICADO`.
- **`finiquitos` (NUEVA) + `parametros_legales_lft` (NUEVA, parametrizable por año: UMA, SMG, tabla vacaciones, tabla ISPT semanal) + `bajas_seguimiento` (NUEVA).**
- **`prestamos_personal` (NUEVA):** cubre `PRESTAMO_EMPRESA` (con JSONB del desglose FO-CH-PP-NN-00) y créditos externos (`INFONAVIT`, `FONACOT`, `PENSION_ALIMENTICIA`), más `prestamos_abonos` (NUEVA).

#### Servicios/Endpoints FastAPI y Frontend
- **Router `reclutamiento_router.py` (`/api/v1/reclutamiento/`):** vacantes + autorización, portal público cosecha/general, detección de reingreso multicriterio, pipeline + bitácora, evaluaciones + aptitud + ranking ponderado, dashboard de contratación, cierre/traspaso a Admin Personal.
- **Router `personal_router.py` (`/api/v1/personal/`):** Ficha Maestra de Persona, relaciones laborales y reingresos, expediente/documentos (upload), contratos + anexo beneficiarios, acuses digitales + validación RH, onboarding, incrementos salariales, bajas + finiquito individual/grupal + cuadro de baja, préstamos + calificación FO-CH-PP-NN-00 + alerta créditos baja temprana, papelera de eliminados (solo `DIRECCION`), organigramas.
- **Frontend:** Pantallas separadas **Reclutamiento y Selección** (vacantes, embudo, evaluaciones, ranking, traspaso), **Administración de Personal** (padrón conciliado, ficha maestra, expediente, contratos, incrementos, bajas/finiquitos, préstamos), **Portal Empleo Público** (selector cosecha vs general), **Acuse Digital RRHH**, **Organigramas NFA/BIO**.

---

### 4.3 Dominio 3: Integración y Conciliación con Merqury (Checador y Nómina Oficial)

#### Reglas de Negocio Legadas
1. **Merqury es la fuente de verdad externa para checador y nómina IMSS (D3):**
   - No se construye un checador biométrico dentro de SEAH.
   - Todo empleado `IMSS` existe en Merqury (`numero_empleado` / `merqury_employee_id`, prefijo histórico `MRQ-`).
   - Los trabajadores de pago en efectivo (`ESPECIAL`, prefijo histórico `ESP-`) **no existen en Merqury**; viven solo en el ERP para control interno y prenómina de efectivos.
2. **Conciliación de Padrón (`clasificarEstatusConciliacionPadron_`, `reconciliarConCrmCosechadoresLive_`):**
   - El problema real del sistema legado fue la desincronización entre `PADRON_MAESTRO` (445 cols), `personas` (bug `contacto_id != persona_id`) y Merqury (`476` activos crudos vs `71` confirmados).
   - En PostgreSQL, la identidad única (`personas`) + tabla de conciliación con Merqury eliminan permanentemente el bug del espejo.
3. **Exportación/Importación hacia Merqury:**
   - **Entrada desde Merqury:** importación periódica (Excel/CSV) de altas, bajas (`estatus_merqury`, `fecha_baja_merqury`), asistencias/checadas (`dias_trabajados`, retardos/faltas), salarios integrados (`SDI`), descuentos de créditos externos (INFONAVIT/FONACOT).
   - **Salida hacia Merqury:** layout semanal de prenómina cerrada (percepciones por destajo, bonos, faltas, incapacidades, descuentos de préstamos) con identificador `lote_exportacion_merqury`.

#### Mapeo a PostgreSQL
- **`merqury_sync_lotes` (NUEVA):** `id UUID`, `direccion` (`IMPORT_EMPLEADOS`|`IMPORT_ASISTENCIA`|`IMPORT_COSTOS`|`EXPORT_PRENOMINA`), `empresa_id FK`, `semana_seah`, `archivo_nombre`, `total_registros`, `coincidencias`, `discrepancias`, `estatus`, `ejecutado_por UUID`, `creado_en`.
- **`merqury_asistencias_import` (NUEVA):** `id UUID`, `lote_id FK`, `persona_id FK NULL`, `numero_empleado_merqury`, `fecha`, `hora_entrada`, `hora_salida`, `estatus_checador`, `minutos_retardo`, `conciliado BOOLEAN`.
- **`merqury_discrepancias` (NUEVA):** registra diferencias detectadas automáticamente (ej. activo en ERP pero baja en Merqury, empleado en Merqury sin alta en ERP, salario diferente) para resolución asistida por RH.

#### Servicios/Endpoints FastAPI y Frontend
- **Router `merqury_router.py` (`/api/v1/merqury/`):** `POST /importar-padron`, `POST /importar-asistencias` (Excel/CSV con `openpyxl`), `GET /discrepancias`, `POST /discrepancias/{id}/resolver`, `GET /exportar-prenomina/{semana}` (genera archivo `.xlsx`/`.csv` con layout Merqury y sella `lote_exportacion_merqury`).
- **Frontend:** Vista **Conciliación Merqury** (subida de archivos, semáforo de discrepancias IMSS vs Especiales, descarga de layout de prenómina).

---

### 4.4 Dominio 4: Operación de Campo, Planeación Grower (PHVA), Rol Semanal, Descansos y Autorizaciones Operativas

#### Reglas de Negocio Legadas
1. **Planeación Grower y Motor PHVA (`planes_grower_semanal`, `calcularPhvaGrower`, `desviaciones_riesgo`):**
   - En Sheets, `json_plan` superaba 50,000 caracteres y requería partirse en chunks de 45KB (`planes_grower_json_chunks`). En PostgreSQL se almacena nativamente en tablas normalizadas + `JSONB` para versiones históricas.
   - Versionado obligatorio con `causa_cambio` y `responsable` (`historial_grower.html`), nunca solo en `localStorage`.
   - **Fórmula PHVA de personal requerido:**
     $$\text{cosechadores\_requeridos} = \left\lceil \frac{\text{cajas\_objetivo}}{\text{capacidad\_cosechador\_dia (default 40)}} \times 1.08 \text{ (ausentismo)} \right\rceil$$
   - Semáforo de desviación: `>= 15%` = `CRITICO`, `>= 8%` = `ALERTA`, `< 8%` = `OK`. Alerta RH `CRITICO` si `vacante_neta >= 3`.
   - **Bitácora de Desviaciones/Riesgos (`desviaciones_riesgo`):** causa raíz + personal faltante + desarrollos atrasados + impacto/riesgo comercial + pérdida estimada + cierre (`ABIERTO → EN_CORRECCION → CERRADO`).
   - **Generalización pendiente de SEAH:** en v2 el plan Grower y Análisis MO nacen parametrizados por `(empresa_id, cultivo_id)` (Frambuesa, Fresa, Arándano), resolviendo la deuda técnica de hardcodeo a Frambuesa.
2. **Configuración Semanal, Rol Semanal y Rol de Descansos:**
   - **`rol_semanal_personal`:** estatus día por día (L–S) por persona; calcula `dias_trabajados` excluyendo catálogo configurable `configuracion_estatus_no_laboral` (`DESCANSO`, `PERMISO`, `FALTA`, `INCAPACIDAD`).
   - **`rol_descansos`:** `dia_descanso_original` vs `dia_descanso_efectivo`, motivo de cambio, `cobertura_persona_id` y `cobertura_estatus` (`PENDIENTE`|`CUBIERTO`). Los cambios se registran en `bitacora_movimientos_personal`.
   - **`asignacion_modulo_semanal` y `asignacion_diaria_labores`:** asigna personal por fecha/módulo/actividad (`COSECHA`, `CULTURALES`, `RIEGO`, `APLICACIONES`, `EMPAQUE`, `MANTENIMIENTO`, `OTRO`) cruzando contra descansos y solo mostrando personal `ACTIVO_CONFIRMADO`.
   - **Regla de movimiento en piso (`ROLES_RESPONSABILIDADES` + `esJefeMO_`):** un `SUPERVISOR` solo puede mover personal entre los módulos de su propia zona (si tiene 2+); mover personal **entre zonas de distintos supervisores** es facultad exclusiva de `JEFE_MO` (validado en servidor).
3. **Autorizaciones Operativas de Destajo (`autorizaciones_operativas`) — REGLA CRÍTICA DE NEGOCIO:**
   - Ninguna caja capturada en campo es pagable por destajo si no existe una autorización operativa `ACTIVA` vigente en esa fecha/módulo/cultivo.
   - **Comodín:** `modulo` o `cultivo` en blanco (`NULL`) en la autorización aplica a todos los módulos/cultivos.
   - **Inmutabilidad:** cerrar una autorización (`CERRADA`) conserva el historial; toda captura posterior vuelve automáticamente a `SOLO_COMPUTO` (`cajas_pagables = 0`).
   - **Banderas que gobierna cada autorización:** `tipo_autorizacion` (`ARRANQUE_DESTAJO`, etc.), `tipo_umbral` (`MODULO_DIA`, etc.), `umbral_cajas`, `aplica_destajo`, `aplica_comida`, `aplica_bono_pesador`, `aplica_bono_supervisor`.
4. **Captura en Campo (Dos flujos unificables en v2: `TabletGrower` + `Tablet de Campo`):**
   - **Captura de cajas (`captura_tablet_grower` + `cajas_diarias_persona`):**
     - Cruza contra `asignacion_diaria_labores` **sin bloquear el guardado**, registrando `alerta_asignacion` (`SIN_TRABAJADOR_IDENTIFICADO`, `SIN_ASIGNACION_REGISTRADA`, `MARCADO_AUSENTE_HOY`, `MODULO_DISTINTO_AL_ASIGNADO`).
     - Ajustes manuales (`AJUSTE_MANUAL`) exigen `supervisor_autoriza` y `comprobante_ajuste` y no pasan como pagables automáticamente.
     - Ajustes negativos (`cajas < 0` o `AJUSTE_NEGATIVO`) quedan como no pagables hasta revisión.
     - Captura por cajas **y/o clamshells** según presentación; confirmación del trabajador con **NIP de 4 dígitos** (`nip_confirmado`).
   - **Captura retroactiva / día completo (`captura_dia_completo`):** wizard con guardado de `BORRADOR` retomable + validación obligatoria de cuadre exacto (`Σ cajas cosechadores == Σ cajas por presentación`) antes de marcar `COMPLETO`.
   - **Cierre diario de módulo y Revisión de Oficina (`cierre_tablet_grower`, `validacion_oficina_tablet`, `administracion_cosecha.html`):** antes de cerrar prenómina, oficina revisa 3 señales: (1) capturas/cierres `PENDIENTE_REVISION`, (2) capturas con `alerta_asignacion`, (3) capturas en `SOLO_COMPUTO`.
   - **Controles apagables de Tablet (`CONFIG_CONTROLES_TABLET`):** interruptor general y override por módulo para activar/desactivar controles de `BANO` y `COMIDA` en días de poca gente.
   - **Snapshots de avance (`avance_snapshots`):** progreso cada 10 min (`pct`, `cajas`, `metros`, `hora_salida_est`), alerta si el avance cae debajo de `UMBRAL_ALERTA_AVANCE_DIA = 0.70` del prorrateo esperado por hora.
   - **Permisos de personal F14 (`permisos_personal`):** solicitud desde campo → bandeja filtrada por módulos del Supervisor/Jefe → aprobación o rechazo firmado con **PIN del jefe/supervisor** (`usuarios_sistema`).
   - **Avisos (`avisos_personal`), Cuadro de Honor (`evaluaciones_cosechador`, `reportes_cosechador`, `ranking_cosechadores_historico`) y Autoconsulta (`consulta_cosechador`):** el cosechador consulta sus cajas confirmadas por NIP, acumulado semanal, dinero estimado, derecho a comida, descansos, permisos y avisos; además puede cambiar su propio NIP.

#### Mapeo a PostgreSQL
- **`planes_grower` (NUEVA) + `planes_grower_semanas` (NUEVA) + `planes_grower_modulos` (NUEVA) + `planes_grower_versiones` (NUEVA):** elimina el chunking de 45KB y normaliza curvas por `(empresa_id, cultivo_id, ciclo, semana_seah, lote_id/modulo)` conservando snapshot JSONB + `causa_cambio` por versión.
- **`desviaciones_riesgo` (NUEVA):** causa raíz, impacto comercial, estatus y cierre.
- **`rol_semanal_personal` (NUEVA) + `catalogo_estatus_no_laboral` (NUEVA).**
- **`rol_descansos` (NUEVA):** descanso original/efectivo, cobertura y estatus.
- **`asignaciones_modulo_semanal` (NUEVA) + `asignaciones_diaria_labores` (NUEVA):** con `UNIQUE(persona_id, fecha)` y `estatus_asistencia`.
- **`autorizaciones_operativas` (NUEVA):** `id UUID`, `empresa_id`, `cultivo_id NULL`, `lote_modulo_id NULL`, `fecha`, `semana_seah`, `tipo_autorizacion`, `tipo_umbral`, `umbral_cajas`, `vigencia_inicio`, `vigencia_fin`, `aplica_destajo`, `aplica_comida`, `aplica_bono_pesador`, `aplica_bono_supervisor`, `autoriza_usuario_id`, `rol_autoriza`, `estatus` (`ACTIVA`|`CERRADA`), `cerrada_por`, `cerrada_en`.
- **Evolucionar `registros_cosecha`:** agregar `client_event_uuid UUID UNIQUE` (idempotencia offline), `empresa_id`, `semana_seah`, `presentacion_id FK`, `clams NUMERIC`, `tipo_evento` (`CAPTURA_COSECHA`|`AJUSTE_MANUAL`|`AJUSTE_NEGATIVO`), `cajas_computo`, `cajas_pagables`, `autorizacion_operativa_id FK NULL`, `destajo_activo BOOLEAN`, `estatus_pago` (`EN_REVISION`|`SOLO_COMPUTO`|`APROBADO`), `motivo_no_pagable`, `alerta_asignacion`, `nip_confirmado BOOLEAN`, `nip_confirmado_en TIMESTAMPTZ`, `supervisor_autoriza_id`, `comprobante_ajuste`, `estatus_oficina` (`PENDIENTE_REVISION`|`REVISADO`|`CON_OBSERVACION`), `revisado_por`, `revisado_en`.
- **`cierres_diarios_modulo` (NUEVA) + `validaciones_oficina_cosecha` (NUEVA) + `capturas_dia_completo` (NUEVA, para flujo retroactivo con `estado`: `BORRADOR`|`COMPLETO`).**
- **`avance_snapshots` (NUEVA) + `config_controles_tablet` (NUEVA).**
- **`permisos_personal` (NUEVA, F14 con `autorizado_por_id` y `pin_verificado BOOLEAN`) + `avisos_personal` (NUEVA).**
- **`evaluaciones_cosechador` (NUEVA) + `reportes_cosechador` (NUEVA) + `ranking_cosechadores_historico` (NUEVA).**

#### Servicios/Endpoints FastAPI y Frontend
- **Router `grower_router.py` (`/api/v1/grower/`):** planes, versiones con causa, motor PHVA (`GET /phva`), requisiciones RH desde plan, historial de curvas, desviaciones/riesgos.
- **Router `personal_operativo_router.py` (`/api/v1/operacion/`):** configuración semanal, rol semanal, rol de descansos + coberturas, asignación diaria + movimiento de personal con validación server-side de zona/Jefe MO, permisos F14 (solicitar/autorizar con PIN), avisos.
- **Router `cosecha_router.py` (`/api/v1/cosecha/`):** CRUD/cierre `autorizaciones-operativas`, captura en vivo + retroactiva (borrador/finalizar con cuadre), confirmación por NIP, cierres diarios, revisión de oficina (`administracion_cosecha`), snapshots de avance, controles tablet (`BANO`/`COMIDA`), Cuadro de Honor y Mi Consulta.
- **Frontend:** Unificar en vistas modulares: **Planeación Grower + Análisis MO + Historial**, **Configuración Semanal / Rol Semanal / Descansos**, **Tablet Campo PWA** (con modos Pesador / Supervisor / Jefe MO + captura retroactiva), **Administración de Cosecha y Autorizaciones**, **Reportes de Avance**, **Cuadro de Honor**, **Mi Consulta (Autoconsulta Cosechador)**.

---

### 4.5 Dominio 5: Pagos, Destajo, Prenómina Semanal y Auditoría Universal de Dinero

#### Reglas de Negocio Legadas (`REGLAS_PAGO`, `calcularPrenominaSemana`, `auditoria_dinero`)
1. **Reglas de pago configurables (`configuracion_reglas_pago`, 2026):**
   - `umbral_cajas_destajo = 80` cajas/semana.
   - `precio_por_caja = PAGO_POR_CAJA = $28.00` MXN (Lunes a Sábado).
   - `minimo_garantizado = SALARIO_MINIMO_SEMANAL = $2,350.00` MXN.
   - `merma_max_pct = 7%` (genera alerta de merma alta).
   - **Esquema de Domingo (`calcularPagoDomingo_`):**
     - Primeras `META_CAJAS_DOMINGO = 10` cajas → `$28.00`/caja (`PAGO_CAJA_DOMINGO_NORMAL`).
     - Excedente (`cajas_domingo - 10`) → `$40.00`/caja (`PAGO_CAJA_DOMINGO_DESPUES_META`).
   - **Comedor:** `COSTO_ALMUERZO = $35.00`, `COSTO_COMIDA = $50.00`.
   - Validación dura: toda regla debe ser `> 0` (rechaza `0` o `NaN` para no arriesgar pagos). Todo cambio dispara `auditoria_dinero`.
2. **Clasificación `DESTAJO` vs `FIJO` (`PUESTOS_SUELDO_FIJO`):**
   - **DESTAJO:** `es_cosechador AND modalidad != 'IMSS'`.
     $$\text{monto\_destajo} = (\text{cajas\_lun\_sab} \times 28) + \text{pago\_domingo}(\text{cajas\_dom})$$
     $$\text{monto\_total\_calculado} = \max(\text{monto\_destajo},\ 2350)$$
     Día de pago estimado: *Lunes después de las 14:30*.
   - **FIJO:** puestos administrativos/staff/pesador/supervisor/jefe/técnicos/empaque o modalidad `IMSS` con sueldo fijo semanal. Día de pago estimado: *Sábado (si trabajó L–V) / Lunes (si trabajó sábado)*.
3. **REGLA CRÍTICA CONFIRMADA (7/jul/2026) — Comida y Hospedaje NO se descuentan del sueldo:**
   - Ni la comida ni el hospedaje en villas se cobran al trabajador; son **gasto operativo de la empresa**.
   - En `prenomina_semanal`, `costo_comida_semana` y `costo_hospedaje_semana` se calculan y muestran únicamente como referencia de gasto/costo real; `monto_neto_estimado` **NO** los resta (solo aplican deducciones reales autorizadas como préstamos/créditos externos/faltas cuando correspondan).
4. **Cierre de Prenómina (`cerrarPrenominaSemana`):**
   - Al cerrar `(semana, empresa)`, los renglones pasan a `CERRADO` con `cerrado_por` y `fecha_cierre` (inmutables ante recálculos accidentales) y queda evidencia obligatoria en `auditoria_dinero`.
5. **Auditoría Universal y de Dinero (`auditoria_dinero`, `persona_eventos`, `bitacora_movimientos_personal`):**
   - En SEAH la auditoría universal estaba parcial (brecha §6 de `SEAH_Vision_Arquitectura.md`). En PostgreSQL se unifica como interceptor/servicio transversal para **todos** los cambios de dinero (reglas de pago, salarios, incrementos, cierre prenómina, decisiones GSP, costos contables, finiquitos, préstamos) y cambios sensibles de identidad/estatus.

#### Mapeo a PostgreSQL
- **`configuracion_reglas_pago` (NUEVA):** `id`, `empresa_id NULL`, `cultivo_id NULL`, `clave`, `valor NUMERIC(12,2) CHECK (valor > 0)`, `descripcion`, `vigente_desde`, `vigente_hasta`, `actualizado_por`, `actualizado_en`. (Complementa `reglas_pago_tarifas` existente para soportar reglas semanales globales + tarifas por cultivo/labor).
- **`prenomina_semanal` (NUEVA — junto a `prenomina_diaria` como desglose diario):** `id UUID`, `semana_seah INT`, `anio INT`, `empresa_id FK`, `persona_id FK`, `relacion_laboral_id FK`, `puesto_snapshot`, `modalidad_imss`, `tipo_pago` (`FIJO`|`DESTAJO`), `dias_trabajados`, `cajas_lun_sab`, `cajas_domingo`, `cajas_validas_semana`, `monto_destajo_lun_sab`, `monto_destajo_domingo`, `monto_destajo_total`, `monto_minimo_garantizado`, `monto_fijo`, `monto_bonos`, `monto_bruto_calculado`, `deduccion_prestamos`, `deduccion_creditos_externos`, `otras_deducciones`, `monto_neto_pagar`, `costo_comida_empresa_ref`, `costo_hospedaje_empresa_ref`, `dia_pago_estimado`, `estatus` (`CALCULADO`|`VALIDADO`|`CERRADO`|`EXPORTADO_MERQURY`), `lote_exportacion_merqury`, `cerrado_por`, `fecha_cierre`, `UNIQUE(anio, semana_seah, empresa_id, persona_id)`.
- **`auditoria_universal` (NUEVA):** `id UUID`, `fecha_hora TIMESTAMPTZ`, `es_dinero BOOLEAN`, `modulo`, `entidad_tipo`, `entidad_id`, `entidad_desc`, `campo`, `valor_anterior`, `valor_nuevo`, `motivo`, `usuario_id FK`, `ip_origen`, `origen_endpoint`.
- **`bitacora_movimientos_personal` (NUEVA):** registro específico de cambios de módulo, descansos, coberturas y puestos.

#### Servicios/Endpoints FastAPI y Frontend
- **Servicio `pagos_service.py` (ampliación de `MotorPagosCampo`):** incorporar `calcular_pago_domingo()`, `calcular_prenomina_semanal()` (leyendo exclusivamente `cajas_pagables` autorizadas + conciliación de comida/hospedaje como costo empresa + abonos de préstamos), y `cerrar_prenomina_semana()` transaccional.
- **Router `prenomina_router.py` (`/api/v1/prenomina/`):** `GET/PUT /reglas-pago`, `POST /calcular`, `GET /semana/{semana}`, `POST /cerrar`, `GET /persona/{persona_id}`.
- **Router `auditoria_router.py` (`/api/v1/auditoria/`):** `GET /dinero`, `GET /universal`, `GET /movimientos-personal` (solo `DIRECCION`/`ADMIN`).
- **Frontend:** Vistas **Prenómina Semanal** (con indicadores de alertas pendientes de oficina antes de cerrar), **Configurador de Reglas de Pago**, **Auditoría de Dinero**.

---

### 4.6 Dominio 6: Área Técnica, Agroquímicos, Riego, Inocuidad, Calidad y Limpieza

#### Reglas de Negocio Legadas
1. **Separación por Cultivo vs Transversal (regla explícita de Luis 4/jul/2026):**
   - **Por cultivo (`cultivo_id` obligatorio):** Monitoreo Técnico, Catálogo de Agroquímicos, Aplicaciones, Recetas de Riego, Mediciones de Riego.
   - **Transversal / Compartido (`sin cultivo_id`):** Inocuidad (`INOCUIDAD_SHEET`), Calidad de Cosecha (`CALIDAD_COSECHA_SHEET`), Calidad de Pesado (`CALIDAD_PESADO_SHEET`), Entrega a Comercio/Frío (`ENTREGA_COMERCIO_FRIO_SHEET`), Limpieza de Módulo (`LIMPIEZA_MODULO_SHEET`).
2. **Verificación de Agroquímicos (`verificarAplicacion`):**
   - Compara contra catálogo autorizado (`dosis_recomendada`, `unidad_dosis`, `intervalo_reingreso_horas`, `intervalo_preconsecha_dias`, `registro_sanitario`, `activo`).
   - Emite alertas (no bloqueantes al guardar registro, pero sí activando bloqueo fitosanitario en el lote si hay intervalo de seguridad/preconsecha):
     - Producto inactivo/dado de baja en catálogo.
     - Dosis aplicada `> dosis_recomendada × 1.10` (+10% de exceso).
     - Violación de intervalo de preconsecha (`dias_hasta_cosecha < intervalo_preconsecha_dias`).
   - **Integración con v2 existente:** el trigger `trg_bloqueo_fitosanitario` en `04_schema_tec_inv_log.sql` (una vez corregido `\vert{}\vert{}` → `||`) bloquea automáticamente `lotes_produccion.estatus_fitosanitario = 'BLOQUEADO_INTERVALO_SEGURIDAD'` y calcula `fecha_liberacion_corte`, impidiendo cosecha en tablet hasta vencimiento del PHI/REI.
3. **Riego y Fertirriego:**
   - **Recetas de riego:** componentes nutritivos JSON (`[{nutriente, concentracion, unidad}]`) + `ph_objetivo` + `ec_objetivo` por cultivo.
   - **Mediciones de riego:** bitácora por módulo/fecha (`ph_medido`, `ec_medido`, `drenaje_pct`, `quimicos_solucion`) comparada contra receta activa.
4. **Inocuidad, Calidad, Limpieza y Labores Culturales:**
   - **Inocuidad:** 8 categorías base configurables (`HIGIENE_PERSONAL`, `LAVADO_MANOS`, `AGUA_Y_HIELO`, `SANITARIOS`, `MANEJO_RESIDUOS`, `CONTROL_PLAGAS_INSTALACIONES`, `EPP`, `TRAZABILIDAD`), estatus `SI | NO | PARCIAL`, hallazgo y acción correctiva.
   - **Calidad Cosecha:** `pct_primera`, `pct_rechazo`, `motivo_rechazo`.
   - **Calidad Pesado:** `peso_esperado_kg`, `peso_real_kg`, cálculo automático `diferencia_pct = round(((real - esperado) / esperado) * 100, 1)`.
   - **Limpieza Módulo:** áreas default (`BAÑOS`, `COMEDOR`, `BODEGA`, `MÓDULO GENERAL`), estatus `OK | PENDIENTE | PROBLEMA`.
   - **Labores Culturales:** avance porcentual por `(modulo, semana, labor)` sobre catálogo configurable.

#### Mapeo a PostgreSQL
- **Ampliar `insumos_agricolas` (ya existe en `04_schema_tec_inv_log.sql`):** agregar `cultivo_id FK NULL`, `dosis_recomendada`, `unidad_dosis`, `intervalo_reingreso_horas INT`, `registro_sanitario`, `actualizado_por`, `actualizado_en`. (Renombrar/mapear `dias_intervalo_seguridad` como `intervalo_preconsecha_dias`).
- **Ampliar `aplicaciones_fitosanitarias` (ya existe):** agregar `empresa_id`, `cultivo_id`, `semana_seah`, `tipo_aplicacion` (`RIEGO`|`FERTIRRIEGO`|`FITOSANITARIO`|`FOLIAR`), `producto_texto_libre` (por compatibilidad si no está en catálogo), `alertas_verificacion_json JSONB`, `fecha_reingreso_calculada TIMESTAMPTZ`. Corregir trigger `fn_bloquear_lote_por_aplicacion()` y agregar job/vista que libere automáticamente cuando `NOW() >= fecha_liberacion_corte`.
- **`monitoreo_tecnico_categorias` (NUEVA) + `monitoreo_tecnico_registros` (NUEVA):** `lote_id`, `empresa_id`, `cultivo_id`, `semana_seah`, `categoria`, `nivel` (`BAJO`|`MEDIO`|`ALTO`), `hallazgo`, `accion_sugerida`, `responsable_id`, `fecha`.
- **`recetas_riego` (NUEVA) + `riego_mediciones` (NUEVA).**
- **`inocuidad_categorias` (NUEVA) + `inocuidad_registros` (NUEVA, sin `cultivo_id`).**
- **`calidad_cosecha_registros` (NUEVA) + `calidad_pesado_registros` (NUEVA) + `limpieza_modulo_registros` (NUEVA) + `labores_culturales_avance_modulo` (NUEVA).**

#### Servicios/Endpoints FastAPI y Frontend
- **Router `tecnico_router.py` (`/api/v1/tecnico/`):** catálogos configurables, monitoreo técnico, catálogo agroquímicos, `POST /aplicaciones/verificar` + `POST /aplicaciones` (retorna alertas + nuevo estatus del lote), recetas y mediciones de riego.
- **Router `inocuidad_calidad_router.py` (`/api/v1/calidad-inocuidad/`):** inocuidad, calidad cosecha, calidad pesado, limpieza de módulos, avance labores culturales.
- **Frontend:** Sub-módulos en Tablet Supervisor/Técnico + tablero web de **Área Técnica (por cultivo)** y **Inocuidad & Calidad (transversal)** con alertas activas de lotes bloqueados por PHI/REI.

---

### 4.7 Dominio 7: Villas (Hospedaje) y Comedor

#### Reglas de Negocio Legadas
1. **Villas y Camas (`villas_hospedaje`, `camas_villas`):**
   - Control de capacidad y ocupación (`disponibles = capacidad - ocupadas`, `% ocupación`) por empresa (`NFA`/`BIO`).
   - **Candado obligatorio (#24):** no se permite asignar cama sin `costo_semanal > 0` (evita hospedajes "en $0" invisibles en costos de prenómina).
   - Validación de unicidad: no permite asignar una `(villa_id, numero_cama)` ya `OCUPADA`.
   - Marcado de residentes permanentes (`PERSONAS_PERMANENTES_VILLAS_`).
   - Cálculo de costo semanal por persona para prenómina: suma asignaciones activas (`OCUPADA` o con `fecha_salida >= inicio_semana`).
2. **Comedores y Reparto Diario (`CONFIG_COMEDORES`, `comidas_diarias`, `control_comida.html`):**
   - Una cuadrilla externa reparte en comedores físicos (`C1..C4`), cada uno configurado con los módulos que cubre (ej. `C1: M1-M3`, `C2: M4-M6`, `C3: M7-M9`, `C4: M10-M11`). Alerta de módulos sin comedor asignado.
   - **Regla de derecho a comida:**
     - **FIJA (sin condición de meta):** `PESADOR`, `SUPERVISOR`, `JEFE_MO`, `JEFE`, `GROWER`, `COORDINADOR_PRODUCCION`, `ENCARGADO_INVERNADERO`, `MONITOR`, `AUXILIAR` (Aux. Operativo).
     - **CONDICIONADA (Cosechadores — Caso H):** tiene derecho si `cajas_hoy >= META_CAJAS_COMIDA` (configurable, default `60`, o según autorización operativa activa `aplica_comida`). *(En el HTML legado `obtenerCajasHoy()` estaba simulado con `Math.random()`; en v2 se conecta directo a `registros_cosecha` reales del día).*
   - Registro diario de `almuerzo` (`$35`) y `comida` (`$50`) tomados dinámicamente de `configuracion_reglas_pago` → `total_costo_dia`.

#### Mapeo a PostgreSQL
- **`villas_hospedaje` (NUEVA):** `id SERIAL`, `empresa_id FK`, `nombre_villa`, `capacidad_camas INT CHECK (capacidad_camas > 0)`, `responsable_id FK`, `estatus` (`ACTIVA`|`INACTIVA`), `observaciones`.
- **`asignaciones_camas_villas` (NUEVA):** `id UUID`, `villa_id FK`, `numero_cama VARCHAR(20)`, `persona_id FK`, `empresa_id FK`, `fecha_ingreso DATE`, `fecha_salida DATE NULL`, `tipo_hospedaje` (`FORANEO`|`PERMANENTE`), `costo_semanal NUMERIC(10,2) NOT NULL CHECK (costo_semanal > 0)`, `estatus_cama` (`OCUPADA`|`LIBERADA`), `observaciones`. **Índice único parcial:** `CREATE UNIQUE INDEX uq_cama_ocupada ON asignaciones_camas_villas(villa_id, numero_cama) WHERE estatus_cama = 'OCUPADA';`.
- **`comedores_config` (NUEVA) + `comedor_modulos` (NUEVA):** relación `1:N` entre comedores físicos y `lotes_produccion`/módulos (con `UNIQUE(lote_modulo_id)` para evitar que un módulo pertenezca a dos comedores).
- **`comidas_diarias` (NUEVA):** `id UUID`, `fecha DATE`, `semana_seah INT`, `persona_id FK`, `empresa_id FK`, `comedor_id FK NULL`, `tipo_derecho` (`FIJA`|`CONDICIONADA_OK`|`AUTORIZACION_ESPECIAL`), `cajas_dia_referencia`, `almuerzo BOOLEAN`, `comida BOOLEAN`, `costo_almuerzo`, `costo_comida`, `total_costo_dia`, `capturo_usuario_id`, `observaciones`, `UNIQUE(fecha, persona_id)`.

#### Servicios/Endpoints FastAPI y Frontend
- **Router `villas_comedor_router.py` (`/api/v1/servicios/`):** disponibilidad villas, asignar/liberar cama (con candado `costo_semanal > 0`), config comedores, reparto diario de comidas con cálculo real de derecho desde cosecha del día, resumen semanal de costos por empresa.
- **Frontend:** Vistas **Villas y Hospedaje** (mapa de ocupación y asignaciones integrado con expediente RH) y **Control de Comida Diario** (reparto por comedor conectado a cajas reales, sin datos simulados).

---

### 4.8 Dominio 8: Comercial, GSP Mastronardi, Postcosecha, Empaque y Embarques

#### Reglas de Negocio Legadas
1. **Catálogo de Presentaciones Comerciales (`catalogo_presentaciones_comercial`):**
   - Configurable por `(empresa, cultivo)` (no hardcodeado). Semilla real Frambuesa NFA 2026:
     - Exportación (USD, piso `$19`, costo directo `$13.50`): `RRAS1020` (*6×12oz Sunset Dream BlkGold No1*, 200 cajas/pallet), `RRAS1024` (*6×12oz Sunset Dream No1*, 200 cajas/pallet), `RRAS1023` (*12×6oz Sunset MEX Dream No1*, 240 cajas/pallet).
     - Nacional (MXN): `NAC-EXP` (piso `$249.78`), `NAC-SOB` (piso `$100.00`), `MERMA`.
   - `tipo_venta`: `CAJA` vs `GRANEL` (para Fresa a granel por kg) + bandera `aplica_prestamo_cajas`.
2. **Control de Préstamo de Cajas Físicas (`control_prestamo_cajas`):**
   - Lleva `cantidad_prestada`, `cantidad_devuelta` y `saldo_pendiente` por cliente/cultivo (Fresa a granel), rechazando devoluciones que excedan lo prestado.
3. **Espejo GSP Mastronardi y Gate Comercial (`gsp_pronostico_mastro`, `gsp_decision_comercial`):**
   - Guarda snapshots históricos del pronóstico semanal enviado por Mastronardi (`kg_semana_pronosticado`, `casos_pronosticado`, `rendimiento_kg_m2`).
   - **Espejo Plan vs GSP (`compararPlanVsGSP`):** compara kg de Planeación Grower (`cajas × peso_comercial`, ej. `2.04 kg`) contra último pronóstico GSP; alerta si `|desviación %| > tolerancia` (default `10%`).
   - **Decisión Comercial GSP (Gate de Producción):** estados `Pendiente | Solicitado | Aceptado | Rechazado | Bloqueada`.
     - Si `bloqueada = TRUE`, rechaza cualquier edición.
     - Una semana modificable **NO puede bajar a producción/módulos** (`gspSemanaListaParaProduccion`) hasta que esté `estado = 'Aceptado'` y `cajas_confirmadas > 0`. Todo cambio en cifras/destino dispara `auditoria_dinero`.
4. **Flujo Completo de Postcosecha, Empaque y Embarques (`postcosecha.html`, `entrega_comercio_frio_registro`, `pedidos_nacionales`, `postcosecha_exportaciones_semana`):**
   - **7 Etapas:** `Recolección → Preenfriado → Conservación → Calidad → Embarque Exportación → Pedido Nacional → Facturación`.
   - **Recolección interna de módulos (`RUTAS_RECOLECCION_INTERNA`):** 2 rutas compartidas entre cultivos — **Roja** (`M1–M6`) y **Gris** (`M7–M11` + fresa); capacidad referencia 350 cajas frambuesa / 184 cajas fresa; taras de `4 kg`, `6 kg`, `10 kg`; duración vuelta 45–80 min.
   - **Entrega a Comercio/Frío:** guía, cajas entregadas, hora, temperatura (°C), quien entrega y recibe.
   - **Preenfriado y Conservación:** control de tiempos entrada/salida preenfriado, temperatura objetivo `2°C` y bitácora continua de temperaturas (`registro_temps`).
   - **Vehículos y Pallets Reales (confirmados 4/jul/2026):**
     - `Isuzu`: 3 pallets (`1 termo 180 + 2 normales 192` = **564 cajas**).
     - `3.5 Ton`: 6 pallets (`2 termo 180 + 4 normales 192` = **1,128 cajas**).
     - `Trailer` (recolección): capacidad referencial pendiente de confirmar.
     - **Mínimo de recolección Mastronardi:** **1,920 cajas** (8 pallets).
   - **Embarques de Exportación:** número de embarque, semana cosecha, pallets, tarimas `CHEP`, cajas 12oz/6oz, total cajas/kilos, `PO`, número de factura, valor factura, agente aduanal, unidad/camión.
   - **Pedidos Nacionales (`pedidos_nacionales`, flujo Patricia Vega — rol `COMERCIAL`):**
     - `OFRECIDO` (cajas fresa 1lb, kg fresa granel, cajas frambuesa + tono) → `AUTORIZADO` (Comercial) → `ENTREGADO` (destino `PACHUCA` | `FRACCIONAMIENTO`, cantidades realmente entregadas pueden diferir de lo ofrecido) o `CANCELADO`.

#### Mapeo a PostgreSQL
- **`catalogo_presentaciones` (NUEVA):** `id SERIAL`, `empresa_id FK`, `cultivo_id FK`, `codigo`, `descripcion`, `tipo_venta` (`CAJA`|`GRANEL`), `unidad`, `peso_neto_kg`, `pallet_cajas`, `moneda_venta` (`USD`|`MXN`), `piso_precio_usd`, `piso_precio_mxn`, `costo_directo_usd`, `aplica_prestamo_cajas`, `activo`.
- **`prestamos_cajas_clientes` (NUEVA) + `prestamos_cajas_movimientos` (NUEVA):** control auditable de entregas y devoluciones de cajas plásticas.
- **`gsp_pronosticos` (NUEVA):** snapshots inmutables por `(empresa_id, cultivo_id, semana_seah, fecha_captura)`.
- **`gsp_decisiones_comerciales` (NUEVA):** gate semanal con `bloqueada`, `estado`, `cajas_base`, `cajas_mas20`, `cajas_confirmadas`, `cajas_ajuste`, `presentacion_id`, `destino`, `UNIQUE(empresa_id, cultivo_id, semana_seah)`.
- **`programa_comercial_snapshots` (NUEVA):** snapshot semanal del programa comercial (se respeta decisión de no alterar lógica de Frambuesa hasta definición comercial).
- **`vehiculos_flota` (NUEVA) + `rutas_recoleccion_interna` (NUEVA):** Isuzu 564, 3.5 Ton 1,128, Trailer, rutas Roja/Gris.
- **`postcosecha_lotes` (NUEVA):** trazabilidad desde recolección interna (`lote_produccion_id`, `taras_json`, `cajas_bruto`, `kg_bruto`, `merma_kg`, `cajas_neto`, `kg_neto`, `hora_recoleccion`, `hora_entrada_preenfriado`, `hora_salida_preenfriado`, `hora_entrada_conservacion`, `temp_conservacion`, `estado` (`RECOLECTADO`|`PREENFRIANDO`|`CONSERVACION`|`EMBARCADO`|`NACIONAL`), `entrega_frio_folio`, `embarque_id FK`).
- **`conservacion_temperaturas` (NUEVA):** serie temporal de temperatura en cuarto frío.
- **`embarques_exportacion` (NUEVA) + `embarques_exportacion_detalle` (NUEVA):** `embarque_num`, `semana_seah`, `empresa_id`, `vehiculo_id`, `po`, `pallets`, `chep`, `cajas_sueltas`, `total_cajas`, `total_kilos`, `factura_num`, `valor_factura`, `agente_aduanal`, `merma_global_kg`, `ts_inicio_carga`, `ts_salida`.
- **`pedidos_nacionales` (NUEVA):** flujo `OFRECIDO → AUTORIZADO → ENTREGADO | CANCELADO` con cantidades ofrecidas vs entregadas y destino (`PACHUCA` | `FRACCIONAMIENTO`).

#### Servicios/Endpoints FastAPI y Frontend
- **Router `comercial_router.py` (`/api/v1/comercial/`):** catálogo de presentaciones, préstamo de cajas clientes, pronósticos GSP + espejo Plan vs GSP, decisiones comerciales GSP + gate `semana-lista-produccion`, snapshots programa comercial.
- **Router `postcosecha_router.py` (`/api/v1/postcosecha/`):** entregas a comercio/frío, lotes postcosecha (recolección → preenfriado → conservación → embarque), registro de temperaturas cuarto frío, embarques exportación + histórico, pedidos nacionales (ofertar/autorizar/entregar).
- **Frontend:** **Programa Comercial & Espejo GSP**, **Configuración Comercial y Préstamo de Cajas**, **Postcosecha 7 Etapas (Empaque · Frío · Embarque · Nacional · Facturación)** (migrando todo el estado que hoy vivía solo en `localStorage` hacia PostgreSQL + cache offline).

---

### 4.9 Dominio 9: Seguridad, Usuarios, Roles, NIPs y Matriz de Permisos Real

#### Reglas de Negocio Legadas y Brechas a Resolver
1. **Unificación de usuarios (`usuarios_sistema`):** un usuario puede tener `rol_menu` (`DIRECCION`, `ADMIN`, `JEFATURA`, `SUPERVISOR`, `PESADOR`, `COMERCIAL`) y/o `rol_tablet` (`JEFE`, `SUP_A/B/C`, `PESADOR_A/B/C`) + módulos asignados. Derivación automática si solo se captura rol de tablet.
2. **Corrección de vulnerabilidades heredadas de Sheets:**
   - Contraseñas en texto plano (`"1234"`) y bug numérico de Sheets (`1234 !== "1234"`): en v2 se almacenan **hasheadas con `bcrypt`** (`passlib`) y autenticación mediante **JWT (`python-jose`)** con refresh token + expiración.
   - Matriz de permisos solo visual (`matriz_permisos.html`): en v2 los permisos viven en DB (`roles`, `permisos`, `rol_permisos`) y se validan en **cada endpoint FastAPI** mediante `Depends(require_permission("modulo:accion"))`.
   - `rol = COMERCIAL` (ej. Patricia Vega) solo accede a `postcosecha:nacional` y endpoints estrictamente permitidos.
3. **Gestión de NIPs de Cosechadores (`nips_personal`):**
   - NIP de 4 dígitos para confirmar cajas en Tablet; generación aleatoria o manual, revocación lógica, autocambio por el trabajador desde `Mi Consulta` (validando NIP actual) y envío opcional de notificación por correo (SMTP). En v2 se guarda `nip_hash` + salt, o hash rápido verificable offline en tablet mediante token firmado.

#### Mapeo a PostgreSQL
- **`usuarios_sistema` (NUEVA):** `id UUID`, `username VARCHAR(50) UNIQUE`, `nombre`, `persona_id FK NULL`, `password_hash TEXT`, `pin_autorizacion_hash TEXT`, `rol_menu`, `rol_tablet`, `modulos_asignados JSONB`, `empresas_asignadas JSONB`, `activo BOOLEAN`, `debe_cambiar_password BOOLEAN`, `ultimo_login TIMESTAMPTZ`.
- **`roles_permisos_matriz` (NUEVA):** `rol`, `modulo`, `accion` (`READ`|`WRITE`|`APPROVE`|`DELETE`|`EXPORT`), `permitido BOOLEAN`, `UNIQUE(rol, modulo, accion)`.
- **`nips_personal` (NUEVA):** `persona_id PK FK`, `nip_hash TEXT`, `activo BOOLEAN`, `actualizado_por`, `es_autocambio BOOLEAN`, `actualizado_en`.

---

### 4.10 Dominio 10: Modo Offline-First y Sincronización de Campo

#### Cómo funciona hoy en `/mnt/c/clasp_project` (Diagnóstico Real)
- **`TabletGrower.html` (el más maduro):** guarda estado completo en `localStorage`, cada captura nace con `sync_estatus = 'PENDIENTE'`, dispara `guardarEventoTabletGrower()`, marca `SINCRONIZADO` o `ERROR`, tiene botón manual `sincronizarPendientes()` y reintento automático cada **60 segundos** (`setInterval`).
- **`tablet_campo.html`:** guarda estado local (`S`) en `localStorage` con fallback silencioso si el iframe bloquea storage; sincroniza cajas/estatus día best-effort y tiene guardado de `BORRADOR` en servidor para captura retroactiva.
- **`postcosecha.html`, `control_comida.html`, `planeacion_grower.html`:** mantienen gran parte del estado operativo en `localStorage` (riesgo real de pérdida de datos si se limpia caché o se cambia de tablet).
- **Limitaciones actuales:** `localStorage` tiene límite ~5MB, no soporta transacciones ni archivos/firmas grandes, y no maneja idempotencia robusta ante doble envío si se cae la red a medio request.

#### Arquitectura Offline-First Propuesta para v2
1. **Frontend PWA (Vite + Workbox Service Worker + IndexedDB con Dexie.js):**
   - **Cache de lectura local (descarga al iniciar turno / cada 15 min online):** catálogo de `personas` activas confirmadas de los módulos asignados, `lotes_produccion` (con `estatus_fitosanitario` y `fecha_liberacion_corte`), `autorizaciones_operativas` activas del día, `catalogo_presentaciones`, `config_controles_tablet`, y paquete firmado de validación de NIPs para la cuadrilla del turno.
   - **Cola transaccional Outbox (`indexedDB.outbox_events`):** toda captura de cosecha, confirmación NIP, entrega a frío, comida, monitoreo técnico o permiso genera un evento inmutable con `client_event_uuid` (UUID v4), `device_id`, `created_at_device`, `event_type`, `payload_json`, `status` (`PENDING`|`SYNCING`|`SYNCED`|`CONFLICT`|`FAILED`).
   - **Sincronización automática:** escuchando evento `window.addEventListener('online', ...)` + `Background Sync API` + reintento exponencial + botón visible con contador de pendientes (conservando la excelente UX del badge de `TabletGrower.html`).
2. **Backend FastAPI (`POST /api/v1/sync/batch` + tabla `sync_outbox_log`):**
   - **`sync_outbox_log` (NUEVA):** `client_event_uuid UUID PK`, `device_id`, `usuario_id`, `event_type`, `payload_json JSONB`, `created_at_device TIMESTAMPTZ`, `received_at TIMESTAMPTZ`, `status` (`APPLIED`|`DUPLICATE_IGNORED`|`CONFLICT`|`REJECTED`), `server_entity_id UUID`, `error_detail TEXT`.
   - **Idempotencia garantizada:** si un evento llega dos veces por timeout de red en campo, `ON CONFLICT (client_event_uuid) DO NOTHING` devuelve el resultado original sin duplicar cajas ni pagos.
   - **Resolución de conflictos sin pérdida de datos:** si al sincronizar una captura offline el lote estaba bloqueado o no había autorización de destajo, el servidor **nunca descarta el dato en silencio**: o rechaza explícitamente con código de conflicto para resolución en pantalla, o guarda en estado `SOLO_COMPUTO` / `CON_OBSERVACION` para revisión en `Administración de Cosecha`.

---

## 5. Propuesta de Arquitectura Modular para `~/agro-erp-berries-v2`

Se recomienda evolucionar de `main.py` monolítico a un **Monolito Modular por Dominios** (misma base de datos PostgreSQL con esquemas/módulos bien delimitados, cero latencia de red entre dominios, y posibilidad futura de extraer servicios si el volumen lo exige):

```text
~/agro-erp-berries-v2/
├── docker-compose.yml              # db (Postgres 16), backend (FastAPI), frontend (Nginx/Vite), redis (opcional para jobs/cache)
├── database/
│   └── migrations/                 # Alembic (reemplaza scripts .sql manuales rotos; mantiene 00_extensions.sql)
├── backend/
│   ├── alembic.ini
│   └── app/
│       ├── main.py                 # Solo montaje de app, CORS controlado, middlewares, inclusión de routers
│       ├── core/
│       │   ├── config.py           # Pydantic Settings (.env)
│       │   ├── database.py         # AsyncSession + Base SQLAlchemy 2.0
│       │   ├── security.py         # JWT, bcrypt, verificación NIP/PIN, RBAC Depends()
│       │   └── audit.py            # Servicio transversal auditoria_universal / auditoria_dinero
│       ├── modules/
│       │   ├── core_org/           # Empresas NFA/BIO, sucursales+funciones, unidades operativas, áreas, localizaciones físicas, codigos_alternativos, documentos_entidad, cultivos, superficies, calendario SEAH/Mastronardi, ranchos/lotes (incl. Módulo 1.1)
│       │   ├── auth_usuarios/      # Usuarios, multi-rol (usuarios_roles), matriz permisos + alcance empresa/sucursal/unidad, 4 niveles autorización, NIPs, CSRF/sesión
│       │   ├── reclutamiento/      # Plazas autorizadas, levantamientos/versiones perfil, cobertura/aprobaciones, vacantes/publicaciones, portal público, pipeline, evaluaciones, ranking 60/25/15, dictámenes ingreso/reingreso, traspaso
│       │   ├── personal/           # Personas, relaciones laborales, funciones operativas temporales (sin pisar nominal), expediente 16 estados + UPDATE_READY + excepciones, responsivas, contratos, acuses, incrementos, bajas, finiquitos, préstamos
│       │   ├── merqry_sync/        # Conector READ-ONLY MySQL 5.7 Merqry + Import/Export controlado + conciliación checador/nómina + separación estricta IMSS→Merqry vs Especial→Contabilidad
│       │   ├── planeacion_grower/  # Curvas Grower (Long Cane / Primocaña), versiones (base/forecast/real), PHVA, desviaciones/riesgos, Análisis MO (cubrir cajas, no solo plazas)
│       │   ├── operacion_campo/    # Proyección mínima RH→Campo (DailyEligibleWorker), config semanal, rol semanal, descansos/cobertura, asignación diaria, culturales individuales diarios, permisos F14, avisos
│       │   ├── trasplante_recepcion/ # Programación llegadas, recepción documental-física por camión/bin (DOCUMENTARY_TRUCK_FINAL_V1), ledger derivado, equipos Norte/Sur (SUPPLY/MOVE/TRANSPLANT), coordinador multi-camión compartido y CLOSE_PERSON_DAY
│       │   ├── cosecha_tablet/     # Autorizaciones operativas, captura vivo/retroactiva, cierres por unidad/global, separación movilidad personas vs cajas, revisión oficina, Cuadro de Honor, Mi Consulta
│       │   ├── prenomina/          # Motor semanal L-S + Domingo, reglas configurables, máquina de estados (captura→revisión→autorizado→pagable→exportado→recibido), cierre inmutable
│       │   ├── servicios_campo/    # Villas/camas, Control de Comida/Comedores, transporte y documentos operativos asociados
│       │   ├── tecnico_inocuidad/  # Monitoreo, agroquímicos, aplicaciones+PHI/REI, riego/recetas, inocuidad, calidad, limpieza
│       │   ├── comercial_postcos/  # Multi-comercializador (Mastronardi/Hortifrut/Crystal Fields), presentaciones + receta empaque (propio vs consignado), préstamo cajas, GSP espejo/decisión, postcosecha 7 etapas, embarques, pedidos nacionales, CxC
│       │   ├── costeo_merqry/      # Catálogo costeo_cuentas_merqry, reglas prorrateo exacto/operativo (feature flag D18), auxiliar importado, clasificación, resultados cultivo/periodo, 14 controles de riesgo
│       │   ├── direccion_bi/       # Dashboard ejecutivo NFA/BIO/GRU, KPIs, bajas proyectadas (solo DIRECCION), consultoría/seguimiento SGC opcional
│       │   ├── sync_offline/       # Fachada autenticada + batch idempotente (409 en payload distinto, committed.ack para ACK perdido, fencing durable) + snapshots con TTL
│       │   └── ayuda_docs/         # Centro de ayuda, glosario SEAH y fichas contextuales por módulo
│       └── tests/                  # Pytest + httpx AsyncClient + Postgres desechable verificado (suite concurrencia, fencing, aislamiento y cierres)
└── frontend/                       # React + Vite + TypeScript + Tailwind + TanStack Query + Dexie.js (PWA)
    ├── src/
    │   ├── shell/                  # Layout (navegación RH/Comercialización/Producción/Dirección), menú dinámico por matriz RBAC, selector NFA/BIO + Semana, botón Ayuda
    │   ├── offline/                # Dexie DB (IndexedDB real), SyncManager, OutboxBadge, ConflictReviewUI, Service Worker (Workbox)
    │   ├── shared/                 # Componentes UI (modales estructurados estilo pedirDatos_, exportación CSV/XLSX, filtros fecha, visor documentos/QR)
    │   └── modules/                # 1 carpeta por dominio (misma taxonomía que backend/app/modules)
```

---

## 6. Orden de Implementación por Fases (Resumen Actualizado)

> **Nota:** Esta tabla resume el plan de **Fase 0 a Fase 7** ya ajustado tras el cruce con `rrhh-automation-system` y `campo`. El detalle de los ajustes específicos y criterios de entrada/salida por fase se desarrolla en la **Sección 10**.

Alineado a la decisión **D14** (*cerrar primero Contratación, Planeación y Producción antes de e-learning/DC3*), a la urgencia operativa de **Trasplante Multi-Camión** documentada en `campo`, y evitando cortar operación real sin validación:

| Fase | Nombre | Alcance Técnico y Funcional (Ajustado Multi-Repo) | Criterio de Terminado ("Done") |
|---|---|---|---|
| **Fase 0** | **Estabilización Base de `v2` + Puerta de Pruebas Desechable** | Reparar `01_schema_core_rh.sql` (quitar `echo`), eliminar archivos Python corruptos de `02/03`, corregir `\|\|` y vista en `04_schema_tec_inv_log.sql`, configurar **Alembic**, crear seeds reales mínimos (`NFA`/`BIO`, cultivos, sucursal matriz/operativa, lotes incl. Módulo 1.1, usuarios base), corregir bug `total_cajas_exportacion` en `main.py`, configurar `.env`, `pytest` y **guarda de base de pruebas desechable verificada** (nunca asumir desechabilidad solo por nombre). | `docker compose up -d --build` levanta desde cero sin errores, pasan tests smoke de salud/seed y la suite corre aislada sobre DB desechable verificada. |
| **Fase 1** | **Jerarquía Organizacional, Seguridad RBAC con Alcance, Documentos/QR y Migración de Identidad** | Adoptar jerarquía `empresas → sucursales (+ sucursal_funciones, 1 matriz) → unidades_operativas → areas → localizaciones_fisicas (trigger contexto)` + `codigos_alternativos` (QR/claves sin mezclar cuenta contable) + `documentos_entidad`/`catalogo_tipos_documento`; seguridad multi-rol (`usuarios_roles`, `roles_permisos`, 4 niveles de autorización, enforcement server-side por `empresa/sucursal/unidad/rol`, CSRF/JWT/bcrypt, `nips_personal`, `auditoria_universal`/`bitacora_cambios`); separación `personas` + `relaciones_laborales` + `funciones_operativas_temporales`; **script ETL auditable** desde CSV/Sheets/históricos sin fusionar personas por nombre. | Login seguro con JWT/RBAC bloqueando por rol y alcance en servidor, jerarquía NFA/BIO creada, capa documental transversal operativa y 100% de identidades conciliadas sin duplicados ni fusiones automáticas indebidas. |
| **Fase 2** | **RH Completo (Plazas, Reclutamiento D1–D8, Expediente 16 Estados, `UPDATE_READY`) + Conector `Merqry` Solo Lectura** | **Estructura y Reclutamiento:** `plazas_autorizadas → levantamientos/versiones perfil → solicitudes_cobertura → aprobaciones_cobertura → vacantes → publicaciones_vacante`, portal cosecha vs general, detección reingreso multicriterio, evaluaciones + ranking 60/25/15, `dictamenes_ingreso_reingreso` + traspaso formal.<br>**Administración de Personal:** expediente digital de **16 estados** (`LISTO_PARA_TRABAJAR != LISTO_MERQRY != LISTO_PRENOMINA`), bandeja **`UPDATE_READY`** (PIN/firma/bitácora + excepciones temporales con fecha límite y bloqueo futuro), responsivas (uniforme/EPP/herramienta/equipo/vehículo/fondo), contratos `BORRADOR→VALIDADO→FIRMADO` (**prohibida renuncia anticipada**), beneficiarios Art. 501, Acuse Digital, incrementos, bajas/finiquitos LFT 2026, préstamos.<br>**Integración Merqry (READ-ONLY):** conector/staging de lectura sobre MySQL 5.7 (`mq_bio_organicos_analisis` / export controlado) + separación absoluta **`IMSS → Merqry`** vs **`Especial → Contabilidad`**. | Flujo punta a punta plaza → cobertura → vacante → candidato → dictamen → expediente (`UPDATE_READY`) → `LISTO_PARA_TRABAJAR` → `LISTO_MERQRY` → reingreso → finiquito, con lectura y conciliación Merqry sin escritura directa. |
| **Fase 3** | **Operación de Campo Offline-First Endurecida (3A: Trasplante Multi-Camión · 3B: Cosecha, Culturales y Prenómina Semanal)** | **Base común:** Contrato mínimo **`RH → Campo` (`DailyEligibleWorker.v0.1`)** con TTL y sin salarios/expediente; fachada autenticada + PWA **IndexedDB real (`Dexie.js`)** + idempotencia endurecida (**`409 Conflict` en payload distinto**, **`committed.ack`** para ACK perdido, **`DURABLE_COMMAND_FENCE`**).<br>**Subfase 3A (Prioridad inmediata operativa):** Programación documental de llegadas, recepción de planta por camión/bin (`DOCUMENTARY_TRUCK_FINAL_V1`, ledger derivado, `rejected=NULL` hasta cierre explícito), equipos Norte/Sur (`SUPPLY`/`MOVE`/`TRANSPLANT`), parejas/segmentos históricos, **coordinador multi-camión** (sin doble asignación ni solapamiento de líneas) y **`CLOSE_PERSON_DAY`**.<br>**Subfase 3B:** `autorizaciones_operativas`, rol semanal, descansos/cobertura, **culturales individuales diarios**, captura cosecha vivo/retroactiva + separación movilidad personas vs cajas, revisión de oficina (`captura → cierre técnico → revisión → autorizado → pagable → exportado`), **Prenómina Semanal** (L–S + Domingo + mínimo `$2,350` + cierre inmutable) y Mi Consulta / Cuadro de Honor. | 3A: Piloto real de 2+ camiones simultáneos con 2 supervisores, reconexión tablet y `CLOSE_PERSON_DAY` sin duplicados ni solapes.<br>3B: Piloto offline de cosecha/culturales → revisión oficina → prenómina semanal cuadrada y separada (`IMSS` vs `Especial`), pasando matriz de concurrencia/cierres. |
| **Fase 4** | **Villas, Comedor, Transporte y Planeación Grower (PHVA) Multi-Cultivo** | `villas_hospedaje` + camas (`costo_semanal > 0`), `comedores_config` + `comidas_diarias` conectado a cajas reales, transporte y **documentos operativos** (reglamentos/cartas/inventario habitación/incidencias) trazables a costo sin descontar indebidamente al trabajador. **Planeación Grower + Análisis MO** multi-cultivo (`Frambuesa`, `Fresa`, `Arándano`), cohortes `Long Cane` vs `Primocaña` separadas, geometría parametrizada (incl. **Módulo 1.1**), separación `curva base aprobada / forecast vigente / real`, enfoque **cubrir cajas (no solo plazas)**, dashboard de faltantes 4–5 semanas para RH y `desviaciones_riesgo`. | Plan multi-cultivo versionado por cohorte conectado a avance real de campo, faltantes 4–5 semanas visibles en RH/Dirección y costos reales de villas/comedor/transporte en reportes. |
| **Fase 5** | **Área Técnica (por Cultivo), Agroquímicos, Riego e Inocuidad/Calidad (Transversal)** | Catálogo agroquímicos + verificación automática (+10% dosis, inactivo, precosecha) + bloqueo fitosanitario automático en lotes (sin inferir bloqueo de pago al trabajador por inocuidad), monitoreo técnico (`observación → revisión humana → aplicación autorizada → evidencia`), recetas y mediciones de riego (pH/EC/drenaje), inocuidad transversal (8 categorías), calidad cosecha/pesado, limpieza de módulos y avance cultural consolidado. | Aplicación con PHI/REI bloquea cosecha en Tablet (online y offline cacheado) con flujo explícito de resolución/liberación sin afectar indebidamente nómina. |
| **Fase 6** | **Comercial Multi-Comercializador, GSP, Postcosecha 7 Etapas, Empaque, Embarques y CxC** | Catálogo presentaciones editable + **receta de empaque** (clamshell/etiqueta/caja/tarima, distinguiendo **propio vs consignado**), multi-comercializador (**Mastronardi, Hortifrut, Crystal Fields**), préstamo de cajas clientes, pronósticos GSP + espejo ±10% + gate `gsp_decision_comercial` (conectando Configuración Comercial con Programa Comercial), Postcosecha 7 etapas (rutas Roja/Gris, preenfriado, cuarto frío + temperaturas, vehículos Isuzu/3.5T y mínimo 1,920 cajas, embarques exportación), pedidos nacionales (`COMERCIAL`) y facturación generando **Cuentas por Cobrar (CxC)** (nunca CxP). | Trazabilidad punta a punta desde caja cosechada hasta pallet/PO embarcado, entrega nacional y cuenta por cobrar generada con conciliación de empaque propio/consignado. |
| **Fase 7** | **Costeo `Merqry`, Dirección BI, Centro de Ayuda, SGC/Consultoría Opcional y Módulo Mantenimiento** | Implementar el modelo completo de **Costeo Merqry (`sql/021`–`022`)**: `costeo_cuentas_merqry`, `costeo_reglas_prorrateo` + detalle (**porcentaje exacto y operativo simultáneos**), `costeo_auxiliar_importado` (hash deduplicación), `costeo_movimientos_clasificados`, `costeo_resultado_cultivo_periodo`, `costeo_observaciones_movimiento`, 14 reportes y **14 controles de riesgo** (prorrateo automático activable vía *feature flag* al aprobar **D18**; prohibido llamar margen neto a subtotales sin indirectos). Dashboard Ejecutivo `NFA`/`BIO`/`GRU` (incl. bajas proyectadas confidenciales **D16**), Centro de Ayuda + glosario SEAH, activación modular opcional de SGC/Consultoría (`sql/020`), y módulo **Mantenimiento** (previo alcance con Dirección). | Costeo real por empresa/cultivo/ciclo/ha/kg/caja conciliado contra auxiliar Merqry en modo solo lectura, tablero ejecutivo validado y apagado controlado de Google Sheets/Apps Script. |

---

## 7. Puntos Abiertos a Validar con Dirección antes de Iniciar Fase 1/2

Tomados de `SEAH_DUDAS_REALES_PENDIENTES.md`, auditoría de `v2`, `rrhh-automation-system` y `HANDOFF_CAMPO_INTEGRAL_2026-11-10.md`:
1. **Producción Apps Script en vivo vs local (`C:\clasp_project`):** confirmar en el editor de Apps Script si existen cambios del 11–13/jul (`buscarPersonaIdPorCurpRfc_`, `config_usuarios.html`, `SEAH_Backend_Parte2.gs`) que deban extraerse antes de migrar datos históricos.
2. **Nomenclatura definitiva de lotes/módulos (Fresa `21/22` vs `B1/B2/B3` y geometría Módulo 1.1):** confirmar códigos definitivos y parámetros físicos (túneles, líneas, metros, densidad) antes de poblar `unidades_operativas`, `localizaciones_fisicas` y `lotes_produccion`.
3. **Candidato interno vs Reingreso:** confirmar si un empleado activo que postula a otra vacante debe tener categoría explícita `INTERNO` distinta de `REINGRESO`.
4. **Regla de Merma/Rezaga y Bono de Calidad:** en `agro-erp-berries-v2` actual existe un bono diario por rezaga `<= 3%` (`bono_calidad_por_unidad`), mientras que en `SEAH_Backend.js` la regla vigente es `merma_max_pct = 7%` (alerta) y el esquema semanal es `$28/caja` L–S + Domingo escalonado (`10` a `$28`, excedente a `$40`) con mínimo semanal `$2,350`. Confirmar si el bono por calidad diario aplica adicionalmente o si prevalece el esquema semanal SEAH.
5. **Orden de ejecución en Fase 3 (Trasplante Multi-Camión 3A vs Cosecha/Prenómina 3B):** confirmar si la prioridad inmediata en campo sigue siendo liberar **Fase 3A (Recepción de camiones/bins y captura de trasplante multi-camión)** antes de **Fase 3B (Cosecha/Prenómina)**, y definir los catálogos reales de unidades de planta (`Grade A`, `Singles`, `plants` vs `canes`, sin conversión implícita).
6. **Activación del Prorrateo de Costeo Merqry (D18) y Porcentaje Activo:** confirmar cuándo se habilita el prorrateo automático en `costeo_reglas_prorrateo` y si los reportes ejecutivos de NFA actual usarán porcentaje **exacto** (`74.26% / 25.74%`) u **operativo** (`75% / 25%`), así como las superficies definitivas del próximo ciclo (`20.9 ha`: NFA 12.8 ha / BIO 8.1 ha).
7. **Fórmula monetaria de Labores Culturales Individuales y Valor Probatorio de `Mi Consulta`:** definir regla pagable para culturales individuales diarios (hoy solo existe pago fijo/avance agregado) y si la conformidad del trabajador (NIP/firma) tendrá valor operativo o probatorio formal.
8. **Alcance del módulo Mantenimiento (Fase 7) y Activación de Módulos Opcionales:** definir activos (maquinaria, vehículos, invernaderos, riego) y si el submódulo de Consultoría/SGC (`sql/020`) vivirá dentro de `agro-erp-berries-v2` o permanecerá en `logos-platform`.

---

## 8. Análisis Cruzado: Aportes y Refinamientos de `rrhh-automation-system` y `campo`

Esta sección documenta lo que aportan de nuevo o refinan los dos repositorios complementarios clonados en WSL (`~/ref_rrhh_automation` y `~/ref_campo`) respecto a lo ya mapeado desde `/mnt/c/clasp_project` y `~/agro-erp-berries-v2`.

### 8.1 Aportes de `~/ref_rrhh_automation` (`Lyonmtz/rrhh-automation-system`)

El repositorio `rrhh-automation-system` es un proyecto funcional real en **Node.js/TypeScript/Express + React 19/Vite 8/Tailwind + PostgreSQL 16 (22 migraciones `sql/001`..`022`) + n8n + Docker MySQL 5.7.44 solo lectura** que resuelve con madurez varias áreas donde `clasp_project` y `v2` eran superficiales o incompletos:

1. **Jerarquía Organizacional Normalizada de 7 Niveles (`sql/001`, `010`, `015`–`019`):**
   - Evoluciona el esquema plano `ranchos → lotes_produccion` (`v2`) hacia una estructura corporativa y multi-industria completa:
     `empresas` (con `tipo_persona`, RFC, razón social legal exacta: `Bio-Orgánicos Saludables, S.P.R. de R.L. de C.V.` y `Natural Fruits of America, S.P.R. de R.L. de C.V.`) → `sucursales` (sede física/fiscal con restricción `UNIQUE` de **una sola matriz por empresa** `es_matriz = true` + `naturaleza_sucursal` + tabla hija `sucursal_funciones` con 18 funciones habilitadas como `produccion`, `rh`, `empaque`, `inocuidad`, `almacen`, `contabilidad`, etc.) → `unidades_operativas` (frentes operativos como ranchos, módulos, empaque) → `areas` (jerárquicas con `id_area_padre` y condicionadas por sucursal/unidad) → `localizaciones_fisicas` (`sql/019`, 19 tipos incluyendo `invernadero`, `tunel`, `camara_fria`, `linea_empaque`, `anden`, `comedor`, `cuarto_bombas`, con **trigger PL/pgSQL `trg_validar_localizacion_fisica_contexto`** que impide inconsistencias empresa/sucursal/unidad) → `puestos` (con `reporta_a_puesto_id` y `perfiles_puesto_versiones`) → `plazas_autorizadas`.
2. **Gobernanza Pre-Vacante centrada en la Plaza Autorizada (`sql/010`–`011`):**
   - Introduce entidades ausentes tanto en `clasp_project` como en `v2`: `plazas_autorizadas`, `levantamientos_perfil`, `perfiles_puesto_versiones`, `solicitudes_cobertura`, `aprobaciones_cobertura`, `publicaciones_vacante` y `dictamenes_ingreso_reingreso`.
   - Establece reglas estructurales clave: **la cobertura no crea estructura** (requiere plaza autorizada), **la vacante nace únicamente de una cobertura aprobada**, y **la publicación por canal no redefine la vacante ni el perfil**.
3. **Expediente Digital de 16 Estados, `UPDATE_READY` y Responsivas (`docs/rh-documentos/00..08`):**
   - Refina el onboarding con invariantes estrictos de negocio:
     - `Documento generado != firmado != escaneado != validado`.
     - `Capacitación impartida != validada`.
     - `Alta interna != alta IMSS`.
     - **`LISTO_PARA_TRABAJAR != LISTO_MERQRY != LISTO_PRENOMINA`**.
   - Define 16 estados explícitos de expediente (`BORRADOR → PREALTA → DOCUMENTOS_PENDIENTES → DOCUMENTOS_CARGADOS / OBSERVADOS → DOCUMENTOS_VALIDADOS → CONTRATO_GENERADO → CONTRATO_FIRMADO → CAPACITACION_PENDIENTE → CAPACITACION_COMPLETA → LISTO_PARA_TRABAJAR → LISTO_MERQRY → LISTO_PRENOMINA → ACTIVO → BAJA → ARCHIVADO`).
   - Diseña la bandeja **`UPDATE_READY`** para autorizaciones ágiles en 3 niveles (*validación rápida*, *validación crítica* y *excepción operativa temporal* con motivo, responsable, fecha límite, autorizador y bloqueo futuro automático si vence sin resolverse), siempre con usuario individual, rol, PIN/firma digital y bitácora.
   - Regla legal explícita: **NUNCA generar "renuncia anticipada" pre-firmada** como documento estándar.
   - Cataloga **responsivas operativas** por criticidad (`Uniforme`, `EPP`, `Herramienta`, `Equipo`, `Vehículo`, `Fondo`) —donde EPP crítico bloquea `LISTO_PARA_TRABAJAR` y no se automatizan descuentos sin autorización— y **documentos operativos de villas, comedor y transporte** (`Carta hospedaje`, `Reglamento villas`, `Inventario habitación`, `Reglamento comedor`, `Carta transporte/rutas`, `Reportes de incidencia`).
4. **Capas Transversales de Documentos y Nomenclatura/QR (`sql/015` y `docs/diseno/03_nomenclatura_codigos_qr_versiones.md`):**
   - **`documentos_entidad` + `catalogo_tipos_documento`:** gestor documental polimórfico por `(tipo_entidad, id_entidad)` para empresas, sucursales, personas, activos y procesos, prohibiendo guardar binarios dentro de tablas maestras.
   - **`codigos_alternativos` y estándar QR:** soporta claves de terceros (ERP Merqry, cuenta contable, proveedor, serie, placas) separadas de la clave interna `{empresa}-{sucursal}-{unidad}-{tipo}-{consecutivo}`, bajo el principio *"No mezclar clave operativa con cuenta contable"*.
5. **Descubrimiento Real de `Merqry` como ERP Central (MySQL 5.7 Read-Only):**
   - Corrige la visión parcial de `clasp_project` (que trataba a `Merqury` solo como checador/nómina por Excel): **`Merqry` es el ERP central completo** (compras, inventarios, almacenes, RH, nómina, contabilidad, finanzas, CxP, CxC, costos, centros de costo).
   - Documenta e inspecciona un espejo real en Docker MySQL 5.7.44 (`mq_bio_organicos_analisis`, puerto `3307`) con volúmenes verificados: `nominaprevio` (15.5M filas), `nominad` (7.08M), `auxiliar` (5.9M), `invd` (1.24M), `contd` (850K), `contactopersonal`, `personalasiste`, `personalreloj`, `personalasisteretardo`, `personalasisteerror`, `inv`, `articulo`, `almacen`, `prod`, `prodd`, `prodmaterialmov`, `cg`, `cgd`.
   - Documenta errores reales del dump (`spBCTasaIVA`, definer `mq_bioorganicos@%`, `nominacfdicontacto`) y fija la regla de oro: **operación estrictamente SOLO LECTURA sobre Merqry** (flujo `lectura → conciliación → validación → preparación → export/API controlada`, nunca escritura directa sin autorización explícita).
   - Fija la regla contable/laboral de separación total de circuitos: **`IMSS → Merqry`** vs **`Especial (efectivo) → Contabilidad`**.
6. **Módulo Completo de Costeo Merqry y Prorrateo (`sql/021`–`022`, `docs/costeo/00..05`, `src/modules/costeo/`):**
   - Bajo el principio *"Grower sabe qué pasó en campo. Merqry sabe cuánto costó."*, entrega 7 tablas PostgreSQL listas para adoptar: `costeo_cuentas_merqry`, `costeo_reglas_prorrateo`, `costeo_reglas_prorrateo_detalle`, `costeo_auxiliar_importado`, `costeo_movimientos_clasificados`, `costeo_resultado_cultivo_periodo`, `costeo_observaciones_movimiento`.
   - Guarda **simultáneamente porcentaje exacto y porcentaje operativo** en tablas versionadas (nunca hardcodeados):
     - Ciclo actual NFA (10.1 ha: Frambuesa 7.5 ha / Fresa 2.6 ha): exacto `74.26% / 25.74%`, operativo `75% / 25%`.
     - Próximo ciclo NFA + BIO (20.9 ha: NFA Frambuesa 10.2 ha + Fresa 2.6 ha = 12.8 ha; BIO Arándano 8.1 ha): entre empresas `61.24% / 38.76%`, global por cultivo `48.80% / 12.44% / 38.76%`, interno NFA `79.69% / 20.31%`.
   - Incluye **hash de deduplicación** (`hash_origen` sobre `Empresa+Fecha+Modulo+ModuloID+Cuenta+Folio+CentroCostos`), 14 reportes estandarizados (por empresa, cultivo, ha, kg, caja, margen) y **14 controles de riesgo** (cuentas nuevas en `PENDIENTE_CLASIFICACION`, movimientos sin centro de costo en `OBSERVADO`, exclusión de IVA, toggle de depreciación, inmutabilidad de reglas bloqueadas/periodos cerrados, alerta por MO en efectivo fuera de Merqry).
7. **Seguridad Multi-Rol, 4 Niveles de Autorización, Modularidad y PR3 (`sql/008`–`009`, `sql/020`, rama PR3):**
   - Modelo multi-rol (`usuarios_roles`), catálogo de permisos granulares (`roles_permisos`), 4 niveles de autorización configurables (`L1 Jefe inmediato` → `L4 Dirección General`), `bitacora_cambios` y 19 códigos estandarizados de tipos de movimiento RH (`RSC-01..05`, `AP-01..11`, `CC-01..03`).
   - En `sql/020` aporta un submódulo opcional de **Consultoría / SGC / Control de Versiones Documentales** (`consultoria_clientes`, `consultoria_proyectos` con semillas `BIO-001`, `NFA-001`, `GRU-001`, checklists y entregables).
   - En la rama PR3 (`origin/campo/document-preparation-v13-20261108`, 70 archivos, 367 casos sintéticos) introduce la separación entre **puesto nominal Merqry** y **función operativa temporal** (`operational-function-history`), dossier portable/recibo documental y adaptadores de métricas históricas que prohíben fusionar personas por coincidencia de nombre o teléfono.

---

### 8.2 Aportes de `~/ref_campo` (`Lyonmtz/campo`)

Aunque `main` de `campo` es estrictamente documental (gobernanza y fronteras), sus dos ramas de respaldo (`origin/respaldo/handoff-campo-20261110` y `origin/respaldo/captura-trasplante-20261110`) aportan un **dominio operativo completo no cubierto en `clasp_project` ni en `v2`**, además de contratos de ingeniería muy superiores para concurrencia, privacidad y modo offline:

1. **Arquitectura de Autoridad Única y Contrato de Privacidad `RH → Campo` (`ARCHITECTURE.md`):**
   - Impone el patrón **Cliente Campo → Fachada Autenticada → Servicio Canónico → Acuse Versionado**: cero acceso directo del cliente a tablas, cero escritores paralelos y actor/autoridad resueltos **siempre en el servidor** (nunca enviados ni confiados desde la tablet).
   - Define el contrato mínimo **`DailyEligibleWorker.v0.1`**: Campo recibe únicamente identidad canónica (`person_id`, `employee_id`), ámbito (`empresa/sucursal/unidad`), vigencia, elegibilidad diaria y operaciones autorizadas; **excluye salarios, expediente, CURP/RFC/NSS, datos fiscales e historial disciplinario**. Regla crítica: *"Un snapshot offline vencido no concede autorización indefinida."*
2. **Separación Estricta de Estados de Negocio y Flujos Paralelos (`HANDOFF_CAMPO_INTEGRAL_2026-11-10.md`):**
   - Separa 7 estados que el legado confundía: **`captura → cómputo → revisión → autorización → pagable → exportación → recepción del consumidor`**. Ni la captura ni el cierre técnico equivalen a cierre global, aprobación de oficina o pagabilidad.
   - Separa explícitamente **movilidad de personas** (`entrega → salida → traslado autorizado → nueva asignación`) de **traslado de cajas/bins** (`recolección parcial → traslado → recepción empaque → empacado → despacho`), porque la recolección no depende de que el trabajador cambie de módulo.
3. **Protocolo Endurecido de Idempotencia, Recuperación de ACK Perdido y Fencing Durable (`transplant-conflict-review`):**
   - Supera el diseño básico `ON CONFLICT DO NOTHING` con 4 reglas obligatorias:
     1. Reintento con misma `commandId` y **mismo payload** → devuelve `200` con el comprobante persistido original (`committed.ack`), recuperando ACKs perdidos sin duplicar efectos ni depender de un re-POST ciego.
     2. Reintento con misma `commandId` y **payload distinto** → **DEBE devolver `409 Conflict`** (nunca ignorar silenciosamente).
     3. Distinguir `ABSENCE_OBSERVED` de `NOT_APPLIED_VERIFIED` cuando un comando no se encuentra tras fallo de red.
     4. **`DURABLE_COMMAND_FENCE`:** permitir cercar/anular de forma durable una `commandId` pendiente dentro de la misma transacción bloqueada para que una entrega tardía desde una tablet offline sea rechazada explícitamente con `COMMAND_FENCED_NOT_APPLIED`.
   - Define una **matriz mínima de aceptación en base desechable verificada** (las suites de prueba nunca deben asumir que una DB es desechable solo por su nombre): reintentos secuenciales/concurrentes, ACK perdido, payload distinto 409, aislamiento empresa/sitio/rol, elegibilidad cambiante tras asignación, captura concurrente con cierre, cierre global (unidad `NULL`) frente a cierre por unidad, y dos cierres globales simultáneos.
4. **Dominio Nuevo de Alta Prioridad: Programación de Llegadas, Recepción por Camión/Bin y Trasplante Multi-Camión (`capture/lab/transplant-bin-v2` + `transplant-planning`):**
   - **Programación previa de llegadas (`transplant-planning`):** registra arribos documentales (`Grade A`, `Singles`, `plants` vs `canes`) conservando unidades y fuentes corroborantes separadas sin sumarlas ni aplicar factores implícitos (ej. no asumir `Grade A = 2`), manteniendo los conteos físicos/rechazos como `NULL` (desconocidos) hasta la recepción real. Editar el plan invalida su mapeo al lote de recepción; nunca promueve datos documentales a stock operativo.
   - **Recepción documental-física (`DOCUMENTARY_TRUCK_FINAL_V1`):** máquina de estados `DECLARE_TRUCK` (`verified: false`, no crea stock) → `BIN_RECEIVE` (conteo físico por bin) → `BIN_RELEASE` (liberación explícita a disponible) → `FINISH_TRUCK` (señal gerencial) → `FINALIZE_RECEIPT` (conciliación total del camión `accepted + rejected = received`, auditoría inmutable). **El rechazo permanece `NULL` hasta el cierre explícito** (cero auto-merma ni conversión silenciosa de diferencias en rechazo).
   - **Ledger Derivado como Única Fuente de Verdad:** el stock disponible se calcula estrictamente desde `binLedger` y `transplants` (sin contadores mutables paralelos), exigiendo `binId` y unidad exacta en cada movimiento.
   - **Operación por Equipos Norte/Sur y Segmentos Históricos:** corrige la división anterior "afuera/adentro": cada equipo (Norte y Sur) abastece y trasplanta su propio lado con 3 funciones explícitas (`SUPPLY`: llenado de carritos, `MOVE`: traslado de carritos, `TRANSPLANT`: trasplante de planta). Calcula **minutos activos de asignación** separados de **minutos de participación reales** por segmento (`segment.functionCode` y `segment.participantIds`), sin multiplicar la producción compartida de una pareja por el número de integrantes y preservando huecos/cambios/relevos/pausas sin sobrescribir historial.
   - **Coordinador Multi-Camión Compartido (`SHARED-TRUCKS`, QA 11/11 PASS):** permite recibir y descargar **2+ camiones simultáneamente** incluso alimentando un mismo módulo compartido (conservando trazabilidad `lote/bin/módulo`), bloqueando bajo la misma transacción:
     - Doble reserva simultánea de una persona entre camiones (`ASSIGNED`/`RUNNING`/`PAUSED`, sin revelar en el error el trabajo del otro lote).
     - Solapamiento físico de `(scope, moduleId, tunnelId, side, rango de líneas)` para `TRANSPLANT`, permitiendo coexistencia de labores distintas como `Clips` o `Barrer` sin que puedan apropiarse del rango de trasplante vía `CHANGE`.
     - Continuación explícita entre camiones/días (`crossBatchContinuationOf`: Camión A → Camión B → Día siguiente) exigiendo origen `FINISHED`, subrango pendiente y preservando inmutables comprobantes previos.
   - **Cierre Individual Persona-Día (`CLOSE_PERSON_DAY`):** exige `reviewToken` fresco atado a actor/alcance/revisiones; bloquea si quedan asignaciones abiertas, temporizadores corriendo o alcance de supervisor incompleto (`PERSON_DAY_SCOPE_INCOMPLETE`, derivable a gerencia); certifica únicamente el lote y fecha revisados (distinto del cierre global `CLOSE_DAY` y distinto de nómina).
5. **Refinamientos Transversales de Producto (Culturales, Curvas, Comercial, Inocuidad y Evidencia):**
   - **Labores culturales individuales diarias:** identifica explícitamente la brecha del legado (que solo guardaba `%` agregado por módulo/semana/labor) y exige captura diaria individual con unidad, meta, cantidad, intervalos, pausas y revisión.
   - **Curvas y capacidad:** el objetivo es **cubrir cajas (no solo plazas)**; `Long Cane` y `Primocaña` son cohortes no intercambiables; separar `curva base aprobada / forecast vigente / real`; parametrizar geometría propia para el **Módulo 1.1**; tablero de faltantes de las próximas 4–5 semanas orientado a RH y consumido por Dirección.
   - **Comercial y CxC:** ampliar el modelo a **multi-comercializador** (Mastronardi, Hortifrut, Crystal Fields), separar **empaque propio/comprado vs consignado** con receta de componentes (clamshell, etiqueta, caja, tarima), conectar Configuración Comercial con Programa Comercial, y fijar la corrección explícita del usuario: **venta/facturación genera Cuenta por Cobrar (CxC), NO Cuenta por Pagar**.
   - **Inocuidad y costos:** no inferir bloqueo de pago al trabajador por hallazgos de inocuidad; no llamar "margen neto" a un subtotal que excluya indirectos.
   - **Escala de evidencia de 8 niveles:** exigir trazabilidad explícita entre *1. Requisito → 2. Fuente leída → 3. Código presente → 4. Prueba sintética → 5. Interfaz observada → 6. Persistencia/reconexión → 7. Despliegue → 8. Aceptación en rancho*.

---

## 9. Matriz de Diferencias y Contradicciones entre los 4 Repositorios y Referencia Recomendada

| # | Dimensión | `agro-erp-berries-v2` (Actual) | `/mnt/c/clasp_project` (SEAH Legado) | `rrhh-automation-system` | `campo` (`main` + respaldos) | Fuente de Referencia Recomendada para `v2` |
|---|---|---|---|---|---|---|
| **1** | **Stack y Plataforma Canónica** | Python 3.12 + FastAPI + PostgreSQL 16 (`agro_berries_erp`) + SPA HTML | Google Apps Script + Google Sheets (83 pestañas) + 57 HTML | Node/TS/Express + React 19/Vite 8/TS/Tailwind + PostgreSQL 16 (DB `n8n`) + n8n | Propone cliente Campo → fachada → backend `logos-platform` (TS/Postgres), API hoy solo `/health` | **Plataforma destino: `agro-erp-berries-v2` (FastAPI + PostgreSQL 16 + React/Vite/TS PWA)**, absorbiendo el modelo SQL normalizado de `rrhh-automation-system` y los contratos de fachada/invariantes de `campo`. No mezclar con la DB `n8n` ni duplicar un segundo padrón. |
| **2** | **Alcance y Grafía de `Merqry`** | No modelado aún | Llamado `Merqury`; tratado solo como checador/nómina vía Excel/CSV | **Nombre estándar `Merqry`**: ERP central completo en MySQL 5.7 (`auxiliar`, `nominaprevio`, `inv`, `prod`, etc.), **solo lectura**, separación estricta `IMSS → Merqry` vs `Especial → Contabilidad` | Confirma lectura controlada, `MerQry` solo para puestos nominales/nómina, sin escritura directa ni mezcla de circuitos | **Tomar `rrhh-automation-system`:** usar grafía `Merqry`, conector/staging **read-only** sobre MySQL 5.7 (o export validado) y separación estricta `IMSS → Merqry` vs `Especial → Contabilidad`. |
| **3** | **Jerarquía Organizacional y Lotes** | 2 niveles: `ranchos → lotes_produccion` + `departamentos` | `NFA`/`BIO` + módulos (`1..11`, `B1..B3`) y `padron_maestro` | 7 niveles (`empresas → sucursales + sucursal_funciones → unidades_operativas → areas → localizaciones_fisicas → puestos → plazas_autorizadas`) con trigger de contexto (`sql/019`) | Exige `tenant/empresa/sitio/unidad`, geometría propia para **Módulo 1.1** y no equiparar IDs externos por nombre | **Tomar `rrhh-automation-system` (`sql/010`–`019`) + especialización agrícola de `v2`/`campo`:** adoptar la jerarquía completa de 7 niveles y vincular `lotes_produccion` (con geometría parametrizable incl. Módulo 1.1) a `unidades_operativas` y `localizaciones_fisicas`. |
| **4** | **Reclutamiento, Plazas y Expediente RH** | 7 estados simples en `candidatos`, `acuses_digitales` sin poblar | 5 etapas + 9 estados persona, portal cosecha vs general, ranking 60/25/15, beneficiarios Art. 501, finiquito LFT 2026 | `plazas_autorizadas → cobertura → aprobación → vacante → publicación`, **16 estados de expediente**, `UPDATE_READY` (excepciones con bloqueo futuro), responsivas, **prohibida renuncia anticipada** | Pide formulario progresivo en lenguaje simple de campo, conciliación de ya contratados sin re-reclutar, sin fusionar personas por nombre | **Combinar `rrhh-automation-system` (estructura y gobernanza) + `clasp_project` (reglas operativas):** adoptar plazas, cobertura, 16 estados, `UPDATE_READY`, responsivas y prohibición legal de `rrhh`, conservando ranking 60/25/15, portal cosecha, beneficiarios Art. 501 y cálculo LFT 2026 de `clasp_project`. |
| **5** | **Puesto Nominal vs Función del Día** | Un solo `puesto_id` en `empleados` | Puesto/rol único (aunque permite asignaciones diarias por módulo) | PR3 (`operational-function-history`): separa puesto nominal de función temporal con historial y retorno | Regla explícita: **nunca sobrescribir puesto nominal Merqry** con función temporal (jornalero/supervisor/pesador) ni mutar RBAC/empleo | **Tomar `campo` + `rrhh` PR3:** conservar `relaciones_laborales.puesto_id` (nominal) intacto y agregar tabla `funciones_operativas_temporales` con vigencia, motivo, autorizador y retorno. |
| **6** | **Frontera de Privacidad `RH → Campo`** | Acceso directo a tablas `empleados` y `prenomina` | Hojas compartidas; riesgo de exposición de datos sensibles | Expediente completo en RH; PR3 inicia separación | Contrato **`DailyEligibleWorker.v0.1`**: Campo recibe solo elegibilidad diaria y alcance; **cero salarios/expediente/CURP/RFC/NSS**, con TTL explícito | **Tomar `campo`:** exponer desde el módulo `personal` hacia `operacion_campo`/`cosecha_tablet`/`trasplante_recepcion` un servicio/vista de elegibilidad mínima diaria con expiración estricta. |
| **7** | **Pagos, Destajo, Calidad y Merma** | Diario `MIXTO_GARANTIA` + bono calidad `<= 3%` (`pagos_service.py`) | Semanal `$28/caja` L–S + Domingo escalonado (`$28/$40`) + mínimo `$2,350` + alerta merma `7%` + comidas/villas no descontables | Sin motor de destajo de campo; enfocado en incidencias de prenómina (`sql/004`) | Separa `captura → cierre técnico → revisión → autorización → pagable → exportado`; prohíbe convertir diferencias en merma/rechazo automático; laborales culturales diarias aún sin fórmula monetaria aprobada | **Tomar `clasp_project` para fórmulas configurables de cosecha + `campo` para máquina de estados y no-auto-merma:** parametrizar tarifas en DB (validando con Dirección si coexiste el bono `<= 3%` de `v2`), nunca marcar como pagable automáticamente al cerrar captura técnica. |
| **8** | **Trasplante y Recepción de Planta** | No existe | Solo fechas estáticas de trasplante en Planeación | Demo básica `/rh/demo/recepcion` en memoria (PR3) | Laboratorio V2 completo (`DOCUMENTARY_TRUCK_FINAL_V1`, programación previa, bins, ledger derivado, Norte/Sur, parejas/segmentos, **coordinador multi-camión** 11/11 PASS, `CLOSE_PERSON_DAY`) | **Tomar `campo` (`respaldo/captura-trasplante-20261110`):** portar su dominio y reglas exactas a tablas PostgreSQL transaccionales y endpoints FastAPI como **Fase 3A**. |
| **9** | **Modo Offline, Idempotencia y Conflictos** | Sin offline ni outbox | `localStorage` (~5MB) + retry 60s; riesgo de pérdida y duplicados | PR3 prepara outbox IndexedDB probado con dobles (no navegador real) | Exige **IndexedDB real**, `commandId` previo al primer envío, **`409 Conflict` si cambia payload**, **`committed.ack`** para ACK perdido, **`DURABLE_COMMAND_FENCE`** y `ABSENCE_OBSERVED` | **Tomar `campo`:** sustituir el `ON CONFLICT DO NOTHING` ingenuo del diseño inicial por verificación de hash de payload (`200` + `committed.ack` vs `409 Conflict`) + tabla de fencing transaccional + Dexie.js (IndexedDB real). |
| **10** | **Costeo y Prorrateo** | Vista `vw_direccion_rentabilidad_cultivo` rota (duplica prenómina en cada cultivo) | Bloqueado por **D18** (sin prorrateo automático aún) | **Módulo implementado (`sql/021`–`022`)**: 7 tablas, porcentajes exacto y operativo simultáneos, hash de auxiliar, 14 reportes y 14 controles | Exige conservar fórmulas/monedas, **no llamar margen neto a subtotales sin indirectos**, y registrar ventas como **CxC** | **Tomar `rrhh-automation-system` (`sql/021`–`022`) + controles de `campo`:** construir la estructura completa en PostgreSQL y controlar la activación automática del prorrateo mediante *feature flag* sujeto a aprobación formal **D18**. |
| **11** | **Seguridad, Roles y Autorizaciones** | Sin autenticación ni RBAC | Contraseñas texto plano, matriz solo visual en menú, PINs en claro | Tablas `usuarios`, `roles`, `usuarios_roles`, `permisos`, `roles_permisos` y 4 niveles de autorización (`sql/008`–`009`), pero backend Express aún sin auth en runtime | Exige sesión/CSRF real, actor y **alcance `(empresa, sucursal, unidad, rol)` resueltos en servidor**, sin auto-confianza del cliente | **Combinar `rrhh-automation-system` + `campo` + `v2`:** modelo multi-rol y 4 niveles de `rrhh`, enforcement por alcance en cada endpoint FastAPI (`campo`), contraseñas/PINs/NIPs hasheados con `bcrypt` y JWT/sesión segura. |
| **12** | **Comercial, Empaque y Curvas** | Solo 3 cultivos básicos | Flujo 7 etapas postcosecha, rutas Roja/Gris, Isuzu/3.5T, GSP Mastronardi, pedidos nacionales (`COMERCIAL`), préstamo cajas Fresa | No cubre operación comercial agrícola | Multi-comercializador (Mastronardi/Hortifrut/Crystal Fields), receta de empaque (**propio vs consignado**), **CxC explícita**, cohortes `Long Cane`/`Primocaña`, cubrir cajas y Módulo 1.1 | **Combinar `clasp_project` + `campo`:** conservar la operación concreta de postcosecha/GSP/pedidos nacionales de `clasp_project` generalizando a multi-comercializador, receta de empaque propio/consignado, CxC y cohortes de `campo`. |

---

## 10. Ajustes Recomendados al Plan de Fases (Fase 0 a Fase 7) antes de Escribir Código

Antes de generar cualquier archivo SQL, FastAPI o Frontend en `~/agro-erp-berries-v2`, se recomiendan los siguientes ajustes concretos al plan original de fases:

### 10.1 Reglas Transversales de Ejecución (Aplican a TODAS las Fases)
1. **Guarda de Base Desechable Verificada (de `campo`):** toda suite automatizada (`pytest`) que limpie/recree esquemas debe exigir una bandera explícita de entorno (ej. `ALLOW_DESTRUCTIVE_TEST_DB=true` + tabla/metadato `db_environment = 'DISPOSABLE_TEST'`) y nunca inferir desechabilidad solo por el nombre de la base.
2. **Escala de Evidencia de 8 Niveles (de `campo`):** ninguna fase se marcará como "terminada" por tener SQL o pruebas unitarias; registrar siempre estado exacto (`Requisito → Fuente → Código → Prueba sintética → UI observada → Persistencia/reconexión → Despliegue → Aceptación en rancho`).
3. **Respeto Estricto a `REUSE_FIRST` y Solo Lectura en `Merqry`:** ninguna migración de `v2` toca MySQL de `Merqry`, ni la DB `n8n` de `rrhh-automation-system`, ni `~/agro-erp-berries`.

### 10.2 Deltas Concretos por Fase

- **Fase 0 (Estabilización Base de `v2`):**
  - **Añadir:** configuración de base de pruebas desechable verificada en `pytest/conftest.py`, estandarización del nombre `merqry` en módulos/variables, y creación del archivo `00_extensions.sql` + estructura Alembic limpia que reemplace los 4 scripts rotos.
- **Fase 1 (Núcleo Organizacional, Seguridad y Identidad):**
  - **Reemplazar/Enriquecer:** en lugar de solo `empresas` + `ranchos` + `lotes_produccion`, incorporar desde el día 1 el núcleo probado de `rrhh-automation-system` (`sql/010`, `015`, `016`, `019`): `sucursales` (1 matriz única por empresa), `sucursal_funciones`, `unidades_operativas`, `areas`, `localizaciones_fisicas` (con su trigger de consistencia de contexto), `catalogo_tipos_documento`, `documentos_entidad` y `codigos_alternativos` (QR/claves externas).
  - **Añadir en Seguridad:** modelo multi-rol (`usuarios_roles`, `roles_permisos`) + `niveles_autorizacion` (L1–L4) + filtro obligatorio en FastAPI por alcance `(empresa_id, sucursal_id, unidad_operativa_id)` para que un permiso acotado a un sitio nunca autorice escrituras a nivel empresa.
  - **Añadir en Identidad:** tabla `funciones_operativas_temporales` (separada de `relaciones_laborales`) y regla ETL de cuarentena para conflictos de nombre/teléfono (cero fusiones automáticas).
- **Fase 2 (RH Completo + Conciliación `Merqry`):**
  - **Enriquecer Reclutamiento:** anteponer `plazas_autorizadas`, `levantamientos_perfil`, `perfiles_puesto_versiones`, `solicitudes_cobertura`, `aprobaciones_cobertura`, `publicaciones_vacante` y `dictamenes_ingreso_reingreso` antes de `vacantes` (manteniendo compatibilidad con el portal cosecha y el ranking 60/25/15 de `clasp_project`).
  - **Enriquecer Expediente:** implementar los **16 estados de expediente**, la bandeja **`UPDATE_READY`** (validación rápida, crítica y excepción temporal con vencimiento/bloqueo), la tabla de **responsivas** (uniforme/EPP/herramienta/equipo/vehículo/fondo) y bloquear a nivel de dominio cualquier plantilla de "renuncia anticipada".
  - **Refinar Integración `Merqry`:** además de import/export Excel/CSV, agregar un servicio/adaptador **READ-ONLY** hacia MySQL 5.7 (`mq_bio_organicos_analisis` o réplica autorizada) y etiquetar explícitamente cada empleado/relación con su circuito de pago (**`IMSS_MERQRY`** vs **`ESPECIAL_CONTABILIDAD`**).
- **Fase 3 (Operación de Campo Offline-First — Dividida en 3A y 3B):**
  - **Endurecer el motor Offline/Sync ANTES de construir pantallas:**
    - Reemplazar `sync_outbox_log` simplificado por un protocolo completo: `client_command_id UUID PK` + `payload_sha256` + `committed_ack_json JSONB` + tabla `sync_command_fences` (fencing durable en la misma transacción). Reglas: mismo hash → devuelve `committed_ack_json` (`200`), hash distinto → **`409 Conflict`**, comando cercado → **`COMMAND_FENCED_NOT_APPLIED`**.
    - Implementar la proyección mínima **`GET /api/v1/campo/eligibility/daily`** (`DailyEligibleWorker.v0.1`) con TTL obligatorio, excluyendo salarios/expediente.
  - **Insertar Subfase 3A (Trasplante & Recepción Multi-Camión — Prioridad Operativa Inmediata):**
    - Tablas PostgreSQL: `trasplante_programacion_llegadas`, `trasplante_camiones_lotes`, `trasplante_bins_ledger`, `trasplante_asignaciones`, `trasplante_segmentos_tiempo`, `trasplante_produccion_lineas`, `trasplante_cierres_persona_dia`, con índices/bloqueos transaccionales que garanticen en PostgreSQL multiusuario las mismas 11 invariantes del coordinador multi-camión (`SHARED-TRUCKS`) y `DOCUMENTARY_TRUCK_FINAL_V1` (`rejected = NULL` hasta `FINALIZE_RECEIPT`).
  - **Refinar Subfase 3B (Cosecha, Culturales y Prenómina):**
    - Agregar **captura diaria individual de labores culturales** (cerrando la brecha del legado).
    - Separar explícitamente endpoints/tablas de **movilidad de personas** vs **traslado de cajas**.
    - Separar la máquina de estados de prenómina (`CAPTURADA → CIERRE_TECNICO → EN_REVISION → AUTORIZADA → PAGABLE → EXPORTADA → RECIBIDA`) y agregar pruebas automatizadas obligatorias para los casos de concurrencia de `campo` (cierre global vs unidad, doble cierre simultáneo, captura simultánea a cierre).
- **Fase 4 (Villas, Comedor, Transporte y Planeación Grower):**
  - **Añadir en Servicios:** gestión de **documentos operativos** (cartas de hospedaje/transporte, reglamentos firmados, inventario de habitación, incidencias) vía `documentos_entidad` y enlace a costos por cuadrilla/módulo sin descuento automático.
  - **Refinar Planeación Grower:** separar explícitamente `curva_base_aprobada`, `forecast_vigente` y `avance_real`, distinguir cohortes **`Long Cane`** vs **`Primocaña`** por cultivo, cargar geometría específica del **Módulo 1.1**, y exponer el **tablero de faltantes 4–5 semanas** orientado a RH para cubrir **cajas** (no solo cabezas).
- **Fase 5 (Área Técnica, Agroquímicos, Riego e Inocuidad):**
  - **Añadir candado de dominio (de `campo`):** flujo formal `observación técnica → revisión humana → aplicación autorizada → evidencia/liberación` con responsable explícito de cierre de hallazgos, y garantía de que un bloqueo de inocuidad/PHI **nunca bloquea ni descuenta automáticamente el pago del trabajador**.
- **Fase 6 (Comercial, GSP, Postcosecha y Embarques):**
  - **Generalizar Comercial:** tabla `comercializadores` (Mastronardi, Hortifrut, Crystal Fields, etc.), `empaque_recetas` con bandera **`origen_empaque` (`PROPIO` | `CONSIGNADO`)** y conciliación de mermas/daños/devoluciones de empaque.
  - **Corregir Integración y Flujo Financiero:** unificar `Configuración Comercial` con `Programa Comercial` sobre las mismas tablas PostgreSQL, y modelar la facturación de embarques/pedidos nacionales generando **`cuentas_por_cobrar` (CxC)** (nunca CxP).
- **Fase 7 (Costeo `Merqry`, Dirección BI, Ayuda y Mantenimiento):**
  - **Adelantar diseño de tablas de Costeo (`sql/021`–`022`):** crear las 7 tablas `costeo_*` desde el modelo oficial de `rrhh-automation-system` (con doble porcentaje exacto/operativo, `hash_origen`, 14 controles de riesgo y bloqueo de periodos cerrados), dejando el prorrateo automático detrás de un *feature flag* hasta aprobación **D18** y etiquetando claramente cualquier subtotal sin indirectos para no llamarlo "margen neto".
  - **Mantener opcional/desacoplado:** activar el submódulo SGC/Consultoría (`sql/020`) solo mediante la tabla de configuración modular por empresa, junto con el módulo Mantenimiento una vez aprobado su alcance.


---

## 11. Inventario Documental y Operativo Local (Downloads, Documents, `datos_privados_rrhh` y WSL `~/proyectos`) y Consolidación de Hallazgos para Fase 0 / Opción B

> **Fecha de barrido e indexación:** 2026-11-21 (modo estrictamente solo lectura sobre fuentes locales; `~/agro-erp-berries` intacto; `Merqry` MySQL solo lectura).  
> **Universo auditado:** 3,071 archivos en `C:\Users\geren\Downloads` (sin carpeta `~/Downloads` en WSL) + `C:\Users\geren\Documents\Campo_*` + `C:\Users\geren\datos_privados_rrhh\base_conocimiento_rh` + `~/proyectos/Sistema integral operativo y administrativo conectado a erp`, excluyendo empresas no relacionadas (DAMOR, Diamond, CARBU, Oxxo, Nesdam) y trámites fiscales SAT/DIOT puros.  
> **Secuencia confirmada:** **Opción B** (`Fase 0 → Fase 1 → Fase 3A Trasplante Multi-Camión → Fase 2 → Fase 3B`).

### 11.1 Inventario Estructurado de Fuentes Útiles por Dominio del ERP

| Dominio / Módulo ERP | Rutas / Archivos Clave Encontrados | Tipo | Resumen de Datos, Reglas o Artefactos Clave |
|---|---|---|---|
| **1. Planta, Variedades, Densidades y Trasplante Multi-Camión (Fase 0 / 3A)** | `Downloads/260100_Natural_Fruits_of_America_DJ_LC_-_Nov (2).pdf`<br>`Downloads/NAT-TRASPLANTE CON DESFASES FRAMBUESA_PROPUESTA_REVISION_2026-11-09.xlsx`<br>`Downloads/PROPUESTA DE TRASPLANTE CAÑA LARGA 2026-2027 brenda 121026.xlsx`<br>`Downloads/PLANTA 2026 0926.xlsx` · `PLANTA GLOBAL 2022-2026  V2.xlsx` · `SALDO DE PLANTA 3 AÑOS CONSIDERANDO DESCUENTOS 14092026.xlsx`<br>`Downloads/MACETA 7 LT FRAMBUESA FTP025 (2).pdf` · `sustrato nfa 2.xlsx`<br>`Downloads/rrhh para revisar/Subidos/1. Requerimientos frambuesa para mod 2.7.xlsx`<br>`Downloads/rrhh para revisar/2. Requerimientos arandano.xlsx`<br>`Downloads/docs berries 2026/FRAMBUESA 2024-2025/TRANSPLANTE.xlsx` · `FRESA CICLO 2024-2025/AVANCE TRANSPLANTE.xlsx` | PDF firmado DocuSign, XLSX, Ficha técnica | **Orden MPL #260100 firmada por Luis (02/11/2026):** Raspberry variedad **`DJ`** (*Diamond Jubilee*), **`Long Cane`**, `10.2 ha`, **`208,000` plantas** a `$3.50 USD` (`$728,000 USD`), devolución obligatoria de cajas/bins plásticos al propagador. Plan multi-camión (10 camiones × `20,800` plantas; `26 bins × 800` o `24 × 702` según vivero). Histórico de merma distingue **1ª merma (planta rota)** y **2ª merma (sin brotación)** (`4.36%`–`9.43%`). Maceta cuadrada INVECO FTP-025 de **7 L** (1,350 pzas/pallet). Kardex de saldo/sobreprecio de planta (escala 80k–120k cajas de `$2.00` a `$3.50 USD/caña`), fletes e importación (SENASICA/DAF). |
| **2. Estructura de Invernaderos, Geometría y Curvas (Fase 0 / 4)** | `datos_privados_rrhh/base_conocimiento_rh/v0_1/salidas/GROWER_MODULOS_CATALOGO_v0_1.xlsx` · `CURVAS_COSECHA_BASE.xlsx`<br>`Downloads/Handoff_Campo_Arandano_Cosecha_RH_2026-11-18.md`<br>`Downloads/Forecast azra blue.xlsx` · `Proyección frambuesa caña larga 2027 v2.xlsx`<br>`Downloads/rrhh para revisar/Proyección fresa 2da cosecha 2026.xlsx`<br>`Documents/Campo_Curvas_v1_20261109/` · `Campo_Conciliacion_20261109/MATRIZ_UNICA_CAMPO_20261109.md`<br>`Downloads/proyecto inv 11 al 14/3.0  PLANO INVERNADERO BATICENITAL C96.pdf` · `COT 106-2026 BIO-ORGANICOS (BATICENITAL 960).pdf` | XLSX, MD, PDF, Planos | **Geometría confirmada M1–M11** (*Manual Integral Berries*): M1–M8 = `7,680 m²` (`0.768 ha`), `40` líneas (`3,040 m`), `174` macetas/línea (`83 N / 91 S`) = `6,960` macetas / `13,920` cañas; M9–M11 = `6,912 m²` (`0.6912 ha`), `36` líneas (`2,736 m`), `6,264` macetas / `12,528` cañas (`148,944` total M1–M11). M1.1: `65` líneas, `78,030` goteros (`26,010` vs `26,520` macetas). Arándano `AzraBlue`: `60,750` plantas en 3 módulos de 2.7 ha (`7,500 pl/ha` = `20,250`/mód vs `8,333 pl/ha`), trasplante S26 (`M2.1`) y S29 (`M2.2`), 22 sem vegetativo. Reglas V3 del handoff 18/11/2026: no unificar curvas de origen distinto (`119.2 t` Excel vs `76 t` oral), fresa = `18,009.93` cajas. |
| **3. Manuales, POEs/SOPs, Políticas y Reglamentos (Fase 1 / 2 / 4 / 5)** | `Downloads/rrhh para revisar/Subidos/NFA_ABR-2026_MANUAL_INTEGRAL_DE_OPERACIÓN_BERRIS_FINAL.pdf`<br>`Downloads/Guia_de_arandano_para_Brenda.pdf` (41 págs, 01/10/2026)<br>`Downloads/NAT-PR-PRO-004-PROCEDIMIENTO POLINIZACIÓN EN FRAMBUESA.docx`<br>`Downloads/NAT-PR-PRO-007-MANEJO INTEGRADO DE ENFERMEDADES EN BERRIES.docx`<br>`Downloads/POL-RH-VAC-001_v1.0.docx` · `ESP-FUN-RH-VAC-001_v1.0.md` · `CONTRATO-MVP-RH-VAC-001_v1.0.docx`<br>`Downloads/Procedimiento para la Revisión y Validación de Corte.docx` · `Procedimiento estimacion.docx` · `Procedimiento Estimación Semanal de Pagos.pdf`<br>`Downloads/PASOS PARA SUBIR CORTE A MERQRY.docx`<br>`Downloads/rrhh para revisar/Subidos/2025/REGLAMENTO DEL COMEDOR.docx` · `REGLAMENTO_VILLAS_MANUAL_NFA ELABORADO POR EL LIC MARTINEZ.docx`<br>`Downloads/Manual integral frambuesas_files.zip` · `Entrega_Campo_Rancho_2026-11-11_v4.zip` | PDF, DOCX, MD, ZIP | Manual operativo maestro de Berries NFA; guía técnica de `AzraBlue (FCM14-031)` en bolsas 30 L coco (28 perf.: 16 sup., 12 inf.) con separación estricta entre observación, hipótesis, diagnóstico y autorización; POEs de polinización (*Diamond Jubilee*) y manejo integrado de enfermedades; política corporativa de vacaciones/permisos (`POL-RH-VAC-001`); procedimientos de validación de cortes y carga a `Merqry`; reglamentos oficiales de comedor y villas. |
| **4. RH, Organigramas, Perfiles de Puesto, Evaluaciones y Nómina (Fase 1 / 2 / 3B)** | `Downloads/rrhh para revisar/Subidos/ORGANIGRAMA Y TABULADOR_RESPALDO.xlsx` · `ESTRUCTURA ORGANIZACIONAL.xlsx` · `BASE PUESTOS JUNIO 2025.xlsx` · `Matriz de Capacitación.xlsx`<br>`Downloads/rrhh para revisar/Subidos/NFA_Pendiente_Clasificar_2026-04-13_NAT-MO-RH-000 PERFIL DE PUESTO DE JEFE DE MANO DE OBRA 2024.xlsx`<br>`Downloads/Organigrama Operativo Grower pdf.pdf` · `Organigrama SEAH.pdf` · `Perfil Jefe de Bahías 3.xls` · `actividades por puesto 2003.xls`<br>`Downloads/rrhh para revisar/FRAMBUESA 2026/CONDICIONES DE TRABAJO {COSECHADOR,PESADOR,SUPERVISOR} 2026.docx` · `20. FORMATO CARTA RESPONSIBA.docx` · `6. ACUSE DE MOBILIARIO Y REGLAMENTO DE VILLAS.docx`<br>`Downloads/RH_Architecture_Freeze_v1/` · `RH-MASTER-SCOPE-001-v2.md` · `01_mapa_maestro_rrhh_original_git.md`<br>`Downloads/Evaluación de cosechador.xlsx` · `RANKING COSECHADORES  SEMANA 34.xlsx` · `BIO-ABR2026_Finiquitos_v4.xlsx` · `FINIQUITOS 200726.xlsx`<br>`Downloads/FORMATO DE NOMINA ESPECIAL {NATURAL,BIO} SEM *.xlsx` · `NOMINA ADM IMS Y EFE.xlsx` · `PAGO POR DESTAJO SEMANA 26_2026 (PRIMO CAÑA).xlsx` · `Personal BIO y Natural2.xlsx` | XLSX, XLS, DOCX, PDF, MD | Organigramas reales NFA/BIO/SEAH, tabulador, matriz de capacitación (10 áreas), perfil de Jefe de MO (`NAT-MO-RH-000`), cartas de condiciones laborales 2026 por rol (Cosechador/Pesador/Supervisor), responsivas, esquema de contratistas, evaluaciones y ranking de cosechadores, arquitectura congelada de RH y formatos reales de nómina `IMSS` vs `ESPECIAL` (efectivo) y finiquitos. *(Nota de privacidad: los padrones con CURP/datos personales en `Downloads` y `datos_privados_rrhh` NO se suben al repositorio Git).* |
| **5. Operación Diaria de Campo y Labores Culturales (Fase 3B)** | `Downloads/docs berries 2026/` (**93 archivos**: Frambuesa 2024–25 y 2025–26 Caña Larga/Primocaña, Fresa 2024–25 y 2025–26): `ASIGNACIONES*.xlsx`, `ROL DE DESCANSO.xlsx`, `BITACORA LABORES CULTURALES (DIARIAS).xlsx`, `TIEMPOS POR OPERACIONES*.xlsx`, `REGISTRO CAJAS POR COSECHADOR*.xlsx`, `poda por valvulas.xlsx`, `RENDIMIENTOS PERSONAL.xlsx`<br>`Downloads/BACKUP_RH_TABLETGROWER_2026-09-16_NO_MODIFICAR.xlsx` · `ACUMULADO_26 FRAMBUESA PRIMO CAÑA..xlsx` · `CIERRE COSECHA CICLO 2025-2026.xlsx` | XLSX | Historial real completo de asignaciones diarias, roles de descanso, registros de cajas por cosechador/pesadora, tiempos por operación y bitácoras diarias individuales de labores culturales (frambuesa y fresa), además del respaldo real de `TabletGrower` al 16/09/2026 para pruebas de migración ETL. |
| **6. Villas, Comedor y Logística de Personal (Fase 4)** | `Downloads/rrhh para revisar/VILLAS/`: `11. GASTOS VILLAS.xlsx`, `11.1 SERVICIOS Y COMIDAS 2025.xlsx`, `3. COMIDAS NATURAL.xlsx`, `4. CHECK LIST DE VERIFICACIÓN DE VILLAS.xlsx`, `8. BITACORAS VILLAS.xlsx`, `Incidencias Villas.xlsx`, `ROL RH VILLAS.xlsx`, `Calendario 2025 y 2026  para aplicaciones en villas version 2 (2).xlsx`, `Traslado a enfermería.docx`<br>`Downloads/COMIDAS PRIMO CAÑA 2026.xlsx` · `Refrigerio mañanero villas .pdf` · `Reuni-n-sobre-Comidas-y-Productividad-*.pdf`<br>`Downloads/rrhh para revisar/Subidos/2025/Comparativa Transporte.xlsx` · `ROL RUTAS 08112025.xlsx` · `VIAJE HUEJUTLA.xlsx` | XLSX, DOCX, PDF | Operación completa de villas (checklists de 9 partes, servicios CFE/agua/internet, fumigación, incidencias, traslado a enfermería), control semanal de comidas/lunches por cultivo (Frambuesa/Fresa) y logística de rutas/viajes de personal foráneo (Huejutla). |
| **7. Técnico, Agroquímicos, Inocuidad y Certificaciones (Fase 5)** | `Downloads/NAT-LIS-PRO-001-LISTA AUTORIZADA PRODUCTOS FRAMBUESA Y FRESA.xlsx`<br>`Downloads/matriz_maestra_srrc_primus_fsma_smeta_natural_fruits_2026.xlsx` (22 pestañas)<br>`Downloads/Plan_recuperacion_inocuidad_certificaciones_NFA.pdf` · `Certificado Cuadrilla de Cosecha.pdf` · `Corrective Actions {Cuadrilla,Cuarto frio}.pdf` · `Resumen no conformidades-Natural Fruit-2.pdf`<br>`Downloads/021646 ANALISIS FITOPATOLOGICO DE PLANTA.pdf` · `PROPUESTA DE OPTIMIZACIÓN DEL MONITOREO MICROBIOLÓGICO DE AGUA.pdf` · `BIO_NOV-2020_009069_ANALISIS_DE_SOLUCION_NUTRITIVA_FINAL.pdf` | XLSX, PDF | Lista oficial autorizada de agroquímicos (`NAT-LIS-PRO-001`: Acaricidas, Fungicidas, Insecticidas, Coadyuvantes, Desinfectantes) con **RSCO, REI (horas), PHI/IS (días), dosis, LMR MEX/USA/CAN y bandera `¿SE APLICA?`** (ej. Pirekrone prohibido en fresa USA; Acaritouch sin LMR). Matriz maestra de auditoría **SENASICA SRRC, PrimusGFS/Mastronardi, FSMA, SMETA y HACCP**. |
| **8. Comercial, Empaque, Embarques y Multi-Comercializador (Fase 6)** | `Downloads/1. Natural Fruit A&R FPMA 11.19.25 - Executed.pdf` · `2. Natural Fruits A&R GLBA 11.19.25 - Executed.pdf` · `3. Natural Fruit A&Restated SA 11.19.25 -Executed.pdf`<br>`Downloads/contrato hortifrut.pdf` · `Analisis_Juridico_Contrato_Hortifrut.docx` · `Propuesta_Modificaciones_Contrato_Hortifrut_T26-27_NFA-BIO.docx`<br>`Downloads/Presentación DEPARTAMENTO DE EMPAQUE.PPTX` · `MATERIAL DE EMPAQUE PARA VENTA.xlsx` · `Resumen_Ejecutivo_CASO_053_001_SOLYSA_Mastronardi.docx`<br>`Downloads/CONTROL DE  ENTRADAS Y SALIDAS FRAMBUESA final 2026_CONCILIADO_v3.xlsx` · `INGRESOS EXPORTACION FRAMBUESA 2026.xlsx` · `INGRESOS NACIONALES FRAMBUESA 2026.xlsx` · `Venta fresa y arandano nov2026 v2.xlsx`<br>`Downloads/NATURAL FRUITS ... Grower Settlement – Week 16.pdf` · `WEEK 17 PRICE SHEET...pdf` · `Mastronardi_2026_Paquete_Direccion_PreFinal_v5.xlsx` | PDF, DOCX, PPTX, XLSX, XLSM | Contratos firmados Mastronardi (FPMA, GLBA, SA), negociación Hortifrut T26-27 y referencias Crystal Fields (`12×6 oz`, `12×1 pt`, convencional/XL; calibrado preliminar estándar `≥12 mm`, jumbo `≥19 mm` Hortifrut). Control conciliado de empaque (caso SOLYSA propio vs consignado), liquidaciones semanales (*Grower Settlement*), papeles de facturación nacional y exportación. |
| **9. Costeo `Merqry`, Finanzas y Presupuestos (Fase 7)** | `Downloads/MODELO_COSTO_REAL_FRAMBUESA_2025_2026_v5.xlsx` · `HANDOFF_55_COSTO_REAL_FRAMBUESA_2026-09-22_v5.md`<br>`Downloads/BIO_2024_COSTOS_FRESA_FINAL.xlsx` · `NFA_Costos_Base_y_Sensibilidad_2027_10oct2026 (3).xlsx` · `PLANTILLA GTO INDIRECTOS {FRAMBUESA 2026,FRESA 2025}.xlsx`<br>`Downloads/Gastos Agroquimicos frambuesa 25-26.xlsx` · `Gastos fertilización frambuesa 25-26.xlsx`<br>`Downloads/tablas merqry.pdf` · `RESUMEN DE VTAS MERQRY 01102026.pdf`<br>`~/MERQURY_TABLAS_COMPLETAS.txt` · `~/NFA-BIO_JUN-2026_Schema_Merqury_ANALISIS_DRAFT.sql`<br>`~/proyectos/Sistema integral .../base_conocimiento_costeo_frambuesa.md` · `analisis_planta_frambuesa_2026.md` · `presupuesto_mo_semanal_bio_natural_2026_actualizado.xlsx` | XLSX, PDF, MD, SQL, TXT | Modelo de costo real Frambuesa 2025–2026 (separando M1–10 vs M11), estructura de costos Fresa (`CF1`, `CF2`, armadura/canaleta, sustrato, MO), esquema analítico de tablas `Merqry` (solo lectura) y presupuestos de mano de obra semanal NFA/BIO. |

---

### 11.2 Qué Quedó CONFIRMADO (ya integrado en Fase 0) vs Qué Sigue PENDIENTE de Validar con Luis

| Tema | ✅ Confirmado con Evidencia Documental (incorporado en `02_schema_campo_pagos.sql` y `03_seed_data.sql`) | ⏳ Pendiente de Validar con Luis antes de Fase 1 / Fase 3A |
|---|---|---|
| **Variedad Frambuesa (`FRAMB` — NFA)** | **`Diamond Jubilee (DJ)`** en dos cohortes separadas: **`Long Cane`** (`FRAMB-DJ-LC`) y **`Primocaña`** (`FRAMB-DJ-PC`). Orden MPL #260100 firmada el 02/11/2026: `10.2 ha`, `208,000` plantas, `$3.50 USD/planta` (`$728,000 USD`), devolución de cajas/bins plásticos. | Confirmar si en la recepción real de camiones de Fase 3A el proveedor entrega clasificaciones separadas (`GRADE_A`, `SINGLES`, `CANES`) y registrarlas **sin conversión implícita**. |
| **Geometría y Densidad Frambuesa M1–M11** | **M1–M8 (`NFA-FRAMB-M01`..`M08`):** `0.7680 ha` (`7,680 m²`), `40` líneas (`3,040 m`), `174` macetas/línea (`83 N / 91 S`) = `6,960` macetas 7 L (INVECO FTP-025), `2` cañas/maceta → **`13,920` cañas/módulo** (`4.579 cañas/m lineal`).<br>**M9–M11 (`NFA-FRAMB-M09`..`M11`):** `0.6912 ha` (`6,912 m²`), `36` líneas (`2,736 m`), `6,264` macetas → **`12,528` cañas/módulo** (`4.579 cañas/m lineal`; M11 = estructura `AUSTERO` / `BAJA`). Total M1–M11 = **`148,944` cañas** (`confirmado_tecnico = TRUE`). | Confirmar umbrales oficiales de **merma en trasplante** (histórico 2022–23 fue `4.36%`–`9.43%` separando 1ª merma rota vs 2ª merma sin brotación), **supervivencia mínima** y **disparador de resiembra** (se mantienen en `NULL` en `lotes_densidades_config`). |
| **Frambuesa Módulo 1.1 (`NFA-FRAMB-M1.1`)** | Nave baticenital `~2.7672 ha` (`~27,000 m²`), túneles de `11.5 m`, **`65` líneas** (`204`/`170` macetas/línea), `78,030` goteros, maceta 7 L, `2` plantas/maceta. | Conciliar discrepancia entre **`26,010` macetas (`52,020` plantas)** en `1. Requerimientos frambuesa para mod 2.7.xlsx` vs **`26,520` macetas (`53,000`–`53,040` plantas)** en `sustrato nfa 2.xlsx` y `NAT-TRASPLANTE`, más destino del remanente de `~6,056` plantas frente a las `208,000` contratadas en 10 camiones de `20,800`. Confirmar metros lineales exactos y clasificación `ALTA` vs `MEDIA_ALTA`. |
| **Arándano (`ARAND` — BIO: M1.2, M2.1, M2.2)** | Variedad **`AzraBlue` (`FCM14-031`, Fall Creek)** confirmada; bolsas elevadas de **30 L** en fibra de coco (28 perforaciones: 16 sup., 12 inf.); túneles `11.5 m` (`M1.2`) y `10.0 m` (`M2.1`, `M2.2`); total **`60,750` plantas** en 3 módulos; trasplante S26 (`M2.1`) y S29 (`M2.2`). | Confirmar: (1) distribución exacta de plantas por módulo (`20,250` parejo a `7,500 pl/ha` en `GROWER_MODULOS_CATALOGO` vs `22,500 / 22,500 / 15,750` a `8,333 pl/ha` en `2. Requerimientos arandano.xlsx`), (2) superficie activa (`5.8 ha` Hortifrut vs `8.1` / `8.3 ha`), (3) si entra **`Sekoya Pop`** en algún bloque, (4) peso oficial de caja en planeación (`2.00 kg` vs `2.040 kg` comercial / `2.140 kg` real), y (5) clasificación `ALTA` vs `MEDIA_ALTA` por nave. |
| **Fresa (`FRESA` — NFA: M21, M22)** | Módulos `21` y `22` (`~1.3000 ha` / `~13,000 m²` c/u; referencia histórica `93.96 m × 136.5 m`), estructura `MEDIA_TECNOLOGIA`, canaletas elevadas 45 cm y `Growbag 18L`. Histórico 2023–24 documentado: **`Albion`** + **`Frontera`** (`108,000` plantas raíz desnuda/módulo: `54k + 54k`) y **`Sayulita`** (cepellón Planasa). | Confirmar variedades vigentes ciclo 2026–2027 en M21 y M22, presentación de planta al arribo (`RAIZ_DESNUDA` vs `CEPELLON`), número exacto de camas/válvulas/metros lineales, densidad objetivo y umbrales de trasplante/resiembra. |
| **Inactivos Excluidos** | Bloque inferior `"Módulo 7"` (`REF-MOD7-INF`) y vivero en plan (`REF-VIVERO-PLAN`) registrados con `activo = FALSE` y `estatus_fitosanitario = 'CERRADO'`. | Confirmar únicamente si alguno de los dos llegara a reactivarse en ciclos futuros. |

---

## 12. Auditoría Comercial, Contractual y Operativa de Mastronardi (MPL / MBWA / MBWV)

> **Alcance del barrido:** 285 archivos y paquetes relacionados con Mastronardi localizados en `C:\Users\geren\Downloads` (y subcarpetas/ZIPs inspeccionados en memoria sin alterar archivos) + `~/proyectos/Sistema integral operativo y administrativo conectado a erp`, cruzados contra el código legado `SEAH` (`/mnt/c/clasp_project`).  
> **Entidades contractuales:** **Mastronardi Produce Limited (`MPL`, Kingsville, Ontario, Canadá)**, sus afiliadas **Mastronardi BerryWorld America (`MBWA`)** y **Mastronardi BerryWorld Varieties, LLC (`MBWV`)**, y **Natural Fruits of America, S.P.R. de R.L. de C.V. (`NFA`)** (Rep. Legal: Luis Adrián Martínez de León).

### 12.1 Catálogo Estructurado de Documentos de/sobre Mastronardi

| Categoría | Archivos / Rutas Clave (`C:\Users\geren\Downloads\...` y local) | Formato | Fecha / Ciclo | Tema Principal |
|---|---|---|---|---|
| **1. Contratos Marco Firmados (Tríada DocuSign `1D7635C3-...`)** | `1. Natural Fruit A&R FPMA 11.19.25 - Executed.pdf` (32 págs)<br>`2. Natural Fruits A&R GLBA 11.19.25 - Executed (1).pdf` (35 págs)<br>`3. Natural Fruit A&Restated SA 11.19.25 -Executed.pdf` (27 págs) | PDF firmado (DocuSign) | Fechados 16/sep/2025, vigencia retroactiva 01/ene/2025, ejecutados 29/oct–19/nov/2025 (plazo inicial 5 años) | **FPMA** (*Fruit Purchase & Marketing Agreement*: compra/comercialización, precio fijo vs Open Price, pronóstico ±20%, calidad/rechazos 7 días/48h, pago 30 días, set-off, garantía RUG/UCC, Schedule 1 precios y Schedule 2 curvas). **GLBA** (*Growing License & Plant Bailment Agreement*: propiedad/comodato de planta *Diamond Jubilee BMR-1VF*, entregas en parcialidades, vida útil permitida y destrucción obligatoria). **SA** (*Service Agreement*: *Consultation Fee* por planta, tabla de 8 escalones `$2.00–$3.50`, plan de retenciones semanales y cuotas de deuda 2023). |
| **2. Órdenes de Planta y Estado de Cuenta de Deuda** | `260100_Natural_Fruits_of_America_DJ_LC_-_Nov (2).pdf`<br>`Natural Fruits Plant Debt Statement - Issued Sept 2026 (2).pdf`<br>`SALDO DE PLANTA 3 AÑOS CONSIDERANDO DESCUENTOS 14092026.xlsx`<br>`PLANTA GLOBAL 2022-2026  V2.xlsx` · `PLANTA 2026 0926.xlsx` | PDF firmado, XLSX | Nov 2026 (Ciclo 2026–2027) y Sept 2026 (Corte 2025–2026) | Orden de suministro `#260100` (`10.2 ha`, `208,000` plantas DJ LC a `$3.50` nominal = `$728,000 USD`, cajas plásticas retornables). Estado de cuenta oficial de planta (`SIMBW*` / `SI*`): desglose `DJ LC`, `DJ Tips` (`$13,806.10`), `Freight` (`$75,950`), `Phyto` (`$900`), `Credits/Claims` (`$93,632`), `Consolidation Credit Applied` (`-$41,673.53`), saldo `$112,899.61` (vs `$112,889.61` citado por Kelcey). |
| **3. Liquidaciones (*Grower Settlements*) y Hojas de Precio** | `NATURAL FRUITS OF AMERICA SPR DE RL DE CV Grower Settlement – Week 16.pdf`<br>`WEEK 17 PRICE SHEET - NATURAL FRUITS OF AMERICA SPR DE RL DE CV.pdf`<br>En `Mastronardi_Evidencias_2026_v5_CierrePlaneado.zip`: `Grower Settlement – Week 31.pdf` (`PO150505`) y `Week 33.pdf` (`PO155367`, `PO155576`) | PDF | Semanas 16, 17, 31 y 33 de 2026 | Liquidaciones reales con líneas separadas de precio base (`$19–$21/caja`), `Over Forecast`, `Unrequested Volume` (`$8/caja` en W31), `Rejection` (`$15.69/caja` en W33), `Transportation Costs` (`-$0.59` a `-$1.80/caja`), `Consolidation Deduction` (`-$0.42/caja` / `-$604.80`), `Plant Deduction` y métrica `3 WK Forecasting Accuracy`. |
| **4. Especificaciones Técnicas, Tarimas y Calidad QIMA-MBWA** | En `Mastronardi-20260617T025354Z-3-001.zip` (46 archivos):<br>• `Item Specification Report - RRAS1005 / RRAS1006 / RRAS1012` (HEB, BW México, BW Costco Canadá)<br>• `MBWA Inspecciones de Calidad.pdf` · `Inspecciones de Calidad QIMA-MBWA.eml`<br>• `Guía Inspección de Calidad PT Frambuesas.pdf` · `Presentacion Tarimas Berry World.eml`<br>• En `Mastronardi_Evidencias_2026*.zip`: `QIMA.xlsx`, `Qima CAÑA LARGA.xlsx`, `PDF QIMA*.rar` | ZIP, PDF, EML, XLSX, RAR | 2023–2026 | Especificaciones exactas de SKU (`RRAS1005`, `RRAS1006`, `RRAS1012`), pesos etiqueta vs físicos, cadena fría (`34–37°F`), empaque primario/secundario/terciario (CHEP 4-way, 4 esquineros 90", 4 flejes, 4 hojas separadoras, etiqueta PTI 4×2, ID Pallet), **240 cajas/tarima (12×20)** y umbrales PASS/FAIL de inspección QIMA en Laredo (`10%` defectos totales / `5%` daño serio / `1%` decay berries o `2%` fresa). |
| **5. Cierre 2026, Conciliaciones y Negociación Adéndum 2027** | `Mastronardi reporte actualizado.pdf` · `NFA Final Review.pdf` (26 oct 2026)<br>`MASTRONARDI_2026_DIRECCION_ACCIONISTAS_FINAL_2026-09-15.md`<br>`Conciliacion_y_compromisos_Mastronardi_10_octubre_2026.docx`<br>`Estado_acuerdos_y_pendientes_Kelcey_2026_10_11_ES.docx`<br>`Guia_reunion_Mastronardi_12nov2026.docx`<br>`NFA_Paquete_Comercial_2027_Correos_y_Adendum_ES_EN.docx`<br>`Propuesta_porcentaje_precio_planta_2027_ES_EN.docx` | PDF, MD, DOCX | Sep–Nov 2026 (Cierre 2026 / Adéndum 2027) | Estado punto por punto de 9 reclamos de cierre 2026 y 13 solicitudes del Adéndum 2027, respuestas oficiales de MPL (`NFA Final Review`: cierre de caso Hernández sin sobrecobro, metodología de flete real prorrateado, revisión Agrizar `$0.21/lb`, propuesta `$19` plano 2027 sin techo, revisión de fórmula continua de planta). |
| **6. Logística, Fletes, Aduana y Empaque SOLYSA** | `INGRESOS FRAMBUESA 2026 - analisis de gastos por envio a mastronardi.xlsx` (16 hojas)<br>`CONTROL DE ENTRADAS Y SALIDAS FRAMBUESA final 2026_CONCILIADO_v3.xlsx`<br>`Resumen_Cronologico_Material_Empaque_SOLYSA_Mastronardi.docx` · `Resumen_Ejecutivo_CASO_053_001_SOLYSA_Mastronardi.docx`<br>`correo de mastro aduana importador.pdf` (escaneado) | XLSX, DOCX, PDF | 2025–2026 | Control embarque por embarque (`SEM PROD` vs `SEM ENVIO`, `PO`, `NX`, flete, descuento planta, saldo USD/MXN), análisis de fletes Primocaña (`$0.652` ref. 2025 vs `$1.022–$1.205` 2026), ventas nacionales MXN (comisión 5% crédito / 0% sitio) y trazabilidad de devolución/notas de crédito de material de empaque con SOLYSA/Vitanova (`ZTRY1070`, `ZTRY1072`). |
| **7. Paquetes Ejecutivos, Costeo y Presentaciones Interactivas** | `Mastronardi_2026_Paquete_Direccion_PreFinal_v5.xlsx` (16 hojas)<br>`Mastronardi_2026_Presentacion_Interactiva.zip` · `Mastronardi_Evidencias_2026_v5_CierrePlaneado.zip`<br>`PAQUETE_COMPLETO_MASTRONARDI_JUEVES.zip` · `PAQUETE_MAESTRO_MASTRONARDI_JUEVES.zip` (27 archivos, 14 libros de costo/escenarios)<br>`~/proyectos/Sistema integral .../analisis_planta_frambuesa_2026.md` · `base_conocimiento_costeo_frambuesa.md` | XLSX, ZIP, HTML, MD | Sep–Nov 2026 | Simuladores de escalones vs fórmula continua de planta, análisis de márgenes y sensibilidad 2025–2027, conciliación de M11 Tips (`8,593`–`9,100` cajas) y expedientes de respaldo organizados por carpeta de evidencia. |

---

### 12.2 Reglas Comerciales, Operativas y Financieras Extraídas para el ERP

#### A. Esquema Comercial, Propiedad de Planta y Modelo de Precios
1. **Naturaleza jurídica dual (Compra/Comercialización + Comodato de Planta):**
   - **GLBA §3.1–3.2 (Comodato/*Bailment*):** Todas las plantas de variedades patentadas (`Diamond Jubilee BMR-1VF`) son propiedad exclusiva de MPL / *Variety Owner*; NFA las posee únicamente como comodatario (*bailee*) sin propiedad sobre el material vegetal, con prohibición estricta de propagar, transferir o conservar fuera de la *Allowed Crop Life* (destrucción obligatoria antes de pedir reposición). MPL renuncia al título sobre el fruto (Art. 2501 CCF) exclusivamente para su venta bajo el FPMA.
   - **FPMA §1–§2 (Exclusividad y compra/comercialización):** Exclusividad del 100% de fruta de calidad para variedades patentadas (pena convencional: `$50,000 USD/acre` campo abierto o `$100,000 USD/acre` invernadero); derecho de preferencia (*ROFR*) en no patentadas. Vigencia inicial 5 años + renovaciones automáticas de 5 años (aviso con 2 años de anticipación; prórroga automática si quedan adeudos/anticipos sin pagar dentro de los 90 días previos al término).
2. **Compra en Firme (*Fixed Set Price*) vs Consignación / Precio Abierto (*Open Price Method*):**
   - **Regla por defecto (FPMA §2):** ***Open Price Method*** (comportamiento tipo consignación/liquidación a resultado): precio bruto de venta al cliente final menos **comisión variable de comercialización (*marketing fee*)** y gastos de venta/distribución de MPL, ponderado sobre **peso de etiqueta (*label weight*)**.
   - **Excepción pactada en Schedule 1 (*Fixed Set Pricing*):** Aplica solo en las ventanas expresamente acordadas (**W26–W42 2025, W05–W20 2026, W26–W42 2026**) con precio bruto fijo de **`$4.22–$4.67 USD/lb`** = **`$19.00–$21.00 USD/caja`** de `4.5 lb` (`12×6 oz` y `6×12 oz`), bajo Incoterm **DDP Punto de Entrada EE.UU.** (Laredo/bodega designada). **No aplica DDP** en envíos *in-bond* a Canadá.
   - **Consecuencia para el ERP:** El motor comercial (Fase 6) DEBE soportar por contrato/ventana ambos modos (`FIXED_SET_PRICE_DDP` y `OPEN_PRICE_MARKETING_FEE`) y permitir que un mismo embarque tenga líneas liquidadas a precio fijo y líneas degradadas a *Open Price* / rechazo / volumen no solicitado (como ocurre en W31 y W33).
3. **Descuentos, Cargos, Planta y Notas de Crédito:**
   - **Deducciones sobre liquidación bruta (DDP):** Del precio bruto (`$19–$21`) MPL descuenta flete internacional/nacional (`Transportation Costs`: metodología oficial confirmada por MPL = **factura total del camión ÷ total de cajas**, fluctuando de `$0.45`–`$0.66/caja` hasta `$1.80/caja` por alzas de combustible o cargas parciales), consolidación/manejo (`Consolidation Deduction`: `$0.42/caja` en W16; tarifa base Agrizar `$0.21/lb` ≈ `$0.945/caja` nominal en revisión), aduanas, aranceles, *brokerage* y maniobras.
   - **Cargos de planta (*Service Agreement* — *Consultation Fee*):**
     - `Tip to Long Cane`: **`$1.10 USD/planta`**.
     - `Long Cane`: facturación nominal inicial **`$3.50 USD/planta`** (ej. OC `#260100`: `208,000 × $3.50 = $728,000 USD`), ajustable por la **Tabla Proporcional de 8 Escalones** según volumen exportado del ciclo (`80,000` cajas → `$2.00`, `85,714` → `$2.25`, `91,429` → `$2.50`, `97,143` → `$2.75`, `102,857` → `$3.00`, `108,571` → `$3.25`, `114,286` → `$3.38`, `120,000` → `$3.50`), más retenciones semanales en liquidación (*Plant Deduction*, ej. `-$19,025.89` en W31 y `-$27,525.94` en W33) y anualidades de adeudo histórico 2023 (`$58,505.35` en W44 de 2026 y 2027).
     - **Cargos accesorios separados en estado de cuenta de planta:** `Freight` (flete de planta importada, `$75,950`), `Phyto` (fitosanitario/SENASICA, `$900`), `DJ Tips` (`$13,806.10`) y **cajas/bins plásticos retornables** (si no se devuelven al propagador se cobran a NFA).
     - **Notas de crédito:** Deben rastrearse con folio formal, concepto, facturas/POs afectadas y estatus (`SOLICITADA / APROBADA / APLICADA`). Ejemplo confirmado: `Consolidation Credit Applied to Plant Balance = -$41,673.53` (ya aplicada al saldo de planta; solo falta folio formal; no reclamar duplicado).
   - **Mercado Nacional (canal alterno MXN):** Ventas en sitio (`0%` comisión) vs ventas a crédito (`5%` comisión sobre importe bruto).

#### B. Plazos de Pago, Semanas Comerciales, Mínimos de Carga y Presentaciones
1. **Plazos de pago, cuenta corriente y *Set-Off* (FPMA §2–§3, SA):**
   - Moneda: **USD**; plazo contractual máximo **30 días calendario** desde entrega en *Delivery Point* (en liquidaciones reales W16/W31/W33 y hoja `FACTURAS FRAMB PRIMO CAÑA`, el pago operativo fluye a **~21 días** posteriores al cierre de semana).
   - **Cuenta corriente única por temporada (*Running Account*):** No divisible; MPL tiene amplio derecho de **compensación (*set-off*)** entre todas sus entidades (`MPL`, `MBWA`, `MBWV`) para descontar anticipos, planta, empaque, fletes, consolidación y reclamos. Garantía prendaria (UCC + **RUG México**).
   - **Interés moratorio sobre adeudos de planta/servicios vencidos (SA):** **1.5% mensual compuesto mensualmente**.
   - **Guarda de cumplimiento:** Facturación fiscal conforme (MX/CA/US), registros computarizados en inglés conservados por **Plazo + 3 años** (auditables con **5 días hábiles** de aviso), reporte final de planta y fruta dentro de los **30 días** posteriores al cierre de temporada, seguro de responsabilidad civil de producto por **`$2,000,000 CAD`** nombrando a MPL asegurado adicional, y cumplimiento patronal IMSS obligatorio (FPMA §16d).
2. **Semanas comerciales, Pronóstico GSP y Penalización ±20% (FPMA §11):**
   - **Pronóstico semanal obligatorio:** Cada **martes**, NFA debe cargar en **GSP** el pronóstico de las siguientes **8 semanas**.
   - **Banda de tolerancia contractual ±20%:** Si la entrega real desvía **más de ±20%** respecto al pronóstico / *Schedule 1* / programa de empaque, el excedente o faltante se considera **producto no conforme**: MPL puede cambiar el precio a *Open Price Method* (como `Unrequested Volume` a `$8/caja` en W31) y repercutir costos de fruta sustituta (*cover costs*). *(Nota: el legado SEAH ya implementa un espejo de alerta temprana a ±10% antes de tocar el umbral duro de ±20%).*
   - **Calendario y desfase de semanas:** El ERP debe persistir simultáneamente **3 marcas temporales/semanales** por embarque para eliminar confusiones entre campo, GSP y finanzas: `semana_produccion` (`SEM PROD`), `semana_embarque_mastronardi` (`SEM ENVIO`, donde el legado maneja `SEMANA_OFFSET_MASTRONARDI = 1`) y `semana_liquidacion_settlement` (corte domingo–sábado de Finanzas MPL, ej. W31 = `08/02–08/08`, W33 = `08/16–08/22`).
3. **Presentaciones, Pesos y Tarimas (Especificaciones Oficiales MBWA/MPL):**
   - **SKUs confirmados en frambuesa:**
     - `12×6 oz` (`RRAS1005` BW México, `RRAS1012` HEB): peso etiqueta `6 oz` (`170 g`/clam = **`2.040 kg`/caja** = `4.5 lb`), peso físico objetivo `6.18–6.36 oz` (`175–180 g`/clam ≈ **`2.10–2.16 kg`/caja**, congruente con `peso_real_caja_kg = 2.140` en Fase 0).
     - `6×12 oz` (`RRAS1006` BW Costco Canadá, `RRAS1020`/`RRAS1024` Summer Dream): peso etiqueta `12 oz` (`341 g`/clam = `2.046 kg`/caja = `4.5 lb`), peso físico objetivo `12.84–13.50 oz`.
   - **Paletizado estándar Mastronardi (`Guía Inspección de Calidad PT Frambuesas.pdf`):** Tarima CHEP de 4 vías con **12 cajas/nivel × 20 niveles = `240 cajas/tarima`** (4 esquineros de 90", 4 flejes, 4 hojas separadoras cada 4 niveles, etiqueta PTI 4×2, ID Pallet con `Grower Code + PO + Fecha + Ítem + Cantidad exacta`, un solo ítem por tarima salvo autorización). **Hallazgo crítico:** esto explica que **8 tarimas = `1,920` cajas** (`8 × 240`) y revela una discrepancia frente al valor base `200 cajas/tarima` cargado en `cultivos.cajas_por_tarima` (seed Fase 0); en Fase 6 el factor `cajas_por_tarima` debe vivir por **presentación/comercializador** (no único por cultivo).
   - **Mínimo de recolección:** Históricamente 5 tarimas (`1,200` cajas); elevado operativamente por MPL a **8 tarimas (`1,920` cajas)** sin acuerdo escrito (camión propio NFA carga 4 tarimas, forzando traslados propios a Silao). Retorno a **5+ tarimas** en gestión por MPL (`NFA Final Review`).

#### C. Reglas de Calidad, Rechazos, Empaque e Impacto en CxC / Facturación / Costeo
1. **Estándares de calidad, QIMA y ventanas de rechazo/disputa (FPMA §4, §6 + Guía QIMA-MBWA):**
   - Grado mínimo **USDA / CFIA No. 1**, registro FDA Bioterrorismo, auditorías vigentes (**PrimusGFS, SRRC, FSMA, SMETA/EFI/Fair Trade**), análisis de residuos en laboratorio **ISO 17025** y cadena fría **34°F–37°F (1.1°C–2.8°C)**; baya frambuesa `≥ 3 g`, firme, cónica, sin pedúnculo.
   - **Umbrales QIMA-MBWA (PASS / FAIL en bodega Laredo):**
     - **Frambuesa, Arándano y Zarzamora:** `≤ 10%` defectos totales, `≤ 5%` daño serio, **`≤ 1%` pudrición/moho/yellow rust (*Decay*)**, suma total de control `≤ 10%`.
     - **Fresa:** `≤ 10%` defectos totales, `≤ 5%` daño serio, **`≤ 2%` *Decay***, suma total de control `≤ 10%`.
   - **Ventana de inspección / responsabilidad post-recepción:** **7 días (168 horas)** para frambuesa, fresa y zarzamora; **10 días** para arándano (inspecciones en bodega de origen son informativas y no implican aceptación).
   - **Ventana de disputa del productor:** Solo **48 horas** desde la notificación de rechazo para aportar evidencia documental sustancial (de lo contrario se pierde el derecho a reclamar). El ERP debe disparar **alertas críticas con conteo regresivo de 48h** al registrar cualquier notificación de rechazo.
   - **Destino de fruta no conforme:** Destrucción/devolución a costa de NFA o venta como USDA #2 / *Open Price* sin marcas MPL descontando re-selección, re-empaque y disposición.
2. **Empaque y caso SOLYSA (FPMA §5 + Expediente SOLYSA):**
   - Solo empaque aprobado por MPL/proveedor autorizado; **regla de inventario máximo de 8 semanas** (por encima de 8 semanas MPL no responde por cambios de formato/etiqueta).
   - Toda devolución/reclamo de empaque (ej. fallas de cierre en W33 `PO155576` o devoluciones SOLYSA `ZTRY1070`/`ZTRY1072`) exige trazabilidad estricta: `SKU + factura original + evidencia fotográfica + acta de inspección/destrucción + validación de cargo de flete`.
3. **Reglas obligatorias para CxC, Facturación y Costeo (Fases 6 y 7):**
   - **Ventas siempre son CxC (nunca CxP):** Todo embarque facturado (`NX*`) genera una Cuenta por Cobrar bruta en USD, que se concilia contra líneas del *Grower Settlement* (deducciones de flete, consolidación, retención de planta y notas de crédito se registran como partidas conciliatorias explícitas vinculadas a `PO + Factura NX + Semana`, nunca sobreescribiendo el ingreso bruto).
   - **Conciliación a nivel `PO + Factura NX + Línea Settlement`:** Como demostró el cierre del caso Hernández (`NFA Final Review`), el estado de cuenta de MPL puede mostrar una tasa prorrateada aparente sobre 100% de las cajas aunque el flete corresponda a otros POs; por ello el ERP jamás debe prorratear a ciegas sin cruzar el detalle por PO.
   - **Regla financiera inquebrantable — NO NETEAR / NO MEZCLAR cuentas heterogéneas:** En el ledger comercial/CxC y en reportes a Dirección deben mantenerse en subcuentas estrictamente separadas:
     1. Liquidación corriente de fruta del ciclo en curso (CxC);
     2. Cuenta de planta del ciclo actual (`OC`, `DJ LC`, `DJ Tips`, `Freight`, `Phyto`, retenciones y nota de crédito de escalón);
     3. Anualidades futuras de adeudo histórico (`$58,505.35` vencimiento 2027);
     4. Reclamos en disputa pendientes de nota de crédito formal (errores de precio W31/W33, daño comercial W31–W35, diferencias de flete/Agrizar, traslados Silao).

---

### 12.3 Matriz de Confirmado vs Pendiente de Validar con Luis (Mastronardi)

| Tema / Parámetro ERP | ✅ Confirmado (Contratos Firmados y Liquidaciones Reales) | ⏳ Pendiente de Validar con Luis (Negociación 2026/2027 sin Firma) |
|---|---|---|
| **Tríada contractual y propiedad de planta** | FPMA, GLBA y SA ejecutados (DocuSign `1D7635C3-...`, 5 años, vigencia 01/ene/2025). Planta *Diamond Jubilee* en comodato (*bailment*), entregas parciales severables (alineado a Fase 3A Multi-Camión), OC `#260100` firmada (`208,000` plantas, `10.2 ha`, `$3.50` nominal, cajas plásticas retornables). | Definir en Adéndum 2027 el procedimiento formal de inspección a recepción (**48h daño físico** y **14–21 días brotación** por lote) y criterio de reposición/nota de crédito por merma de planta. |
| **Esquema de precios fruta 2026 vs 2027** | 2025–2026: Fixed Set Price DDP `$19–$21/caja` (`$4.22–$4.67/lb`) en W26–W42 (2025), W05–W20 y W26–W42 (2026); fuera de ventana o desviado >±20% aplica *Open Price*. | **Tarifa 2027 aún abierta:** MPL ofrece **`$19/caja` plano sin techo** para LC+PC (1 año); NFA solicita `$21` base / `$25` techo (objetivo `$20`). Confirmar tarifa final y ventanas exactas (W05–20 / W31–43) al firmarse el adéndum. |
| **Precio final de planta y fórmula 2027** | 2025–2026 contractual: tabla de **8 escalones** (`80k` → `$2.00` hasta `120k` → `$3.50`) + `Tips = $1.10/planta`. Crédito por consolidaciones `-$41,673.53` ya aplicado (falta solo folio formal). | (1) Cierre 2026: conciliar base computable (con o sin ~`8,593–9,100` cajas de M11 Tips: `100,628` → `$3.00` / crédito `$68,208–$69,202` vs `109,728` → `$3.25` / `$34,104`), y la diferencia de `$10` en saldo (`$112,899.61` vs `$112,889.61`).<br>(2) 2027: validar si se firma **fórmula continua porcentual** (`MAX(2.00, 2.00*Q/ref)`) en sustitución de los 8 escalones. |
| **Flujo de efectivo, retenciones y deuda histórica** | Plazo contractual 30 días USD (~21 días real), cuenta corriente única con *set-off* y 1.5%/mes interés moratorio. Cuota histórica 2027 = `$58,505.35` (W44). | Confirmar si MPL concede **3–4 semanas de gracia inicial** sin retención de planta (reserva de nómina), proporción 60% LC / 40% PC y diferimiento de la cuota `$58,505.35` al último cobro de PC 2027. |
| **Logística, fletes, Agrizar y tarimas** | Metodología flete confirmada por MPL: factura camión ÷ cajas totales. Caso Hernández (`NX232/233/235/236/241`) **cerrado sin sobrecobro**. Empaque CHEP estándar MBWA = **`240 cajas/tarima` (12×20)** en `12×6 oz` y `6×12 oz`. | (1) Confirmar con Luis el estándar de **`200` vs `240` cajas/tarima** para `FRAMB` (el seed de Fase 0 mantiene `200` según instrucción inicial; en Fase 6 se parametrizará por presentación/cliente).<br>(2) Confirmar tarifa final Agrizar (`$0.21/lb` = `$0.945/caja` vs desglose carga/descarga `$0.623/caja`), tarifa flete 2027 y fecha efectiva de regreso a recolección desde **5+ tarimas**. |
| **Calidad, GSP y reclamos abiertos 2026** | QIMA-MBWA PASS/FAIL (`10%/5%/1%` berries, `2%` fresa), 7 días inspección frambuesa/fresa (10 días arándano), 48h disputa, pronóstico martes 8 semanas ±20%, inventario empaque máx. 8 semanas. | Confirmar resolución/folios de notas de crédito pendientes: `13,090` cajas no exportadas (`$47,378.61` en revisión con James), W31 `479` cajas (`$5,269`), W33 `640` cajas (`$2,117.01` crédito empaque en trámite `PO155576`), flete/manejo W27–W33 (`$20,386.55`), traslados Silao (`$7,058.82`), y exención de penalización GSP durante las 3 primeras semanas de desarrollo. |
| **Uso de cámara fría y esquema de empaque 2027** | Empaque actual bajo reglas FPMA §5 (aprobado por MPL, tope 8 semanas) y trazabilidad documental de devoluciones SOLYSA. | Confirmar si MPL acepta uso no exclusivo de cámara fría (con inocuidad/trazabilidad) y esquema 2027 de empaque en consignación a precio de contado pagando solo material consumido. |

