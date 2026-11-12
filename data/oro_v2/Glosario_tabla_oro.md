# Glosario – Capa Oro v2 (`viajes_foraneos_oro.csv`)

Diccionario de datos de la capa oro vigente. Cada fila es **un viaje foráneo** identificado por `ID_VIAJE`.

| | |
|---|---|
| **Archivo** | `data/oro_v2/viajes_foraneos_oro.csv` |
| **Formato** | CSV separado por comas (`,`), UTF-8 |
| **Tamaño actual** | 71,967 viajes × 47 columnas |
| **Generado por** | `etl_oro.py`, con el catálogo de km de `distancias_v2.py` (`data/distancias_v2/catalogo_distancias_v2.csv`) |
| **Entrada** | `data/plata/viajes_foraneos_plata.csv` (capa plata, generada por `capa_plata.py`) |
| **Ventana** | Egresos del 2026-01-01 al 2026-09-01 (ene–ago completos; septiembre solo 23 viajes) |
| **Archivos que lo acompañan** | `viajes_rechazados.csv`, `rutas_pendientes.csv`, `capacidades_config.csv`, `reporte_calidad.json` |

Diferencias clave con el oro v1 (`data_engineer.py`):
- **No se borran outliers**: se marcan con `Flag_*`. Solo se rechazarían registros imposibles (hoy no hay ninguno).
- **No se imputan km**: si una ruta no tiene distancia confiable, el km queda vacío y `Km_Fuente` dice por qué.
- **El tipo de camión sale del texto declarado**, no del peso cargado.

Las columnas se dividen en dos bloques:

- **Columnas de la capa plata (1–16):** vienen de las tablas originales. `etl_oro.py` solo unifica grafías y convierte tipos.
- **Columnas calculadas (17–47):** las crea `etl_oro.py` o vienen del catálogo de distancias.

> **Los componentes no usan todas las columnas.** Clasifican la unidad con su propio mapeo de `FAMILIA_CAMION_DESC` y calculan su propia capacidad (NOM-012 − tara) en `ternium_comun.py`. Por eso `Nomenclatura_Inferida`, `Capacidad_Max_kg` y las columnas derivadas de esa capacidad (sección B.3) son **referencia del ETL**, no las cifras de los reportes.

---

## A. Columnas de la capa plata

### Tabla *Detalles viajes foráneos último año* (pasa antes por `limpieza_viajes_foraneos.py`)

| # | Columna | Tipo | Unidad | Descripción |
|---|---|---|---|---|
| 1 | `ID_VIAJE` | entero | – | Identificador único del viaje. Es la llave con la que se unieron las tres tablas. En origen se llamaba `ID Viaje`. |
| 2 | `Ciudad Destino` | texto | – | Ciudad a la que se entregó el material (524 distintas). `etl_oro.py` unifica grafías (mayúsculas, acentos, espacios) y corrige errores conocidos (p. ej. *Chilpancilgo* → *Chilpancingo*). Puede contener varios destinos separados por coma o una región con `+` (ver `Es_Multidestino` y `Es_Region`). |
| 3 | `ID Camión` | entero | – | Código interno del tipo de camión programado. |
| 4 | `Tipo Camión` | texto | – | Descripción del tipo de camión programado (p. ej. *Plataforma 2 ejes Neumática*). Sirve de respaldo para clasificar la unidad cuando `FAMILIA_CAMION_DESC` viene vacía. |
| 5 | `Programado (Peso)` | decimal | toneladas | Peso que se planeó cargar. Tiene errores de captura (máximo 1,116 t); ver `Flag_Discrepancia_Peso`. |

### Tabla *Tiempos Viajes Foráneos* (una fila por parada; se conserva una por viaje)

| # | Columna | Tipo | Unidad | Descripción |
|---|---|---|---|---|
| 6 | `PLANTA_ORIGEN` | texto | – | Planta de salida (20 distintas, p. ej. *Guerrero*). Junto con `Ciudad Destino` define la ruta. |
| 7 | `GRUPO_PLANTA_ORIGEN` | texto | – | Grupo de producto o planta: *Masivos* (34,220), *Largos* (16,300), *Revestidos* (10,853), *CEDIS* (5,798), *CeSer* (4,048), *Bodega* (748). Es lo más cercano a "producto" que hay en los datos. |
| 8 | `FECHA_EGRESO` | fecha-hora | – | Momento en que el camión salió de la planta. Define la ventana, el mes y la semana. |
| 9 | `FAMILIA_CAMION_DESC` | texto | – | Familia de camión registrada (p. ej. *PLATAFORMA 3 EJES NEUMATICA*). Es la base para clasificar la unidad. 5 viajes la tienen vacía (plataformas de 40 pies). |
| 10 | `FECHA_VIAJE_FINALIZADO` | fecha-hora | – | Momento en que el viaje se dio por terminado. **No es la llegada física**: en 37 % de los casos la placa sale a otro viaje antes de esta fecha. Parece un cierre administrativo. |

### Tabla *Viajes con Costos V2*

| # | Columna | Tipo | Unidad | Descripción |
|---|---|---|---|---|
| 11 | `Planta Origen` | texto | – | Código corto de la planta de origen (p. ej. *GUE*). |
| 12 | `Transportista` | texto | – | Empresa transportista, anonimizada (p. ej. *TRANSPORTISTA_003*; 136 distintas). En origen se llamaba `Nombre`. |
| 13 | `Desc TpoTrn` | texto | – | Tipo de transporte según la tabla de costos (p. ej. *2_EJES*). |
| 14 | `Peso Total` | entero | kg | **Peso real** transportado, según báscula. |
| 15 | `Monto total` | entero | MXN | Lo que se pagó por el viaje. |
| 16 | `Placas` | texto | – | Placas del tractocamión. En origen se llamaba `Placas tract`. Una placa no siempre es un solo camión físico. |

---

## B. Columnas calculadas

### 1. Duración del viaje

| # | Columna | Tipo | Unidad | Cálculo | Interpretación |
|---|---|---|---|---|---|
| 17 | `Tiempo_Viaje_Horas` | decimal | horas | `FECHA_VIAJE_FINALIZADO − FECHA_EGRESO` | Duración registrada del viaje. Como la fecha de finalización es administrativa, incluye esperas y cierres (máximo 786 h). Se usa para la velocidad implícita de la ruta, no como tiempo de manejo. |

### 2. Tipo de vehículo

| # | Columna | Tipo | Unidad | Descripción |
|---|---|---|---|---|
| 18 | `Nomenclatura_Inferida` | texto | – | Unidad según el texto de `FAMILIA_CAMION_DESC` (o `Tipo Camión` si la familia está vacía). Se aplica la **primera** regla que coincide. Nunca se reclasifica por el peso cargado. |
| 19 | `Capacidad_Max_kg` | decimal | kg | Carga útil supuesta de esa unidad. Sale de `CAPACIDADES_DEFAULT` en `etl_oro.py` (heredada del v1, **sin verificar** contra la NOM-012) o de `--capacidades`. Se guarda en `capacidades_config.csv`. Vacía en las plataformas de 40 pies. |

**Reglas y capacidades** (en orden de prioridad; el texto se normaliza a mayúsculas sin acentos):

| Prioridad | El texto contiene | `Nomenclatura_Inferida` | `Capacidad_Max_kg` | Viajes |
|---|---|---|---|---|
| 1 | `FULL` | T3-S2-R4 (Full) | 51,500 | 729 |
| 2 | `PORTACINTA` o `BIG COIL` | T3-S3 (Portacintas/Big Coil) | 38,500 | 6,242 |
| 3 | `53 PIES` | Plataforma larga 53 pies | 24,000 | 37 |
| 4 | `48 PIES` | Plataforma larga 48 pies | 25,000 | 420 |
| 5 | `40 PIES` | Plataforma larga 40 pies | (sin dato) | 5 |
| 6 | `TORTONETA` | Tortoneta | 12,000 | 283 |
| 7 | `TORTON` | Torton | 20,000 | 2,080 |
| 8 | `CAMIONETA` | Camioneta 3.5 | 3,500 | 624 |
| 9 | `CAMA BAJA` | Cama Baja Doble Piso | 35,000 | 170 |
| 10 | `HEAVY` | Heavy | 40,000 | 362 |
| 11 | `3 EJES` | T3-S3 (3 Ejes) | 38,500 | 47,059 |
| 12 | `2 EJES` | T3-S2 (2 Ejes) | 32,000 | 13,956 |
| – | Ninguna | SIN_CLASIFICAR | – | 0 |

> El "3 Ejes" de esta tabla incluye las **Cortina**, que los componentes excluyen por indicación de Ternium. El "Portacintas/Big Coil" junta las Big Coil (que los componentes sí analizan) con las Portacintas comunes (que excluyen).

### 3. Peso, capacidad y utilización (con la capacidad del ETL)

| # | Columna | Tipo | Unidad | Cálculo | Interpretación |
|---|---|---|---|---|---|
| 20 | `Programado_kg` | entero | kg | `Programado (Peso) × 1000` | Peso programado en kg, para compararlo con `Peso Total`. |
| 21 | `Discrepancia_Peso_kg` | decimal | kg | `Programado_kg − Peso Total` | **> 0**: se cargó menos de lo programado. **< 0**: más. Mediana 13 kg: casi siempre coinciden. |
| 22 | `Toneladas_Reales` | decimal | t | `Peso Total / 1000` | Peso real en toneladas. Es el peso que usan los componentes. |
| 23 | `Toneladas_Maximas` | decimal | t | `Capacidad_Max_kg / 1000` | Capacidad de la unidad en toneladas. |
| 24 | `Porcentaje_Utilizacion_Real` | decimal | % | `Peso Total / Capacidad_Max_kg × 100` | Qué tan lleno iba el camión por peso. Mediana ≈ 80 %. |
| 25 | `Capacidad_Sobra_kg` | decimal | kg | `Capacidad_Max_kg − Peso Total` | Capacidad no usada. Si es negativa, hubo sobrecarga. |
| 26 | `Excede_Capacidad` | booleano | – | `Porcentaje_Utilizacion_Real > 100` | El viaje cargó más que la capacidad asignada (421 viajes). Se marca, no se corrige. |
| 27 | `Costo_Ton_Real` | decimal | MXN/t | `Monto total / Toneladas_Reales` | Lo que se pagó por tonelada movida. |
| 28 | `Costo_Ton_Optimo` | decimal | MXN/t | `Monto total / Toneladas_Maximas` | Costo por tonelada si el camión hubiera ido lleno con la misma tarifa. |
| 29 | `Sobrecosto_Ton` | decimal | MXN/t | `Costo_Ton_Real − Costo_Ton_Optimo` | Dinero por tonelada que paga la capacidad vacía. **Supone consolidación total**: es una cota superior laxa, no un ahorro alcanzable. |
| 30 | `Flag_Discrepancia_Peso` | booleano | – | `|Discrepancia_Peso_kg| > 1,000` | El peso programado difiere más de 1 t del real (1,489 viajes). Casi siempre es un error de captura (p. ej. programados de 72 t o en unidades equivocadas). Los componentes 2 y 4 excluyen estos viajes cuando usan el peso programado. |

### 4. Distancia y su calidad

| # | Columna | Tipo | Unidad | Cálculo | Interpretación |
|---|---|---|---|---|---|
| 31 | `Kilometros_Ruta` | decimal | km | Del catálogo `catalogo_distancias_v2.csv`, por (`PLANTA_ORIGEN`, `Ciudad Destino`) | Distancia por carretera (OSRM) entre la ciudad de la planta y la del destino. **Nunca se imputa**: vacía en 1,126 viajes. |
| 32 | `Km_Fuente` | texto | – | Del catálogo | Origen del km: `osrm` (70,841), `region` (1,037), `multidestino` (88), `sin_geocodificar_destino` (1). También puede ser `estimado_haversine` (línea recta × 1.252) o `faltante` (ruta que no está en el catálogo); hoy no hay ninguno de los dos. |
| 33 | `Es_Multidestino` | booleano | – | `Ciudad Destino` contiene `,` | El viaje tiene varios destinos: no hay km de ruta (88 viajes). |
| 34 | `Es_Region` | booleano | – | `Ciudad Destino` contiene `+` | El destino es una región (p. ej. *CDMX+EDOMEX*), no un punto (1,037 viajes). |
| 35 | `Ruta_ID` | texto | – | `PLANTA_ORIGEN + ' \| ' + Ciudad Destino` | Identificador de la ruta (1,600 rutas). Es el conglomerado "ruta" del bootstrap y el efecto fijo de los modelos. |
| 36 | `Vel_Implicita_kmh` | decimal | km/h | `Kilometros_Ruta / mediana de Tiempo_Viaje_Horas de la ruta` | Velocidad promedio implícita, incluidas esperas. Sirve solo para detectar km imposibles. |
| 37 | `Km_Sospechoso` | booleano | – | `Vel_Implicita_kmh > 90` o `< 3`, o `Kilometros_Ruta < 5` | El km no es creíble para esa ruta (2,427 viajes). El viaje se conserva. |
| 38 | `Km_Estimado` | booleano | – | `Km_Fuente == 'estimado_haversine'` | El km es línea recta × factor de carretera, no una ruta real. Hoy son 0. |
| 39 | `Km_Confiable` | booleano | – | Hay km, y no es sospechoso ni estimado | Viajes cuyo km se puede usar en métricas por km (68,414, 95 %). |
| 40 | `Tonelada_Kilometro` | decimal | t·km | `Toneladas_Reales × Kilometros_Ruta` | Trabajo de transporte. Solo si `Km_Confiable`; si no, vacío (3,553 viajes). |
| 41 | `Costo_Ton_Km` | decimal | MXN/(t·km) | `Monto total / Tonelada_Kilometro` | Costo de mover una tonelada un kilómetro. Solo con km confiable. Mediana ≈ 1.77 MXN. Baja con la distancia (la tarifa tiene un componente fijo): compara rutas dentro de bandas de distancia. |
| 42 | `Costo_Ton_Km_Bruto` | decimal | MXN/(t·km) | `Monto total / (Toneladas_Reales × Kilometros_Ruta)` | Igual que el anterior, pero sin filtrar km sospechosos ni estimados. Es para análisis de sensibilidad. Vale infinito en los 2 viajes con 0 km. |

### 5. Marcas de outliers (se marcan, no se eliminan)

| # | Columna | Tipo | Cálculo | Interpretación |
|---|---|---|---|---|
| 43 | `Flag_Outlier_Costo_Ton` | booleano | Puntaje z robusto (z-MAD) de `log(Costo_Ton_Real)` dentro de su `Ruta_ID`; se marca si `|z| > 5` | Costo por tonelada extremo para su ruta (1,120 viajes). Solo se evalúa en rutas con ≥ 8 viajes; el MAD tiene un piso de 0.05 porque muchas rutas tienen tarifa casi fija. |
| 44 | `Flag_Outlier_Tiempo` | booleano | Lo mismo con `log(Tiempo_Viaje_Horas)` | Duración extrema para su ruta (66 viajes). |
| 45 | `Flag_Util_Baja_70` | booleano | `Porcentaje_Utilizacion_Real < 70` | El camión fue a menos del 70 % de la capacidad del ETL (15,088 viajes). Reemplaza a `Ineficiencia_Capacidad` del v1. |

### 6. Periodo

| # | Columna | Tipo | Formato | Interpretación |
|---|---|---|---|---|
| 46 | `Mes_Egreso` | texto | `AAAA-MM` | Mes de `FECHA_EGRESO`. Julio (6,887) tiene menos viajes que el resto (~9,000): posible hueco de extracción, por confirmar. Septiembre: 23 viajes. |
| 47 | `Semana_Egreso` | texto | `AAAA-MM-DD/AAAA-MM-DD` | Semana de `FECHA_EGRESO` (lunes a domingo). Se usa en el bootstrap y en la disponibilidad semanal de flota. |

---

## C. Limpieza y validaciones de `etl_oro.py`

1. **Valida el esquema**: falla si a la plata le falta alguna columna requerida.
2. **Normaliza textos**: quita espacios en planta, destino, transportista y familia; unifica las grafías de `Ciudad Destino` y `PLANTA_ORIGEN` (se queda con la más frecuente entre las que solo difieren en mayúsculas, acentos o espacios) y corrige destinos con errores conocidos.
3. **Rechaza solo registros imposibles** y los manda a `viajes_rechazados.csv` con su motivo: `ID_VIAJE` nulo o duplicado, fecha inválida, tiempo de viaje ≤ 0, peso nulo o ≤ 0, monto nulo o ≤ 0, origen o destino nulo. **Hoy no se rechaza ningún viaje.**
4. **Marca, no borra**: outliers (`Flag_Outlier_*`), discrepancias de peso, exceso de capacidad, km sospechosos y baja utilización.
5. **Comprueba que nada se pierda**: viajes de oro + rechazados = viajes de plata.

## D. Rangos de referencia (versión actual)

| Columna | Mínimo | Mediana | Máximo |
|---|---|---|---|
| `Peso Total` (kg) | 713 | 30,010 | 51,362 |
| `Programado (Peso)` (t) | 1.2 | 30.4 | 1,116 |
| `Monto total` (MXN) | 1,529 | 22,237 | 185,000 |
| `Tiempo_Viaje_Horas` | 0.2 | 43.5 | 786.0 |
| `Porcentaje_Utilizacion_Real` (%) | 1.9 | 80.4 | 139.5 |
| `Costo_Ton_Real` (MXN/t) | 56 | 808 | 61,975 |
| `Kilometros_Ruta` (km) | 0 | 476 | 4,183 |
| `Costo_Ton_Km` (MXN/t·km, km confiable) | 0.10 | 1.77 | 271.6 |

Los valores extremos (pesos programados de más de 1,000 t, costos por tonelada de más de 60,000 MXN) siguen en el archivo a propósito: están marcados con `Flag_Discrepancia_Peso` o `Flag_Outlier_*` para que cada análisis decida qué hacer con ellos.

## E. Notas sobre el archivo actual

- **Formato de fechas**: el CSV del repo se guardó con Excel, así que las fechas aparecen como `1/8/2026 16:57` (mes/día/año, sin segundos). Si se vuelve a correr `etl_oro.py`, quedan como `2026-01-08 16:57:00`. Los componentes leen bien ambos formatos.
- **Rutas a Baja California Sur** (29 viajes): el km de OSRM es por tierra (~3,300–4,200 km). Si cruzan en ferry, el km real es menor. Está pendiente de decidir.
- **Capacidades**: `capacidades_config.csv` tiene `Verificado_NOM012 = False` en todas las unidades.
