# Diseño Técnico de Escritura Controlada hacia Merqry (`merqry_writer`)

> **Estado actual:** **APAGADO POR DEFECTO (`MERQRY_WRITE_ENABLED=false`, `MERQRY_WRITE_MODE=DISABLED`, `MERQRY_READONLY_MODE=true`)**.  
> **Base analizada (estrictamente SOLO LECTURA):** `mq_bio_organicos_analisis` (`localhost:3307`, MySQL `5.7.44`).  
> **Referencia de esquema completo:** [MERQRY_BACKUP_SCHEMA_MAP.md](./MERQRY_BACKUP_SCHEMA_MAP.md).

---

## 1. Hallazgos Forenses Críticos del Motor Merqry

1. **Integridad 100% en Stored Procedures (0 triggers transaccionales, 0 FKs cabecera → detalle):**
   - No existen triggers sobre `ap`, `incid`, `nomina`, `inv`, `cont`, `bc`, `auxiliar`, `saldo`, `acumulado`.
   - No existen llaves foráneas físicas entre `ap/apd`, `incid/incidd`, `nomina/nominad`, `inv/invd`, `cont/contd`.
   - El despachador único `spAplicar` delega en `sp<Mod>` → `spGeneralInicio` → `sp<Mod>Validar` (`pe<Mod>Validar`) → `sp<Mod>Aplicar` → `spMovFolioAsignar` / `spSaldo` / `spGeneralFin`.
2. **Ausencia total de bloqueos explícitos en los 28 SPs auditados:**
   - `SELECT ... FOR UPDATE`: **0 ocurrencias**.
   - `LOCK TABLES`: **0 ocurrencias**.
   - `GET_LOCK()`: **0 ocurrencias**.
   - Tanto `spMovFolioAsignar` (`*consecutivo`) como `spSaldo` (`saldo`/`acumulado`) y `spPersonalAsiste` (`personalreloj`) operan sin bloqueo pesimista previo.
3. **Bug real confirmado en `spNominaValidar` (líneas 418, 429 y 441):**
   - El SP contiene `vg_MovClase in ('NOM.N' 'NOM.EX', ...)` **sin coma** entre ambos literales. En MySQL 5.7 eso se concatena silenciosamente a `'NOM.NNOM.EX'`.
   - Como consecuencia, Merqry **omite** las validaciones `09001` (Fórmula), `09017` (FechaPago), `09002` (saldo/cantidad excedida en `incidd`) y `09003` (importe neto negativo a pagar) para `NOM.N` y `NOM.EX`.
   - `merqry_writer` implementa obligatoriamente estas 4 validaciones en Python antes de encolar o despachar cualquier nómina.
4. **Inversión crítica de IDs de empresa entre PostgreSQL y Merqry:**
   - **PostgreSQL (`empresas`):** `clave = 'NFA'` → `id = 1`; `clave = 'BIO'` → `id = 2`.
   - **Merqry (`empresa`):** `Empresa = 1, Sucursal = 1` → `BIO-ORGANICOS SALUDABLES` (`BSA150508DY2`); `Empresa = 2, Sucursal = 2` → `NATURAL FRUITS OF AMERICA` (`NFA1702024H2`).
   - Toda traducción de empresa DEBE resolverse por **`empresas.clave`** (`BIO -> (1,1)`, `NFA -> (2,2)`), jamás por igualdad numérica de IDs.
5. **Trampa homónima `'Nomina Especial'` (`NOM.EX`):**
   - En Merqry, `nomina.Mov = 'Nomina Especial'` es nómina fiscal/CFDI extraordinaria que además genera `bc`, `nominabccfdi` y puede disparar `AP.BAJA` automática (`spNominaAplicar` L457–478). Está **permanentemente en lista negra** en `merqry_writer` y nunca debe confundirse con `ESPECIAL_CONTABILIDAD`.

---

## 2. Contrato de Stored Procedures, Estados Iniciales y Validaciones

### Despachador `spAplicar`
```sql
CALL spAplicar(
  vg_ID, vg_Modulo, vg_Accion, vg_ConBaseEn, vg_MovAvanzar,
  vg_Usuario, vg_EnSilencio /* 1 */, vg_SinTransaccion /* 0 */,
  @vg_OK, @vg_OkMensaje
);
```

| Flujo | SPs Principales | Estado Inicial Seguro | `Mov` Permitidos (Whitelist) | Validaciones Internas Clave (`mensaje`) | Riesgo Principal |
|---|---|---|---|---|---|
| **1. `AP` (Altas/Bajas IMSS)** | `spAP`, `spAPValidar`, `spAPAplicar`, `spNominaTurno` | `ap.Estatus = 'SINAPLICAR'` | `Alta`, `Baja`, `Cambio`, `ReIngreso` | `08001`–`08020` (estatus previo, jefe activo, sucursal, fechas ≤ emisión, depto, puesto, salario, jornada, turno) | Contención en `contactopersonal`/`nominaturno`; doble alta/baja corrompe antigüedad/SDI |
| **2. `INCID` + `NOM` + `ASISTE`** | `spPersonalAsiste`, `spIncid*`, `spNomina*`, `spContGenerarNomina` | `incid`: `'SINAPLICAR'`<br>`nomina`: **`'PREVIO'`** | `INCID`: faltas, horas extra, bonos, incapacidades<br>`NOM`: `Nomina`, `Nomina Quincenal` | `INCID`: `09012`, `10001`–`10008`<br>`NOM`: `09004` + **pre-validación Python espejo para `09001`, `09002`, `09003`, `09017`** | `spPersonalAsiste` usa `NOW()` (no apto para offline); `spNominaAplicar` genera `bc`/`nominabccfdi`/`AP`; bug en `spNominaValidar` |
| **3. `INV` + `PROD`** | `spInv*`, `peInvValidar`, `spProd*` | `inv.Estatus = 'SINAPLICAR'` (soporta `'VALIDAR'`) | `Entrada`, `Entrada Diversa`, `Salida`, `Consumo Materiales`, `Transferencia`, `Merma` | `02001`–`02048` (lotes exactos `serielotemov`, disponible `02039`, caducidad `02037`, costo `02009`/`02024`); `17004`–`17021` (`PROD`); `peInvValidar` solo aplica a `CG`/`VENTA.F` | `spInvAplicar` (65 KB) toca `saldo`/`saldou`/`serielote`/`articulocosto` sin `FOR UPDATE`; costeo `Promedio` sensible a orden cronológico |
| **4. `CONT` (Pólizas y Auxiliar)** | `spCont*`, `spContGenerar`, `spSaldo` | `cont.Estatus = 'SINAPLICAR'` (soporta `'VALIDAR'`) | `Diario`, `Egresos`, `Ingresos` | `05000`–`05003` (cuenta subcuenta/auxiliar activa no acumulativa, moneda `'Pesos'`), `05005` (`Cargos == Abonos`), `05006` (`CuentaPadre`), `05010` (póliza cancelación) | Deadlocks InnoDB al propagar `spSaldo` a `CuentaPadre` compartidas; riesgo de doble contabilización sin lock en `*cont` |

---

## 3. Arquitectura de `merqry_writer` (Fail-Closed)

### Triple Candado de Activación
1. `MERQRY_WRITE_ENABLED=false` (default inmutable en producción hasta autorización explícita).
2. `MERQRY_WRITE_MODE=DISABLED` (modos futuros: `STAGING_DRAFT_ONLY` → solo borradores `SINAPLICAR`/`PREVIO`; `CONTROLLED_APPLY` → `spAplicar` solo en módulos en `MERQRY_WRITE_ALLOWED_MODULES`).
3. **Verificación de esquema/host destino:** `MERQRY_WRITE_ALLOWED_SCHEMA` nunca puede ser vacío ni `mq_bio_organicos_analisis` (espejo forense bloqueado permanentemente).
4. **Firewall de circuitos:** `CHECK (circuito_pago = 'IMSS_MERQRY')` físico en PostgreSQL + rechazo `403 CIRCUIT_FIREWALL_BLOCKED` en API para `ESPECIAL_CONTABILIDAD`, `EFECTIVO`, `OFF_IMSS` y `Nomina Especial`.
5. **Outbox idempotente en PostgreSQL:** `merqry_write_outbox` (`idempotency_key UNIQUE`, `payload_sha256` → `409 Conflict` ante mutación, `merqry_ref_tag` `AGRO:<uuid12>` para recuperación post-commit) + `merqry_write_audit_log`.

### Serialización Externa contra Deadlocks y Colisión de Folios
- Antes de escribir en MySQL (cuando se active en laboratorio), adquirir:
  1. Lock en PostgreSQL (`pg_advisory_xact_lock`) sobre `(merqry_empresa, modulo, mov)`.
  2. Lock en MySQL (`SELECT GET_LOCK('agro_mq:<emp>:<mod>:<mov>', 15)`) y lock global `agro_mq:<emp>:CONT` para `CONT`/`spContGenerar`.
- Reintento acotado (máx. 3 intentos con *backoff*) únicamente ante errores InnoDB `1213` (Deadlock) y `1205` (Lock wait timeout), verificando previamente por `merqry_ref_tag` para impedir duplicados.

---

## 4. Plan de Pruebas en Clon Aislado (`mq_bio_organicos_write_lab`)

1. **Fase 0 — Clon Efímero:** levantar contenedor MySQL `5.7.44` aislado en puerto `3308` con copia completa de `mq_bio_organicos_analisis` y usuario `agro_writer_lab` sin `DROP/ALTER/TRUNCATE`.
2. **Fase 1 — Pruebas de Firewall y Fail-Closed (PostgreSQL + Pytest, sin MySQL):**
   - `MERQRY_WRITE_ENABLED=false` bloquea cualquier `dispatch` con `503`.
   - `ESPECIAL_CONTABILIDAD` y `Nomina Especial` bloqueados con `403` y auditados; `CHECK` físico en PostgreSQL impide inserción directa.
   - Pre-validaciones espejo de `spNominaValidar` bloquean neto negativo, `FormulaID` nulo, `FechaPago` nulo y exceso de `incidd`.
   - Idempotencia (`200/201` en replay idéntico, `409` en cambio de payload).
3. **Fase 2 — Pruebas Diferenciales en Clon Aislado:**
   - Orden progresivo: `AP` → `INCID` → `CONT` (+ `spContGenerar` con `vg_Simular=1`) → `INV` (con y sin `serielotemov`) → `NOM` (`PREVIO` y luego `APLICAR`).
   - Snapshot diferencial de `*consecutivo`, `movlog`, `movrastreo`, `auxiliar*`, `saldo*`, `acumulado*`, `*cont`, `bc`, `contactopersonal`.
   - Verificación de cancelación limpia (`vg_Accion='CANCELAR'`) y recuperación ante caída simulada tras `COMMIT`.
4. **Fase 3 — Concurrencia (10 workers paralelos):** validar 0 deadlocks no recuperados, 0 colisiones de folio (`00116`) y 0 descuadres contables (`05005`).
5. **Fase 4 — Criterio Go/No-Go:** solo habilitar piloto en `STAGING_DRAFT_ONLY` (`AP` e `INCID`) tras aprobación 100% de laboratorio y revisión visual de RH/Contabilidad en cliente Merqry.
