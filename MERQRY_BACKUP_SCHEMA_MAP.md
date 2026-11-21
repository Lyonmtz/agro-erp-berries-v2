# Mapeo Completo del Respaldo de Merqry (`mq_bio_organicos_analisis`)

> **Origen verificado (modo estrictamente SOLO LECTURA — `SET SESSION TRANSACTION READ ONLY`):**
> - **Servidor:** `localhost:3307` (Docker `erp_mysql57`, MySQL `5.7.44`)
> - **Base de datos:** `mq_bio_organicos_analisis` (espejo de análisis; **no productivo**, cero escrituras ni migraciones ejecutadas)
> - **Fecha de extracción:** 2026-11-21
> - **Regla rectora del proyecto:** Merqry permanece estrictamente **SOLO LECTURA** en `agro-erp-berries-v2`. Este mapa documenta la arquitectura interna completa y sirve como base técnica para evaluar **en el futuro** una eventual escritura controlada únicamente para el circuito `IMSS_MERQRY`, protegiendo en todo momento la separación absoluta respecto al circuito `ESPECIAL_CONTABILIDAD` (efectivo).

---

## 1. Resumen Ejecutivo y Métricas Globales del Esquema

| Métrica del Esquema | Cantidad Verificada | Observación Arquitectónica |
|---|---:|---|
| **Tablas base (`BASE TABLE`)** | **579** | Motor transaccional estilo Intelisis (cabecera + detalle `*d` + consecutivos `*consecutivo` + enlace contable `*cont`). |
| **Vistas (`VIEW`)** | **26** | Reporteo de existencias, costos, reservas, CFDI y aplicaciones `BC`/`CG`/`VENTA`/`INV`. |
| **Llaves foráneas físicas (`FK`)** | **114** *(en 101 constraints)* | **Hallazgo crítico:** la mayoría de relaciones cabecera↔detalle y módulo↔auxiliar son **lógicas** (no tienen FK física en MySQL), gobernadas por SPs. |
| **Índices (`STATISTICS`)** | **690** | Incluyen PKs compuestas y claves de consulta por `Empresa`, `Modulo`, `Folio`, `Cuenta`, `Articulo`, `Contacto`. |
| **Triggers activos** | **31** | **Hallazgo crítico:** **0 triggers en tablas transaccionales** (`ap`, `incid`, `nomina`, `inv`, `cont`, `bc`, `cg`, `venta`). Los 31 triggers son solo de configuración/catálogo/UI (`constructor*`, `empresa`, `sucursal`, `puesto`, `moneda`, `nominauma`, `nominavariablelista`). |
| **Rutinas almacenadas** | **803** | **764 Procedimientos almacenados (`sp*`, `pe*`) + 39 Funciones (`fn*`)**. Toda la lógica de negocio, folios, saldos y pólizas vive aquí. |

### Empresas y Sucursales Registradas en el Respaldo

| `Empresa` | Nombre en Merqry | RFC | `Sucursal` | Nombre Sucursal | Estatus |
|---:|---|---|---:|---|---|
| **1** | `BIO-ORGANICOS SALUDABLES` | `BSA150508DY2` | `1` | `BIO-ORGANICOS` | `ACTIVA` |
| **2** | `NATURAL FRUITS OF AMERICA` | `NFA1702024H2` | `2` | `NATURAL FRUITS` | `ACTIVA` |

---

## 2. Agrupación Completa de las 579 Tablas Base por Módulo Funcional

| Módulo Funcional | # Tablas | Filas Aprox. | MB Aprox. | Tablas Clave Representativas |
|---|---:|---:|---:|---|
| **1. RH, Expediente y Movimientos de Personal (AP)** | 7 | 20,489 | 5.97 | `apd`, `ap`, `contactopersonal`, `puesto`, `departamento`, `contactobeneficiario`, `personalcategoria` |
| **2. Asistencia, Incidencias y Nómina / CFDI (ASISTE / INCID / NOM)** | 70 | 23,491,048 | 2,142.16 | `nominaprevio`, `nominad`, `nominacfdipercepciond`, `nominacfdideducciond`, `nominacontacto`, `nominacfdiprocesar`, `incidd`, `nominaaplica` |
| **3. Inventarios, Almacén, Series/Lotes y Producción (INV / PROD)** | 84 | 4,657,313 | 810.85 | `auxiliaru`, `invd`, `serieloteauxiliar`, `serielotemov`, `inv`, `acumuladou`, `prodretrocesoconsumo`, `prodd` |
| **4. Compras, Gastos y Proveedores (CG)** | 23 | 223,568 | 210.45 | `cgd`, `cg`, `cgcont`, `cgxml`, `cgcto`, `cggasto`, `cgimportacion`, `cgdcaducidadprov` |
| **5. Ventas, Facturación, POS y Embarques (VENTA / PV / EMB)** | 61 | 30,154 | 7.38 | `ventacto`, `ventad`, `venta`, `ventaimporte`, `ventaformapagocobro`, `ventacont`, `ventabcpendienteaplica`, `ventadgastosarancelarios` |
| **6. Tesorería, Bancos, CxC/CxP y CFDI (BC / XMLCFDI)** | 42 | 1,237,589 | 382.25 | `xmlcfdimov`, `bc`, `bcpendienteaplicar`, `xmlcfdi`, `bcd`, `bctasaimpuesto1`, `bccont`, `bctasaimpuesto2` |
| **7. Contabilidad, Pólizas, Auxiliar y Saldos (CONT)** | 32 | 7,418,243 | 1,203.80 | `auxiliar`, `contd`, `acumulado`, `cont`, `contsimulador`, `acumuladom`, `auxiliarm`, `saldo` |
| **8. Activo Fijo, Mantenimiento, Calidad, CRM y Agrícola (AF / MANTTO / CALIDAD / AGRI)** | 68 | 99,306 | 14.24 | `afd`, `af`, `afcont`, `afartserie`, `afcarga`, `manttomarca`, `aftipo`, `manttomotivo` |
| **9. Catálogos Globales, Seguridad, Constructor UI y SAT** | 58 | 753,218 | 74.23 | `constructord`, `colonia`, `cpcolonia`, `movdavance`, `constructortbd`, `codigopostal`, `movrastreoresumen`, `constructorb` |
| **10. Folios y Consecutivos** | 26 | 442 | 0.52 | `bcconsecutivo`, `incidconsecutivo`, `invconsecutivo`, `cgconsecutivo`, `prodconsecutivo`, `contconsecutivo`, `ventaconsecutivo`, `manttoconsecutivo` |
| **11. Auditoría, Bitácora, Rastreo y Workflow** | 17 | 2,181,421 | 178.48 | `movlog`, `movrastreo`, `contgenerarlogd`, `aioslog`, `monedahist`, `contgenerarlog`, `incidsugerirlogd`, `pvsincrologd` |
| **12. Otros / Auxiliares de Sistema** | 91 | 132,379 | 25.44 | `vermovrastreod`, `vermovrastreoo`, `boprodserielotemov`, `fraccionarancelaria`, `busquedaavanzadab`, `boprodpresentacion`, `boprodpresupuestorastreo`, `cpclaveestaciones` |

### 2.1 Top 35 Tablas por Volumen Real en `mq_bio_organicos_analisis`

| # | Tabla | Módulo | Filas Aprox. | Tamaño (MB) | Cols | Llave Primaria (`PK`) |
|---:|---|---|---:|---:|---:|---|
| 1 | `nominaprevio` | Asistencia, Incidencias y Nómina / CFDI (ASISTE / INCID / NOM) | 15,580,825 | 1164.00 | 14 | `ID, Contacto, ClaveCalc` |
| 2 | `nominad` | Asistencia, Incidencias y Nómina / CFDI (ASISTE / INCID / NOM) | 7,086,433 | 905.66 | 10 | `RenglonID, ID` |
| 3 | `auxiliar` | Contabilidad, Pólizas, Auxiliar y Saldos (CONT) | 5,906,649 | 1010.97 | 18 | `ID` |
| 4 | `movlog` | Auditoría, Bitácora, Rastreo y Workflow | 1,356,953 | 77.64 | 7 | `IDInterno, ID, Modulo` |
| 5 | `auxiliaru` | Inventarios, Almacén, Series/Lotes y Producción (INV / PROD) | 1,343,905 | 300.39 | 21 | `ID` |
| 6 | `invd` | Inventarios, Almacén, Series/Lotes y Producción (INV / PROD) | 1,243,209 | 163.30 | 22 | `RenglonID, ID` |
| 7 | `contd` | Contabilidad, Pólizas, Auxiliar y Saldos (CONT) | 850,489 | 109.72 | 7 | `RenglonID, ID` |
| 8 | `movrastreo` | Auditoría, Bitácora, Rastreo y Workflow | 783,126 | 96.22 | 9 | `OID, OModulo, DID, DModulo` |
| 9 | `xmlcfdimov` | Tesorería, Bancos, CxC/CxP y CFDI (BC / XMLCFDI) | 467,857 | 158.98 | 5 | `IDInterno, ID, Modulo, Renglon` |
| 10 | `serieloteauxiliar` | Inventarios, Almacén, Series/Lotes y Producción (INV / PROD) | 373,366 | 113.31 | 14 | `ID` |
| 11 | `serielotemov` | Inventarios, Almacén, Series/Lotes y Producción (INV / PROD) | 363,364 | 23.59 | 12 | `ID, Modulo, RenglonID, Articulo, SerieLote` |
| 12 | `inv` | Inventarios, Almacén, Series/Lotes y Producción (INV / PROD) | 358,444 | 89.64 | 31 | `ID` |
| 13 | `nominacfdipercepciond` | Asistencia, Incidencias y Nómina / CFDI (ASISTE / INCID / NOM) | 256,662 | 17.56 | 7 | `ID, Contacto, Clave` |
| 14 | `acumulado` | Contabilidad, Pólizas, Auxiliar y Saldos (CONT) | 245,058 | 22.61 | 11 | `Cuenta, CentroCostos, Moneda, Periodo, Ejercicio, Modulo, Tipo, Sucursal, Empresa` |
| 15 | `acumuladou` | Inventarios, Almacén, Series/Lotes y Producción (INV / PROD) | 226,858 | 24.61 | 12 | `Articulo, Moneda, Periodo, Ejercicio, Modulo, Tipo, Almacen, Empresa` |
| 16 | `constructord` | Catálogos Globales, Seguridad, Constructor UI y SAT | 165,971 | 23.06 | 4 | `ID2` |
| 17 | `cont` | Contabilidad, Pólizas, Auxiliar y Saldos (CONT) | 163,836 | 31.56 | 22 | `ID` |
| 18 | `bc` | Tesorería, Bancos, CxC/CxP y CFDI (BC / XMLCFDI) | 154,836 | 45.59 | 69 | `ID` |
| 19 | `colonia` | Catálogos Globales, Seguridad, Constructor UI y SAT | 145,975 | 7.52 | 4 | `ID` |
| 20 | `cpcolonia` | Catálogos Globales, Seguridad, Constructor UI y SAT | 144,966 | 7.52 | 3 | `Clave, CodigoPostal, NombreAsentamiento` |
| 21 | `contsimulador` | Contabilidad, Pólizas, Auxiliar y Saldos (CONT) | 143,945 | 10.52 | 8 | `RenglonID, PID` |
| 22 | `bcpendienteaplicar` | Tesorería, Bancos, CxC/CxP y CFDI (BC / XMLCFDI) | 134,987 | 13.52 | 19 | `pid, ID` |
| 23 | `nominacfdideducciond` | Asistencia, Incidencias y Nómina / CFDI (ASISTE / INCID / NOM) | 133,235 | 8.52 | 7 | `ID, Contacto, Clave` |
| 24 | `xmlcfdi` | Tesorería, Bancos, CxC/CxP y CFDI (BC / XMLCFDI) | 132,333 | 135.28 | 75 | `(sin PK)` |
| 25 | `prodretrocesoconsumo` | Inventarios, Almacén, Series/Lotes y Producción (INV / PROD) | 131,201 | 12.55 | 9 | `ID, RenglonID, Material` |
| 26 | `bcd` | Tesorería, Bancos, CxC/CxP y CFDI (BC / XMLCFDI) | 125,457 | 7.52 | 6 | `RenglonID, ID` |
| 27 | `cgd` | Compras, Gastos y Proveedores (CG) | 121,981 | 40.11 | 49 | `RenglonID, ID` |
| 28 | `prodd` | Inventarios, Almacén, Series/Lotes y Producción (INV / PROD) | 114,432 | 23.58 | 16 | `RenglonID, ID` |
| 29 | `bctasaimpuesto1` | Tesorería, Bancos, CxC/CxP y CFDI (BC / XMLCFDI) | 106,816 | 10.55 | 17 | `ID, ModuloAplica, IDAplica, Tasa, Exento, Tasa2, Exento2, DiotExcluir, ObjetoImpuesto` |
| 30 | `movdavance` | Catálogos Globales, Seguridad, Constructor UI y SAT | 100,446 | 16.55 | 25 | `IDInterno` |
| 31 | `nominacontacto` | Asistencia, Incidencias y Nómina / CFDI (ASISTE / INCID / NOM) | 95,211 | 16.03 | 14 | `ID, Contacto` |
| 32 | `afd` | Activo Fijo, Mantenimiento, Calidad, CRM y Agrícola (AF / MANTTO / CALIDAD / AGRI) | 92,904 | 12.06 | 8 | `ID, Articulo, Serie` |
| 33 | `nominacfdiprocesar` | Asistencia, Incidencias y Nómina / CFDI (ASISTE / INCID / NOM) | 91,632 | 3.52 | 3 | `ID, Contacto` |
| 34 | `constructortbd` | Catálogos Globales, Seguridad, Constructor UI y SAT | 80,941 | 5.52 | 4 | `Tabla, Campo, Variable` |
| 35 | `prodmaterialmov` | Inventarios, Almacén, Series/Lotes y Producción (INV / PROD) | 79,023 | 8.56 | 12 | `IDInterno, ID, Articulo, Lote, Material` |

### 2.2 Inventario Completo de Tablas por Módulo (579 tablas base)

#### 1. RH, Expediente y Movimientos de Personal (AP) (7 tablas)
`ap` (6,301), `apd` (11,960), `contactobeneficiario`, `contactopersonal` (2,098), `departamento` (44), `personalcategoria`, `puesto` (86)

#### 2. Asistencia, Incidencias y Nómina / CFDI (ASISTE / INCID / NOM) (70 tablas)
`incid` (20,136), `incidd` (75,350), `incidsugerir` (69), `incidsugerird` (123), `nomina` (7,667), `nominaacumulado` (97), `nominaaplica` (59,272), `nominaarqueo` (46), `nominaarqueod` (38), `nominabccfdi` (215), `nominacalc` (14), `nominacalcd` (1,441), `nominacalcddepartamento` (2,099), `nominacalcdie`, `nominacfdicancelar`, `nominacfdiconcepto` (183), `nominacfdicontactoprevio`, `nominacfdideduccion` (101), `nominacfdideducciond` (133,235), `nominacfdihorasextra`, `nominacfdiincapacidad` (25), `nominacfdimov` (7), `nominacfdiotrospagosd` (23,015), `nominacfdipercepcion` (44), `nominacfdipercepciond` (256,662), `nominacfdiprocesar` (91,632), `nominacont` (7,197), `nominacontacto` (95,211), `nominacontratotipo` (7), `nominacontratotiposat` (11), `nominad` (7,086,433), `nominaexgenerabaja` (2), `nominafuncion` (60), `nominahorasextras`, `nominajornada` (3), `nominajornadad` (15), `nominajornadafecha` (282), `nominajornadasat` (9), `nominaorigenrecurso` (3), `nominaperiodicidadpago` (10), `nominaperiodo` (5), `nominaperiodoconfig` (198), `nominaperiodod` (4), `nominaprevio` (15,580,825), `nominariesgopuesto` (6), `nominatablaimpuesto` (5), `nominatablaimpuestod` (55), `nominatablatope` (8), `nominatablatoped` (76), `nominatablatopezona`, `nominatablatopezonad` (9), `nominatipo` (2), `nominatipohoras` (3), `nominatipoincapacidad` (4), `nominatipootropago` (5), `nominaturno` (10,069), `nominauma`, `nominavariablegrupo` (5), `nominavariablelista` (74), `nominavariablesreportes` (75), `nominavariablesreportesd` (52), `nominavariablevalor` (38,821), `nominazonaeconomica`, `personalasiste`, `personalasisteerror` (12), `personalasisteretardo`, `personalasistetipo` (21), `personalgrupo`, `personalreloj`, `progincid`

#### 3. Inventarios, Almacén, Series/Lotes y Producción (INV / PROD) (84 tablas)
`acumuladou` (226,858), `almacen` (121), `almacendistancia`, `almacensurtido`, `articulo` (4,082), `articulocategoria` (106), `articuloclasegasto` (4), `articulocomandaextra`, `articulocontacto`, `articulocosto` (9,287), `articulocostocapa`, `articulocostocapaauxiliar`, `articuloempresa` (2,532), `articulofamilia` (179), `articulogrupo` (13), `articuloimpuestotipo`, `articulokit`, `articulokitd`, `articulolinea` (56), `articuloposicion`, `articuloproductosservicios` (51,921), `articulorelacionado`, `articulounidad` (5,847), `artkitseleccion`, `artmaterial` (1,105), `auxiliaru` (1,343,905), `dimension`, `dimensionpropiedad` (2), `inv` (358,444), `invcont` (52,200), `invd` (1,243,209), `invmodificarex`, `invmodificarexr`, `invmodulotransfrastreo`, `invmovunir` (303), `invtransf`, `invtransfmat`, `invtransformacion` (2,469), `invtransformaciond` (4,644), `invtransformacionmat` (5,093), `invtransfserie` (4), `modelo`, `modeloarticulo`, `modelocolumna`, `modelorenglon`, `pedimento` (1,404), `pedimentoclave` (4), `pedimentoclaveregimen` (5), `pedimentod`, `pedimentoincoterm` (11), `pedimentorectificacion` (3), `pedimentoregimen` (2), `pedimentoremesa`, `pedimentoseleccion` (40), `prod` (77,512), `prodarticulooperacion`, `prodavanceentrada` (54,435), `prodcentro` (8), `prodcentrotipo` (3), `prodcont`, `prodd` (114,432), `prodestacion`, `prodlote` (2,074), `prodmaterialmov` (79,023), `prodoperacion` (3), `prodoperaciongrupo` (2), `prodoperacionmov`, `prodretrocesoconsumo` (131,201), `prodruta` (7), `prodrutad` (7), `prodrutamov` (11,996), `prodtransferenciamov` (68,950), `saldou` (15,496), `serielote` (47,549), `serieloteauxiliar` (373,366), `serielotemov` (363,364), `serielotepedimento` (8), `ubicacion` (8), `ubicacioncalendario`, `ubicaciongrupo` (3), `ubicacionmov`, `unidad` (297), `unidadclavesat` (2,510), `unidadtemp` (1,206)

#### 4. Compras, Gastos y Proveedores (CG) (23 tablas)
`cg` (58,175), `cgcont` (30,136), `cgcto` (5,467), `cgd` (121,981), `cgdcaducidadprov` (5), `cgdcentrocostoart` (4), `cggasto` (303), `cgimportacion` (215), `cgxml` (7,271), `cgxmlarchivo`, `cgxmlimportar`, `compitecategoriacto`, `compitecategoriactod`, `compitectodoctipo`, `compitehonorarios`, `compitehonorariosd`, `compiteotros`, `compiteotrosd`, `compitetarifazona` (3), `compiteusuario` (3), `compiteviaticos`, `compiteviaticosd`, `contactoproveedor` (5)

#### 5. Ventas, Facturación, POS y Embarques (VENTA / PV / EMB) (61 tablas)
`comanda`, `comandad`, `comandaformapagocobro`, `comandalistaespera` (2), `comandamesaunion`, `comandaopcion`, `comandaopcionlista` (3), `comandaopcionvalor` (4), `comandapersona` (4), `comandaterminal`, `comandaturno`, `contactocliente`, `contactoentrega` (358), `contactoentregadistancia`, `embarque` (2), `embarqued`, `embarqueestado` (4), `embarqueguia`, `embarquemov` (19), `embarquemovd`, `embarqueremolque`, `embarqueseleccionar` (231), `embarquetimbrado`, `listaprecios`, `listapreciosd`, `mesa` (4), `pc` (2), `pcd` (2), `pcredondeo` (3), `pv`, `pvcaja`, `pvd`, `pvformapagocobro` (9), `pvfpcdenom`, `pvreporte` (21), `pvreportefiltro` (63), `pvsincrodato`, `pvsincroid` (2), `pvsincrorecibo`, `pvterminal` (9), `pvventarefacturar`, `ruta`, `rutad`, `venta` (3,660), `ventabcaplica` (25), `ventabcpendienteaplica` (1,103), `ventacartaporte`, `ventacartaportemercancia`, `ventacartaporteubicacionde`, `ventacartaporteubicacionor`, `ventaconcluirnotaseleccion`, `ventacont` (2,692), `ventacontrato`, `ventacto` (8,654), `ventad` (6,900), `ventadgastosarancelarios` (375), `ventaformapagocobro` (2,996), `ventafpcdenom`, `ventaimporte` (2,997), `ventarefacturado` (10), `ventarefacturar`

#### 6. Tesorería, Bancos, CxC/CxP y CFDI (BC / XMLCFDI) (42 tablas)
`banco` (94), `bancosucursal`, `bc` (154,836), `bcaplicadif`, `bccont` (51,124), `bcd` (125,457), `bcdconceptos`, `bcformapagocobro` (1,507), `bcpendienteaplicar` (134,987), `bcsaldoinicial`, `bctasaimpuesto1` (106,816), `bctasaimpuesto2` (32,296), `bctasaiva`, `cajaformapagocobro`, `cajaformapagocobroespejo`, `cfdiactualizar` (1), `cfdibccomplemento` (301), `cfdibccomplementod` (833), `cfdicancelartimbre` (127), `cfdiconfirmacion`, `cfdiformapagocobro` (22), `cfdimensajes` (25), `cfdimoneda` (178), `cfdimotivocancelacion` (4), `cfdipeticionpendiente`, `cfdirespuesta` (218), `cfdisugerir` (2,020), `cfdiuuidrelacionado` (2,364), `cfdiventaaplicar` (19), `condicionpago` (24), `cuentabanco` (47), `diottipooperacion` (3), `diottipotercero` (3), `formapagocobro` (17), `formapagocobrocondicion` (3), `formapagocobroreferencia`, `fpcdenom`, `moneda` (4), `xmlcfdi` (132,333), `xmlcfdidividendos` (4), `xmlcfdimov` (467,857), `xmlcfdisugerir` (24,065)

#### 7. Contabilidad, Pólizas, Auxiliar y Saldos (CONT) (32 tablas)
`acumulado` (245,058), `acumuladom` (36,405), `auxiliar` (5,906,649), `auxiliarm` (32,048), `centrocostos` (66), `centrocostosd` (12), `centrocostosgrupo` (9), `cont` (163,836), `contacto` (3,650), `contactoaddenda`, `contactocontcuenta` (2,511), `contactodistancia`, `contactoempresa` (3,793), `contactomov`, `contactonominacuenta` (127), `contbcmovconcepto` (29), `contcuenta` (4,360), `contcuentaagrupador` (1,078), `contcuentadeducible` (8), `contcuentadiferenciatc`, `contcuentaempresa` (4,283), `contcuentaiva` (19), `contd` (850,489), `contgenerar` (71), `contgenerard` (373), `contmonitor` (1,100), `contratotipo` (2), `contsimulador` (143,945), `conttasaiva` (8), `proyecto` (5), `saldo` (13,097), `saldom` (5,212)

#### 8. Activo Fijo, Mantenimiento, Calidad, CRM y Agrícola (AF / MANTTO / CALIDAD / AGRI) (68 tablas)
`af` (2,122), `afartserie` (1,584), `afartserieamortizacion`, `afcarga` (660), `afcont` (1,854), `afd` (92,904), `aftipo` (34), `agrianalisisprevio`, `agrianalisispreviod`, `agrianalisispreviodt`, `agricategoriaantidoto`, `calidad`, `calidadconceptoevalm`, `calidadconceptoevaluacion`, `calidadcuadrillaespecial`, `calidadd`, `calidaddtareafechaconcluir`, `calidadequipotrabajo`, `calidadevaluacion`, `calidadevaluacionesd`, `calidadevaluacionesdd`, `calidadevento`, `calidadeventoc`, `calidadnorma`, `calidadplan`, `calidadpland`, `calidadrequisito`, `calidadrequisitod`, `calidadrequisitodtarea`, `calidadrequisitodtareae`, `calidadrequisitodtareau`, `competidor` (3), `crm`, `crmcompetidor`, `crmcontacto`, `crmd`, `crmplantilla`, `crmplantillacat`, `crmplantillad`, `crmplantilladact`, `crmpropuesta`, `crmpropuestad`, `fc`, `fcauxiliar`, `fcd`, `fcformapagocobro`, `fcserie`, `mantto` (10), `manttod` (9), `manttoequipo` (10), `manttoequiposerviciohist`, `manttoequipotipo` (8), `manttomarca` (37), `manttomotivo` (30), `manttomovequipo`, `manttoplan`, `manttopland`, `manttoservicio`, `manttosolref`, `manttotareagrales`, `manttotareagralesd`, `manttotecnologia` (11), `manttotipo` (30), `manttotipod`, `manttotipodtarea`, `manttotipodtareaart`, `ms`, `msevento`

#### 9. Catálogos Globales, Seguridad, Constructor UI y SAT (58 tablas)
`codigopostal` (59,459), `colonia` (145,975), `concepto` (180), `conceptomov` (204), `constructor` (554), `constructorb` (8,417), `constructorc` (127), `constructord` (165,971), `constructori` (2,257), `constructort` (33), `constructortb` (468), `constructortbd` (80,941), `constructortbi`, `constructorv` (153), `cpcolonia` (144,966), `empresa` (2), `empresaconfig` (260), `empresaconfigembarquemov` (5), `empresaconfiglista` (130), `empresaconfigmodulo` (7), `empresagrupo` (2), `empresasucursal` (2), `grupoconf` (18), `grupoconfd` (2,754), `grupoconfig` (434), `grupoconfiglista` (24), `grupoconfigpvreporte` (24), `impuestocuota` (19), `impuestotipo` (3), `linkcatalogo`, `linkmov`, `medio`, `menusistema` (417), `movautorizar`, `movclase` (131), `movdavance` (100,446), `movescaneo` (3), `movescaneod`, `movescaneoserielote`, `movlista` (323), `movlistaavance` (197), `movrastreoresumen` (34,440), `movreporte` (84), `movreservaauto`, `movvencido`, `pais` (250), `paisestado` (95), `submedio`, `sucursal` (2), `sucursalgrupo` (3), `usuario` (300), `usuariocajas`, `usuarioconfig` (2,100), `usuarioconfiglista` (7), `usuarioempresa` (514), `usuariosucursal` (510), `zona` (3), `zonaimpuesto` (4)

#### 10. Folios y Consecutivos (26 tablas)
`afconsecutivo` (5), `agrianalisispreviofolio`, `apconsecutivo` (9), `bcconsecutivo` (177), `calidadconsecutivo`, `calidadplanconsecutivo`, `cgconsecutivo` (40), `compitehonorariofolio`, `compiteotrofolio` (2), `compiteviaticofolio`, `contconsecutivo` (14), `crmconsecutivo`, `ctaconsecutivo` (3), `embarqueconsecutivo` (2), `fcconsecutivo` (2), `incidconsecutivo` (70), `invconsecutivo` (49), `invtransfconsecutivo` (2), `manttoconsecutivo` (13), `manttoplanconsecutivo`, `msconsecutivo`, `nominaconsecutivo` (13), `pcconsecutivo` (2), `prodconsecutivo` (21), `progincidconsecutivo` (4), `ventaconsecutivo` (14)

#### 11. Auditoría, Bitácora, Rastreo y Workflow (17 tablas)
`aioslog` (7,248), `contgenerarlog` (2,258), `contgenerarlogd` (28,932), `incidsugerirlog` (5), `incidsugerirlogd` (80), `incidsugerirproglog` (19), `log`, `monedahist` (2,713), `movautorizarusuario` (10), `movlog` (1,356,953), `movrastreo` (783,126), `nominaturnohist`, `nominaumahist` (9), `pvsincrolog` (20), `pvsincrologd` (21), `wf` (19), `wfusuario` (8)

#### 12. Otros / Auxiliares de Sistema (91 tablas)
`addenda` (2), `aduana`, `agentegrupo`, `aioskey`, `aiosreport` (110), `boarticuloprodclase` (2), `boarticuloprodclased` (14), `bopresentacion` (18), `boprodlote` (513), `boprodpresentacion` (6,638), `boprodpresuppresentacion` (605), `boprodpresupuesto` (31), `boprodpresupuestoc` (2), `boprodpresupuestod` (896), `boprodpresupuestorastreo` (6,468), `boprodserielotemov` (21,897), `busquedaavanzada` (473), `busquedaavanzadab` (10,725), `busquedaavanzadac` (3), `busquedaavanzadad` (5,187), `bymarticulopuntadas`, `clientegrupo` (2), `codigobarras`, `correo`, `cpclaveestaciones` (5,257), `cpclavetransporte` (4), `cpconfigautotransporte` (34), `cpconfigmaritima` (15), `cpcontenedormaritimo` (10), `cpderechospaso` (119), `cpfiguratransporte` (4), `cplocalidad` (664), `cpmaterialpeligroso` (1,000), `cpmunicipio` (2,463), `cpnumautnaviero` (297), `cppartetransporte` (12), `cptipocarga` (6), `cptipocarro` (11), `cptipocontenedor` (5), `cptipoembalaje` (59), `cptipoestacion` (3), `cptipopermiso` (26), `cptiporemolque` (31), `cptiposervicio` (4), `cptipotrafico` (4), `cptransporteaereo` (160), `cuadrillagrupo`, `cubicajemov`, `cuentacontgrupo` (3), `descuentoglobal`, `diafestivo`, `filtromovimientos`, `fraccionarancelaria` (11,895), `generadoretiqueta`, `horariotipo`, `icconfig`, `idioma`, `jamcocontactoprefijo` (4), `listaorden` (2), `mensaje` (718), `mensajemodulo`, `metodopago` (2), `modulo` (26), `motivo` (2), `nacionalidad` (7), `nivelacademico` (8), `nivelinteres` (4), `objetoimpuesto` (4), `parametrossdk`, `permisotipo` (2), `planeadorordencompra`, `proveedorgrupo` (3), `pruebacheck` (6), `recuperarcfdi`, `regimenfiscal` (19), `regimentipo` (11), `relacioncfditipo` (7), `relojchecador`, `relojterminal`, `repcontbalanzagridcuentas`, `retenciontipo` (8), `rfcanexo` (38), `supercache` (15), `tbidiomas` (6), `test` (4), `usocomprobante` (24), `vehiculo` (3), `vermovrastreod` (30,795), `vermovrastreoo` (24,966), `versionaios`, `wfd` (23)

---

## 3. Vistas, Folios/Consecutivos, Auditoría/Bitácora, Triggers, FKs y Relaciones Cabecera–Detalle

### 3.1 Tablas de Folios y Consecutivos (21 tablas `*consecutivo` + 4 `*folio`)

Todas las series de documentos se gobiernan centralmente por **`spMovFolioAsignar`** (24,100 caracteres) y **`spMovFolioValidar`** (5,754 caracteres). Cada tabla tiene llave compuesta `(Empresa, Sucursal, Mov)` (excepto `bcconsecutivo` que añade `CuentaBanco` y `ctaconsecutivo` por `TipoCta`):

| Tabla de Consecutivos | Módulo Asociado | Llave Primaria (`PK`) | Ejemplos de `Mov` / `Prefijo` / `Folio` observados |
|---|---|---|---|
| `afconsecutivo` | `AF` | `Mov, Sucursal, Empresa` | 5 series activas |
| `agrianalisispreviofolio` | `AGRIANALISISPREVIO` | `Mov, Sucursal, Folio, Empresa` | 0 series activas |
| `apconsecutivo` | `AP` | `Mov, Sucursal, Empresa` | Emp 1: `Alta` (`A`, 1822), `Baja` (`B`, 1425), `Cambio` (`C`, 2037), `ReIngreso` (9) · Emp 2: `Alta` (338), `Baja` (249), `Cambio` (338) |
| `bcconsecutivo` | `BC` | `Mov, Sucursal, CuentaBanco, Empresa` | 177 series por cuenta bancaria (`Gasto`, `Cheque Electronico`, `Compra`, `Deposito Electronico`, `Transferencia`, `Nota de Credito`) |
| `calidadconsecutivo` | `CALIDAD` | `Mov, Sucursal, Folio, Empresa` | 0 series activas |
| `calidadplanconsecutivo` | `CALIDADPLAN` | `Mov, Sucursal, Folio, Empresa` | 0 series activas |
| `cgconsecutivo` | `CG` | `Mov, Sucursal, Empresa` | 40 series (`Gasto`, `Compra`, `Orden de Compra`, `Requisicion Compra`, `Orden de Gasto`, `Compra AF`) |
| `compitehonorariofolio` | `COMPITEHONORARIO` | `Mov, Sucursal, Folio, Empresa` | 0 series activas |
| `compiteotrofolio` | `COMPITEOTRO` | `Mov, Sucursal, Folio, Empresa` | 2 series activas |
| `compiteviaticofolio` | `COMPITEVIATICO` | `Mov, Sucursal, Folio, Empresa` | 0 series activas |
| `contconsecutivo` | `CONT` | `Mov, Sucursal, Empresa` | Emp 1: `Diario` (`D`, 93036), `Egresos` (`E`, 31626), `Ventas` (`VTA`, 2136), `Ingresos` (`I`, 1835), `Cierre` (`C`, 46) · Emp 2: `Diario` (`D`, 20969), `Egresos` (`E`, 13740), `Ventas` (`VTA`, 2425), `Ingresos` (`I`, 2219) |
| `crmconsecutivo` | `CRM` | `Mov, Sucursal, Empresa` | 0 series activas |
| `ctaconsecutivo` | `CTA` | `TipoCta` | 3 series activas |
| `embarqueconsecutivo` | `EMBARQUE` | `Mov, Sucursal, Empresa` | 2 series activas |
| `fcconsecutivo` | `FC` | `Mov, Sucursal, Empresa` | 2 series activas |
| `incidconsecutivo` | `INCID` | `Mov, Sucursal, Empresa` | 70 series (`Compensacion` `COMP` 2764, `Faltas`, `Vacaciones Tomadas`, `Descanso Laborado` 693, `Despensa E` 677, `Incapacidad EG`, `Credito FONACOT`) |
| `invconsecutivo` | `INV` | `Mov, Sucursal, Empresa` | 49 series (`Consumo Especial` `CE` 67848, `Entrada` `E` 2382, `Entrada Diversa` 1567, `Consumo Materiales` `CM` 1159, `Merma Especial` `ME` 772, `Merma Natural` `MN` 36, `Entrada Berries`) |
| `invtransfconsecutivo` | `INVTRANSF` | `Mov, Sucursal, Empresa` | 2 series activas |
| `manttoconsecutivo` | `MANTTO` | `Mov, Sucursal, Empresa` | 13 series activas |
| `manttoplanconsecutivo` | `MANTTOPLAN` | `Mov, Sucursal, Empresa` | 0 series activas |
| `msconsecutivo` | `MS` | `Mov, Sucursal, Empresa` | 0 series activas |
| `nominaconsecutivo` | `NOMINA` | `Mov, Sucursal, Empresa` | Emp 1: `Nomina` (`NOM`, 4356), `Nomina Especial` (`NE`, 639), `Nomina Quincenal` (`NOMQ`, 188), `Liquidacion` (1336), `Aguinaldo` (`AG`, 117) · Emp 2: `Nomina` (512), `Nomina Quincenal` (166), `Liquidacion` (242) |
| `pcconsecutivo` | `PC` | `Mov, Sucursal, Empresa` | 2 series activas |
| `prodconsecutivo` | `PROD` | `Mov, Sucursal, Empresa` | 21 series (`Integracion de Costo`, `Orden de Produccion`, `Avance de Produccion`, `Entrada Produccion`) |
| `progincidconsecutivo` | `PROGINCID` | `Mov, Sucursal, Empresa` | 4 series activas |
| `ventaconsecutivo` | `VENTA` | `Mov, Sucursal, Empresa` | 14 series (`Factura NA`, `Factura EX`, `Factura NF`, `Factura ST`, `Factura`, `Nota Remision`, `Proforma`) |

### 3.2 Tablas de Auditoría, Bitácora, Rastreo y Flujo Documental

| Tabla | Filas Aprox. | `PK` | Función Exacta en Merqry |
|---|---:|---|---|
| `movlog` | 1,356,953 | `IDInterno, ID, Modulo` | Bitácora maestra de eventos sobre movimientos de los 13 módulos (`INV`: 583k, `BC`: 285k, `CONT`: 185k, `PROD`: 146k, `CG`: 113k, `INCID`: 23k, `NOM`: 7.9k, `AP`: 6.9k, `VENTA`: 4.1k). |
| `movrastreo` | 783,126 | `OID, OModulo, DID, DModulo` | Grafo origen→destino entre documentos (`OModulo/OID` → `DModulo/DID`): `INV→INV` (202k), `PROD→INV` (112k), `BC→CONT` (59k), `INV→CONT` (55k), `NOM→BC` (47k), `CG→BC` (34k), `CG→CONT` (32k), `INCID→NOM` (14k), `NOM→CONT` (7.8k), `NOM→AP` (1.5k). |
| `aioslog` | 7,248 | `ID` | Bitácora técnica de sesiones/operaciones del cliente Merqry. |
| `contgenerarlog` | 2,258 | `ID` | Cabecera de corridas de contabilización automática (`spContGenerar`). |
| `contgenerarlogd` | 28,932 | `IDInterno, ID` | Detalle de pólizas generadas o errores de contabilización automática (28,932 filas). |
| `monedahist` | 2,713 | `Moneda, Fecha` | Histórico automático de cambios de tipo de cambio alimentado por trigger `tgMonedaUpdate`. |
| `nominaumahist` | 9 | `FechaCambio` | Histórico automático de cambios de UMA alimentado por trigger `tgNominaUMAUpdate`. |
| `incidsugerirlog` | 5 | `ID` | Bitácora de generación masiva de incidencias (`spIncidGenerar`). |
| `wfusuario` | 8 | `Mov, Modulo, Estatus, ID, Usuario` | Usuarios asignados en flujo de autorización de movimientos (`WFEstado`/`WFUsuario`). |
| `movautorizarusuario` | 10 | `IDInterno` | Reglas de autorización por usuario/movimiento. |

### 3.3 Relaciones Clave Cabecera ↔ Detalle ↔ Auxiliar ↔ Contabilidad

Merqry sigue un patrón uniforme en todos los módulos operativos (la mayoría son relaciones **lógicas** por `(ID)` y `(Modulo, ModuloID)`, NO llaves foráneas físicas):

| Módulo | Cabecera | Detalle(s) | Consecutivo | Enlace Contable | Auxiliar / Saldos | Motor SP |
|---|---|---|---|---|---|---|
| **Personal (`AP`)** | `ap` (`ID`) | `apd` (`ID, Contacto`) + `contacto` / `contactopersonal` | `apconsecutivo` | *(sin póliza directa)* | `nominavariablevalor`, `nominaturno` | `spAP → spAPValidar → spAPAplicar` |
| **Incidencias (`INCID`)** | `incid` (`ID`) | `incidd` (`ID, RenglonID`) + `progincid`/`progincidd` | `incidconsecutivo` | *(vía Nómina)* | `auxiliar` (`Modulo='INCID', Tipo='VACAC'`), `saldo`, `acumulado` | `spIncid → spIncidValidar → spIncidAplicar` |
| **Nómina (`NOM`)** | `nomina` (`ID`) | `nominad` (`ID, RenglonID`), `nominaprevio` (`ID, Contacto, ClaveCalc`), `nominacontacto`, `nominaaplica`, `nominacfdi*` | `nominaconsecutivo` | `nominacont` → `cont`/`contd` | Genera `bc`/`bcd` (pagos/CxP), actualiza `incid`/`ap`/`contactopersonal` | `spNomina → spNominaValidar → spNominaAplicar` + `spContGenerarNomina` |
| **Inventarios (`INV`)** | `inv` (`ID`) | `invd` (`ID, RenglonID`), `serielotemov`, `serieloteauxiliar` | `invconsecutivo` | `invcont` → `cont`/`contd` | `auxiliaru` (`Tipo='INV'/'TR'`), `acumuladou`, `saldou`, `articulocosto` | `spInv → spInvValidar → spInvAplicar` + `spContGenerarInv` |
| **Producción (`PROD`)** | `prod` (`ID`) | `prodd`, `prodmaterialmov`, `prodretrocesoconsumo`, `prodavanceentrada` | `prodconsecutivo` | *(vía `INV`/`CONT`)* | `auxiliaru` (`Modulo='PROD'`), genera movimientos `INV` | `spProdValidar → spProdAplicar` |
| **Compras/Gastos (`CG`)** | `cg` (`ID`) | `cgd` (`ID, RenglonID`), `cggasto` | `cgconsecutivo` | `cgcont` → `cont`/`contd` | `auxiliaru` (`Modulo='CG'`), genera `bc` (CxP) | `spAplicar` + `spContGenerarCG` |
| **Ventas (`VENTA`)** | `venta` (`ID`) | `ventad` (`ID, RenglonID`), `ventaimporte` | `ventaconsecutivo` | `ventacont` → `cont`/`contd` | `auxiliaru` (`Modulo='VENTA'`), genera `bc` (CxC) + `xmlcfdi*` | `spInvAplicar` / `spBCGenerar` + `spContGenerarVenta` |
| **Tesorería/CxC/CxP (`BC`)** | `bc` (`ID`) | `bcd` (`ID, RenglonID`), `bcpendienteaplicar`, `bctasaimpuesto1` | `bcconsecutivo` | `bccont` → `cont`/`contd` | `auxiliar` (`Modulo='BC'`, `CTOSALDO`/`CBSALDO`/`CBSBC`), `saldo`, `acumulado` | `spBC` / `spBCGenerar` + `spContGenerarBC` |
| **Contabilidad (`CONT`)** | `cont` (`ID`) | `contd` (`ID, RenglonID`) + `contcuenta`, `centrocostos` | `contconsecutivo` | *(destino final)* | `auxiliar` (`Modulo='CONT'`, 5.78M filas), `acumulado`, `saldo` | `spCont → spContValidar → spContAplicar` + `spSaldo` |

### 3.4 Los 31 Triggers Activos en `mq_bio_organicos_analisis`

> **Hallazgo determinante:** Ninguno de los 31 triggers se ejecuta sobre tablas transaccionales de operación (`ap`, `incid`, `nomina`, `inv`, `cont`, `auxiliar`, `bc`, `cg`, `venta`). Todos mantienen metadatos del constructor de pantallas, propagación de configuraciones o bitácoras de tipo de cambio / UMA / variables de nómina.

| Trigger | Tabla | Evento | Tablas que Modifica |
|---|---|---|---|
| `tgConstructorBDelete` | `constructorb` | `AFTER DELETE` | `constructor` |
| `tgConstructorBInsert` | `constructorb` | `AFTER INSERT` | `constructor` |
| `tgConstructorBUpdate` | `constructorb` | `AFTER UPDATE` | `constructor` |
| `tgConstructorDDelete` | `constructord` | `AFTER DELETE` | `constructor` |
| `tgConstructorDInsert` | `constructord` | `AFTER INSERT` | `constructor` |
| `tgConstructorDUpdate` | `constructord` | `AFTER UPDATE` | `constructor` |
| `tgConstructorIDelete` | `constructori` | `AFTER DELETE` | `constructor` |
| `tgConstructorIInsert` | `constructori` | `AFTER INSERT` | `constructor` |
| `tgConstructorIUpdate` | `constructori` | `AFTER UPDATE` | `constructor` |
| `tgConstructorTBDDELETE` | `constructortbd` | `AFTER DELETE` | `constructortb` |
| `tgConstructorTBDInsert` | `constructortbd` | `AFTER INSERT` | `constructortb` |
| `tgConstructorTBDUpdate` | `constructortbd` | `AFTER UPDATE` | `constructortb` |
| `tgEmpresaInsert` | `empresa` | `AFTER INSERT` | `empresaconfig`, `nominavariablevalor` |
| `tgEmpresaUpdate` | `empresa` | `AFTER UPDATE` | `nominavariablevalor` |
| `tgMascaraCuentaCont` | `empresaconfig` | `AFTER UPDATE` | `constructord` |
| `tgEmpresaConfigListaInsert` | `empresaconfiglista` | `AFTER INSERT` | `empresaconfig` |
| `tgGrupoConfInsert` | `grupoconf` | `AFTER INSERT` | `grupoconfig` |
| `tgGrupoConfigListaInsert` | `grupoconfiglista` | `AFTER INSERT` | `grupoconfig` |
| `tgMonedaUpdate` | `moneda` | `AFTER UPDATE` | `monedahist` |
| `tgNominaUMAUpdate` | `nominauma` | `AFTER UPDATE` | `nominaumahist` |
| `tgNominaVariableListaDelete` | `nominavariablelista` | `AFTER DELETE` | `nominavariablevalor` |
| `tgNominaVariableListaInsert` | `nominavariablelista` | `AFTER INSERT` | `nominavariablevalor` |
| `tgNominaVariableListaUpdate` | `nominavariablelista` | `AFTER UPDATE` | `nominavariablevalor` |
| `tgPersonalCategoriaInsert` | `personalcategoria` | `AFTER INSERT` | `nominavariablevalor` |
| `tgPersonalCategoriaUpdate` | `personalcategoria` | `AFTER UPDATE` | `nominavariablevalor` |
| `tgPuestoInsert` | `puesto` | `AFTER INSERT` | `nominavariablevalor` |
| `tgPuestoUpdate` | `puesto` | `AFTER UPDATE` | `nominavariablevalor` |
| `tgSucursalInsert` | `sucursal` | `AFTER INSERT` | `nominavariablevalor` |
| `tgSucursalUpdate` | `sucursal` | `AFTER UPDATE` | `nominavariablevalor` |
| `tgUsuarioInsert` | `usuario` | `AFTER INSERT` | `usuarioconfig` |
| `tgUsuarioConfigListaInsert` | `usuarioconfiglista` | `AFTER INSERT` | `usuarioconfig` |

### 3.5 Las 26 Vistas (`VIEW`)

- **Inventarios y Costos (7):** `articulocostoempresa`, `articulodisponible`, `articuloexistencia`, `articuloresumen`, `articuloresumenunidad`, `artcantidadreserva`, `invaplica`
- **CFDI y Cumplimiento Fiscal (6):** `cfdiuuidasignado`, `xmlcfdibc`, `xmlcfdicg`, `xmlcfdicont`, `xmlcfdigasto`, `xmlcfdiventa`
- **Bancos, Compras y Ventas (8):** `bcaplica`, `bcsaldo`, `chequesbc`, `cgaplica`, `cgtransferir`, `ventaaplica`, `ventaneta`, `ventareservacioncierre`
- **Embarques, Activo Fijo, Mantto y Precios (5):** `embarqueasignado`, `embarquelista`, `afartseriev`, `manttoaplica`, `pclistacalcular`

### 3.6 Llaves Foráneas Físicas Relevantes (114 referencias en 100 constraints)

Las FKs físicas de MySQL cubren únicamente catálogos maestros y referencias de dimensiones/mantenimiento/calidad:
- **Personal/RH:** `contactopersonal.ContactoPersonal → contacto`, `contactobeneficiario.Contacto → contactopersonal`, `apd.Contacto → contacto`, `incidd.Contacto → contacto`, `nominacontacto.Contacto → contacto`, `nominad.ContactoD → contacto`, `nominacfdiconcepto → nominacalcd`, `nominajornada* → nominajornada`, `nominatabla* → nominatabla*`.
- **Inventarios/Producción:** `inv.(Almacen, AlmacenDestino) → almacen`, `invd.Articulo → articulo`, `invtransf*.Articulo → articulo`, `prod.Almacen → almacen`, `prodd.Articulo → articulo`, `articulounidad/kit → articulo/unidad`.
- **Contabilidad/Compras/Ventas:** `contd.Cuenta → contcuenta`, `contd.CentroCostos → centrocostos`, `cg.Contacto → contacto`, `cgd.(Articulo, CentroCostosD, ContactoD)`, `venta.(Almacen, Contacto)`, `ventad.(AlmacenD, Articulo)`.
- **Nota crítica:** **`nomina`/`nominad`, `inv`/`invd`, `cont`/`contd`, `ap`/`apd`, `incid`/`incidd`, `bc`/`bcd`, `cg`/`cgd`, `venta`/`ventad` NO tienen FK física cabecera→detalle**; borrar o insertar mal en cabecera/detalle deja registros huérfanos silenciosos si no se usa el motor `sp*`.

---

## 4. Análisis Profundo de los 4 Flujos Candidatos a Escritura Controlada Futura

> **Conclusión arquitectónica general:** En Merqry **NUNCA debe hacerse `INSERT`/`UPDATE` directo a tablas operativas como método final de afectación**, porque los triggers **NO** asignan folios, **NO** calculan costos, **NO** escriben en `auxiliar`/`auxiliaru`/`saldo`/`saldou`/`acumulado`/`acumuladou`, **NO** registran `movrastreo` ni `movlog`, y **NO** validan reglas fiscales/CFDI. Toda escritura controlada futura deberá seguir el patrón **Staging controlado (`SINAPLICAR`) + invocación autorizada de `spAplicar` (o procedimiento oficial del módulo) bajo transacción + validación previa de circuito** — o continuar usando paquetes de importación validados en paralelo hasta superar pruebas integrales en un espejo desechable de Merqry.

### 4.1 Flujo 1: Altas, Bajas y Cambios de Empleados IMSS (`AP` + `contacto`/`contactopersonal`)

- **Cómo opera realmente en Merqry:**
  - Un empleado vive en `contacto` (datos generales/RFC/CURP/nombre) + `contactopersonal` (36 columnas laborales: `PersonalEstatus`, `FechaAlta`, `FechaBaja`, `FechaAntiguedad`, `Departamento`, `Puesto`, `PersonalCategoria`, `MovNomina` [`Nomina` / `Nomina Quincenal`], `Periodo` [`Semanal` / `Quincenal`], `Jornada`, `ContratoTipo`, `SueldoDiario`, `SDI`, `NSS`, `TipoSueldo` [`Mixto`/`Fijo`], `CentroCostos`, `Empresa`, `PersonalSucursal`, cuentas bancarias) + `contactobeneficiario`.
  - Los movimientos laborales formales se registran como documentos en **`ap`** (`Mov` ∈ `Alta`, `Baja`, `Cambio`, `ReIngreso`; estatus `SINAPLICAR → CONCLUIDO / CANCELADO`) y su detalle **`apd`** (`ID, Contacto, Puesto, Departamento, SueldoDiario, SDI, FechaAlta, Periodo, Jornada, CentroCostos, ...`).
  - **Motor SP:** `spAplicar` → `spAP` → `spGeneralInicio` (`spMovFolioValidar`) → `spAPValidar` (`peAPValidar`) → **`spAPAplicar`** (12,919 chars):
    - `UPDATE`: `ap`, `apd`, `contacto`, `contactopersonal`.
    - `INSERT`: `nominaturno`, `nominavariablevalor`.
    - `CALL`: `spMovFolioAsignar` (actualiza `apconsecutivo`), `spNominaTurno`, `spGeneralFin`.
  - **Triggers que se disparan:** Ninguno en `ap`/`apd`/`contacto`/`contactopersonal`. Solo si se crean catálogos nuevos (`puesto`, `personalcategoria`, `sucursal`) se disparan `tgPuestoInsert`, `tgPersonalCategoriaInsert`, `tgSucursalInsert` escribiendo en `nominavariablevalor`.
  - **Hallazgo real en datos:** En `contactopersonal` hay **84 activos semanales + 28 quincenales** en Empresa 1 (`BIO`) y **26 activos semanales + 5 quincenales** en Empresa 2 (`NFA`), con mayoría en `TipoSueldo = 'Mixto'`.
- **Candados obligatorios contra mezcla de circuito Especial:**
  1. **Filtro duro de circuito en ERP v2:** Solo relaciones laborales con `circuito_pago = 'IMSS_MERQRY'`, `expediente.estatus = 'LISTO_MERQRY'` y `alta_imss_confirmada = TRUE` (NSS válido) pueden generar un borrador `ap` (`Estatus = 'SINAPLICAR'`).
  2. **Bloqueo duro de `ESPECIAL_CONTABILIDAD`:** Un trabajador de circuito Especial **jamás** puede existir como `Alta` en `ap`/`contactopersonal` (se mantiene en PostgreSQL + export exclusivo a Contabilidad).
  3. **Validación de empresa/sucursal exacta:** Mapear `BIO → Empresa=1, Sucursal=1` y `NFA → Empresa=2, Sucursal=2`; prohibir cruces.
  4. **Inmutabilidad del puesto nominal:** Nunca enviar `funciones_operativas_temporales` de campo hacia `apd.Puesto`/`contactopersonal.Puesto`; solo el puesto nominal aprobado por RH.

### 4.2 Flujo 2: Asistencia, Incidencias y Prenómina Semanal (`personalasiste` + `INCID` + `NOM`)

- **Cómo opera realmente en Merqry:**
  1. **Asistencia/Reloj:** `spPersonalAsiste` inserta en `personalasiste`, `personalasisteretardo`, `personalreloj` y actualiza `progincid` (errores van a `personalasisteerror`).
  2. **Incidencias (`INCID`):** Cabecera `incid` + detalle `incidd` (`Mov`: `Faltas`, `Compensacion`, `Vacaciones Tomadas`, `Prima Dominical`, `Descanso Laborado`, `Incapacidad EG`, `Despensa E`, `Credito FONACOT`, etc.). Motor: `spIncid → spIncidValidar → spIncidAplicar` (actualiza `contacto`, `incid`, `incidd`; llama `spMovFolioAsignar` sobre `incidconsecutivo` y `spSaldo` escribiendo en `auxiliar` [`Modulo='INCID', Tipo='VACAC'`], `saldo`, `acumulado`). `spIncidGenerar` genera incidencias en lote desde `progincid`/`incidsugerir`.
  3. **Nómina (`NOM`):** Cabecera `nomina` (`Empresa, Mov, Sucursal, Folio, Periodo, FechaDel, FechaAl, FechaPago, FormulaID`) + detalle `nominad` (7.08M filas: `ContactoD, Clave, Descripcion, Importe, Tipo, Cantidad`) + cálculo previo `nominaprevio` (15.58M filas) + `nominacontacto` (95k) + `nominaaplica` (59k, liga `INCID → NOM`: 14,872 vínculos en `movrastreo`).
     - **Motor SP:** `spNomina → spNominaValidar` (`nominasaldo`, `peNominaValidar`) → **`spNominaAplicar`** (25,475 chars):
       - `INSERT/UPDATE`: `nomina`, `nominaperiodod`, `nominabccfdi`, `contacto`, `contactopersonal`, `incid`/`incidd`, `ap`/`apd` (en liquidaciones), y `bc`/`bcd` vía **`spBCGenerar`** (genera cuentas por pagar/dispersión bancaria: 47,141 vínculos `NOM → BC`!).
       - `CALL`: `spMovFolioAsignar` (`nominaconsecutivo`), `spMovRastreo`, `spAplicar`, `spBCGenerar`, `spNominaTablaTope`.
     - **Contabilización:** `spContGenerar → spContGenerarNomina` genera `contgenerartemp` → `nominacont` → póliza `cont`/`contd` (7,872 vínculos `NOM → CONT`).
- **⚠️ TRAMPA CRÍTICA DETECTADA EN MERQRY (`Nomina Especial`):**
  - En `nominaconsecutivo` y `nomina` (Empresa 1 BIO), Merqry **YA TIENE** un movimiento llamado **`Mov = 'Nomina Especial'`** (`Prefijo = 'NE'`, `602` registros `CONCLUIDO`). En Merqry ese movimiento es una **nómina extraordinaria fiscal/CFDI** (ligada a `bc`, CFDI de nómina y pólizas `CONT`), **NO** corresponde al circuito operativo de pago en efectivo (`ESPECIAL_CONTABILIDAD`)!
  - **Regla de oro:** **JAMÁS** mapear `ESPECIAL_CONTABILIDAD` a `nomina.Mov = 'Nomina Especial'`. En escritura futura hacia Merqry, **únicamente** se deben enviar incidencias/prenómina de personal `IMSS_MERQRY` (con `Mov = 'Nomina'` semanal o `Mov = 'Nomina Quincenal'` y `incid` autorizadas) dejando la nómina en estatus **`PREVIO` o `SINAPLICAR`** para revisión y timbrado humano en Merqry, mientras el circuito `ESPECIAL_CONTABILIDAD` sale exclusivamente en su paquete separado hacia **Contabilidad**.

### 4.3 Flujo 3: Movimientos de Almacén e Insumos (`INV` + `PROD` + `auxiliaru`)

- **Cómo opera realmente en Merqry:**
  - Cabecera `inv` (358k filas: `Empresa, Mov, Sucursal, Folio, Almacen, AlmacenDestino, Concepto, CentroCostos, Proyecto, Estatus`) + detalle `invd` (1.24M filas: `Articulo, Cantidad, Costo, Unidad, Factor, ProdLote, ProdArticulo, CentroCostosD`) + trazabilidad por lote `serielotemov` (363k) / `serieloteauxiliar` (373k).
  - Movimientos reales dominantes en la operación actual: `Recibo Transferencia` (74k), `Transferencia` (74k), `Consumo Especial` (69k, prefijo `CE`), `Orden Transferencia` (68k), `Orden Consumo` (53k), `Salida` (2.4k), `Entrada` (2.4k), `Entrada Diversa` (1.7k), `Consumo Materiales` (996), `Merma Especial` (838), `Entrada Berries` (140).
  - **Motor SP:** `spInv` → **`spInvValidar`** (49,364 chars: valida existencias, kits, reservas, CFDI, precios) → **`spInvAplicar`** (65,406 chars — **el SP más complejo del ERP**):
    - `UPDATE/INSERT`: `inv`, `invd`, `almacen`, `articulo`, `cg`/`cgd`, `prod`/`prodd`, `venta`/`ventad`, `bc`/`bcd`, `movgasto`, `xmlcfdimov`.
    - `CALL`: `spInvArticuloCosto` / `spInvArticuloCostoGet` (capas de costo promedio/PEPS), `spInvArticuloSerieLote` / `Salida`, `spInvReservar`, **`spSaldo`** (inserta/actualiza `auxiliaru` [1.34M], `acumuladou` [226k], `saldou`), `spMovFolioAsignar` (`invconsecutivo`), `spMovRastreo`, `spProdAplicar`, `spBCGenerar`, `spGeneralFin`.
  - **Contabilización:** `spContGenerar → spContGenerarInv` vincula `invcont` → `cont`/`contd` (55,593 vínculos `INV → CONT`).
  - **Triggers:** Ninguno en `inv`/`invd`/`auxiliaru`.
- **Candados obligatorios para escritura controlada futura:**
  1. **Nunca alterar existencias/costos directo en `saldou`/`auxiliaru`:** toda entrada/consumo de agroquímicos, fertilizantes o empaque desde ERP v2 deberá insertarse en `inv`/`invd` en estado **`SINAPLICAR`** (como `Orden Consumo` o `Consumo Materiales`) con `Empresa`, `Almacen`, `Articulo`, `Unidad` y `CentroCostosD` previamente conciliados contra catálogo Merqry, y afectarse solo vía `spInv`/`spAplicar` (o revisión de almacén en Merqry).
  2. **Candado de empaque propio vs consignado (Mastronardi/SOLYSA):** distinguir explícitamente almacén de empaque consignado para no contaminar costo de inventario propio ni generar pólizas indebidas en `invcont`.
  3. **Idempotencia por `Referencia`:** grabar en `inv.Referencia` el UUID/folio único del ERP v2 y validar no-duplicidad antes de crear borrador.

### 4.4 Flujo 4: Pólizas y Auxiliar Contable (`CONT` + `auxiliar`/`acumulado`/`saldo`)

- **Cómo opera realmente en Merqry:**
  - Cabecera `cont` (163k filas: `Empresa, Mov` [`Diario`, `Egresos`, `Ventas`, `Ingresos`, `Cierre`], `Sucursal, Folio, FechaEmision, Moneda, TipoCambio, Cargos, Abonos, OrigenModulo, OrigenID`) + detalle `contd` (850k filas: `Cuenta` [FK a `contcuenta`], `CentroCostos` [FK a `centrocostos`], `Cargo`, `Abono`, `ReferenciaD`).
  - **Tablas puente de contabilización:** `afcont`, `bccont` (51k), `cgcont`, `invcont` (52k), `nominacont`, `ventacont` (evitan doble contabilización de un mismo documento origen).
  - **Motor SP:** `spCont` → `spContValidar` (cuadre cargos=abonos, ejercicio/periodo abierto, `peContValidar`) → **`spContAplicar`** (10,522 chars):
    - `UPDATE/DELETE`: `cont`, `contcuenta`, `centrocostos`, tablas puente `*cont`.
    - `CALL`: `spMovFolioAsignar` (`contconsecutivo`), `spMovRastreo`, **`spSaldo`** (inserta en `auxiliar` [5.78M filas `CONT`], actualiza `acumulado` [245k] y `saldo`), `spXMLCFDIAvanzar`, `spGeneralFin`.
  - **Triggers:** Ninguno en `cont`/`contd`/`auxiliar`/`acumulado`.
- **Candados obligatorios para escritura controlada futura y separación del circuito Especial:**
  1. **Prohibido escribir directo en `auxiliar`, `acumulado` o `saldo`:** siempre debe nacer una póliza cuadrada en `cont`/`contd` (`Cargos = Abonos`) y pasar por `spContValidar` + `spContAplicar`.
  2. **Centro de costos obligatorio por cultivo/empresa:** validar `contd.CentroCostos` contra `centrocostos` de la `Empresa` (`1=BIO`, `2=NFA`) y reglas de prorrateo **D18** (nunca mezclar cuentas NFA y BIO).
  3. **Separación absoluta del circuito Especial (`ESPECIAL_CONTABILIDAD`):**
     - La nómina `ESPECIAL_CONTABILIDAD` **nunca** se contabiliza vía `spContGenerarNomina` (ni entra a `nomina`/`nominacont`).
     - Su tratamiento contable queda estrictamente en manos de **Contabilidad** mediante el export separado (`POST /api/v1/merqry/exports/especial-contabilidad`), con cuentas/pólizas autorizadas explícitamente por Dirección/Contabilidad (nunca automáticas sin aprobación).
  4. **Prevención de doble contabilización:** antes de crear cualquier póliza desde ERP v2, verificar `cont.OrigenModulo`/`cont.OrigenID` y `cont.Referencia` + tablas puente `*cont` para impedir duplicados.

---

## 5. Matriz de Candados para Evaluar Escritura Controlada en el Futuro

| # | Candado Obligatorio | Qué Protege |
|---:|---|---|
| 1 | **Usuario MySQL dedicado con privilegios mínimos** (hoy: solo `SELECT`; futuro: solo staging/SPs whitelisteados, jamás `DDL` ni `DELETE` masivo) | Impide alteración de estructura o borrado accidental en Merqry. |
| 2 | **Separación dura `circuito_pago` (`IMSS_MERQRY` vs `ESPECIAL_CONTABILIDAD`) + lista negra de `Mov = 'Nomina Especial'`** | Garantiza que ningún trabajador o pago en efectivo contamine `ap`, `incid`, `nomina`, CFDI ni `bc` de Merqry. |
| 3 | **Entrada siempre en estado `SINAPLICAR` / `PREVIO` + idempotencia por `Referencia` (UUID ERP v2)** | Permite revisión humana antes de afectar saldos, evita folios duplicados ante reintentos de red. |
| 4 | **Afectación exclusivamente mediante motor nativo (`spAplicar` / `spAP` / `spIncid` / `spNomina` / `spInv` / `spCont`)** | Preserva folios (`*consecutivo`), `auxiliar`/`auxiliaru`, `saldo`/`saldou`, `acumulado`/`acumuladou`, `movrastreo` y `movlog`. |
| 5 | **Validación previa en espejo desechable (`mq_bio_organicos_analisis` clonado) + auditoría bilateral** | Verifica cuadre contable, existencias y CFDI antes de tocar producción. |
| 6 | **Feature flag `MERQRY_READONLY_MODE=True` por defecto en código** | Mientras Dirección no autorice formalmente un conector controlado, el ERP v2 rechaza en arranque y runtime cualquier intento de escritura contra Merqry. |
