# Glosario – Capa Oro (`viajes_foraneos_oro.csv`)

Diccionario de datos de la tabla final del pipeline. Cada fila es **un viaje foráneo** identificado por `ID_VIAJE`.

| | |
|---|---|
| **Archivo** | `data/plata/viajes_foraneos_oro.csv` |
| **Formato** | CSV separado por comas (`,`), UTF-8 |
| **Tamaño actual** | 55,388 viajes × 32 columnas |
| **Generado por** | `data_engineer.py` + `imputación_rutas_capa_oro.ipynb` |
| **Entrada** | `data/plata/viajes_foraneos_plata.csv` (capa plata) |

Las columnas se dividen en dos bloques:

- **Columnas heredadas (1–16):** vienen de las tablas originales a través de la capa plata.
- **Columnas calculadas (17–32):** se crean en `data_engineer.py` y en el notebook de imputación.

---

## A. Columnas heredadas de la capa plata

### Tabla *Detalles viajes foráneos último año*

| # | Columna | Tipo | Unidad | Descripción |
|---|---|---|---|---|
| 1 | `ID_VIAJE` | entero | – | Identificador único del viaje. Es la llave con la que se unieron las tres tablas. |
| 2 | `Ciudad Destino` | texto | – | Ciudad a la que se entregó el material. |
| 3 | `ID Camión` | entero | – | Código interno del tipo de camión programado. |
| 4 | `Tipo Camión` | texto | – | Descripción del tipo de camión programado (p. ej. *Plataforma 2 ejes Neumática*). |
| 5 | `Programado (Peso)` | decimal | toneladas | Peso que se planeó cargar en el viaje. |

### Tabla *Tiempos Viajes Foráneos*

| # | Columna | Tipo | Unidad | Descripción |
|---|---|---|---|---|
| 6 | `PLANTA_ORIGEN` | texto | – | Nombre de la planta de salida (p. ej. *Guerrero*). Junto con `Ciudad Destino`, define la ruta. |
| 7 | `GRUPO_PLANTA_ORIGEN` | texto | – | Grupo de producción al que pertenece cada planta (p. ej. *Masivos*, *Revestidos*). |
| 8 | `FECHA_EGRESO` | fecha-hora | – | Momento en que el camión salió de la planta. |
| 9 | `FAMILIA_CAMION_DESC` | texto | – | Familia de camión registrada en el sistema. Contiene errores de captura (ver sección C). |
| 10 | `FECHA_VIAJE_FINALIZADO` | fecha-hora | – | Momento en que el viaje se dio por terminado. |

### Tabla *Viajes con Costos V2*

| # | Columna | Tipo | Unidad | Descripción |
|---|---|---|---|---|
| 11 | `Planta Origen` | texto | – | Código corto de la planta de origen (p. ej. *GUE*). |
| 12 | `Transportista` | texto | – | Empresa transportista, anonimizada (p. ej. *TRANSPORTISTA_003*). Originalmente se llamaba `Nombre`. |
| 13 | `Desc TpoTrn` | texto | – | Tipo de transporte según la tabla de costos (p. ej. *2_EJES*). |
| 14 | `Peso Total` | decimal | kg | **Peso real** transportado, según báscula. |
| 15 | `Monto total` | entero | MXN | Lo que se pagó por el viaje. |
| 16 | `Placas` | texto | – | Placas del tractocamión. Originalmente se llamaba `Placas tract`. |

---

## B. Columnas calculadas

### 1. Duración del viaje

| # | Columna | Tipo | Unidad | Cálculo | Interpretación |
|---|---|---|---|---|---|
| 17 | `Tiempo_Viaje_Horas` | decimal | horas | `FECHA_VIAJE_FINALIZADO − FECHA_EGRESO` | Duración total del viaje. Sirve como indicador de la distancia y la complejidad de la ruta. |

### 2. Peso programado vs. peso real

| # | Columna | Tipo | Unidad | Cálculo | Interpretación |
|---|---|---|---|---|---|
| 18 | `Programado_kg` | decimal | kg | `Programado (Peso) × 1000` | Peso programado convertido a kg, para compararlo con `Peso Total`. |
| 19 | `Discrepancia_Peso_kg` | decimal | kg | `Programado_kg − Peso Total` | **> 0**: viajó menos de lo planeado. **< 0**: viajó más de lo planeado. **= 0**: coincide. |
| 20 | `Ineficiencia_Capacidad` | booleano | – | `Discrepancia_Peso_kg > 0` | `True` si se cargó menos de lo programado. |

> Después del filtro de outliers, la discrepancia queda entre −60 y +100 kg. En la práctica, **lo programado casi siempre coincide con lo cargado**. La ineficiencia se ve en la comparación contra la **capacidad del camión** (sección 4), no contra lo programado.

### 3. Tipo de vehículo inferido

`FAMILIA_CAMION_DESC` contiene errores de captura graves (p. ej. camiones de 2 ejes registrados con más de 70 t). Por eso `data_engineer.py` asigna una unidad con **reglas en orden de prioridad**: se aplica la primera que se cumple. Los límites de peso se basan en la NOM-012-SCT-2.

| # | Columna | Tipo | Unidad | Descripción |
|---|---|---|---|---|
| 21 | `Nomenclatura_Inferida` | texto | – | Unidad que corresponde al viaje según las reglas de abajo. |
| 22 | `Capacidad_Max_kg` | entero | kg | Carga útil máxima de la unidad inferida (peso bruto permitido menos tara). |

Tara = Peso propio del vehículo

**Reglas y capacidades** (en orden de prioridad):

| Prioridad | Condición | `Nomenclatura_Inferida` | `Capacidad_Max_kg` | Viajes* |
|---|---|---|---|---|
| 1 | Programado > 38,500 kg **o** la familia contiene "FULL" | T3-S2-R4 (Full) | 51,500 | 815 |
| 2 | Familia contiene "PORTACINTA" o "BIG COIL" | T3-S3 (Portacintas/Big Coil) | 38,500 | 5,659 |
| 3 | Familia contiene "48 PIES" | Plataforma larga 48 pies | 25,000 | 343 |
| 4 | Familia contiene "53 PIES" | Plataforma larga 53 pies | 24,000 | 2 |
| 5 | Familia contiene "TORTONETA" | Tortoneta | 12,000 | 250 |
| 6 | Familia contiene "TORTON" (sin "TORTONETA") | Torton | 20,000 | 1,674 |
| 7 | Familia contiene "CAMIONETA 3.5" | Camioneta 3.5 | 3,500 | 0 |
| 8 | Familia contiene "CAMA BAJA" | Cama Baja Doble Piso | 35,000 | 167 |
| 9 | Familia contiene "HEAVY" | Heavy | 40,000 | 34 |
| 10 | Programado > 32,000 kg **o** la familia contiene "3 EJES" | T3-S3 (3 Ejes) | 38,500 | 37,621 |
| 11 | Familia contiene "2 EJES", o ninguna regla anterior | T3-S2 (2 Ejes) | 32,000 | 8,823 |

\* Conteo en la versión actual de la capa oro.

### 4. Utilización de la capacidad

| # | Columna | Tipo | Unidad | Cálculo | Interpretación |
|---|---|---|---|---|---|
| 23 | `Porcentaje_Utilizacion_Real` | decimal | % | `Peso Total / Capacidad_Max_kg × 100` | Qué tan lleno iba el camión por peso. **100%** = lleno. **> 100%** = sobrecarga respecto al límite asignado. Mediana ≈ 81%. |
| 24 | `Capacidad_Sobra_kg` | decimal | kg | `Capacidad_Max_kg − Peso Total` | Kilos de capacidad que no se usaron. Si es negativo, hay sobrecarga. |
| 25 | `Toneladas_Reales` | decimal | t | `Peso Total / 1000` | Peso real en toneladas. |
| 26 | `Toneladas_Maximas` | decimal | t | `Capacidad_Max_kg / 1000` | Capacidad de la unidad en toneladas. |

> **Sugerencia:** cruza `Porcentaje_Utilizacion_Real` con `GRUPO_PLANTA_ORIGEN` para ubicar ineficiencias en materiales densos, como los revestidos.

### 5. Valoración económica

| # | Columna | Tipo | Unidad | Cálculo | Interpretación |
|---|---|---|---|---|---|
| 27 | `Costo_Ton_Real` | decimal | MXN/t | `Monto total / Toneladas_Reales` | Lo que se pagó por cada tonelada efectivamente movida. |
| 28 | `Costo_Ton_Optimo` | decimal | MXN/t | `Monto total / Toneladas_Maximas` | Lo que habría costado cada tonelada si el camión hubiera ido al 100% de su capacidad. |
| 29 | `Sobrecosto_Ton` | decimal | MXN/t | `Costo_Ton_Real − Costo_Ton_Optimo` | **Métrica principal de la propuesta financiera.** Es el dinero perdido por tonelada por no llenar el camión. Si es negativo, hubo sobrecarga. |

> Para estimar el sobrecosto total de un viaje: `Sobrecosto_Ton × Toneladas_Reales`.

### 6. Distancia y costo por tonelada-kilómetro

| # | Columna | Tipo | Unidad | Cálculo | Interpretación |
|---|---|---|---|---|---|
| 30 | `Kilometros_Ruta` | decimal | km | Se toma de `catalogo_distancias.csv` (Nominatim + OSRM) por (`PLANTA_ORIGEN`, `Ciudad Destino`). Si falta, se imputa con la mediana por ciudad destino → por planta origen → global. | Distancia en carretera de la ruta. |
| 31 | `Tonelada_Kilometro` | decimal | t·km | `Toneladas_Reales × Kilometros_Ruta` | Trabajo de transporte realizado. |
| 32 | `Costo_Ton_Km` | decimal | MXN/(t·km) | `Monto total / Tonelada_Kilometro` | Costo de mover una tonelada un kilómetro. Permite comparar rutas de distinta longitud. Mediana ≈ 1.54 MXN. |

> ⚠️ **En la versión actual del archivo, 17,666 viajes (≈ 32%) tienen vacíos `Kilometros_Ruta`, `Tonelada_Kilometro` y `Costo_Ton_Km`.** Eso significa que `data_engineer.py` se volvió a correr sin correr después `imputación_rutas_capa_oro.ipynb`. Hay que ejecutar el notebook para completarlos.

---

## C. Limpieza aplicada en la capa oro

1. **Eliminación de nulos críticos:** se descartan los viajes sin `Tiempo_Viaje_Horas`, `Discrepancia_Peso_kg` o `Costo_Ton_Real` (por ejemplo, viajes con peso real 0).
2. **Filtro de outliers por IQR:** se eliminan los viajes fuera de `[Q1 − 1.5·IQR, Q3 + 1.5·IQR]` en estas columnas, una tras otra:
   - `Tiempo_Viaje_Horas` (quita, por ejemplo, viajes de más de 700 h por errores de sistema),
   - `Discrepancia_Peso_kg`,
   - `Sobrecosto_Ton`.

El filtro de outliers **no** se aplica a `Costo_Ton_Km`, porque se calcula antes de imputar las distancias. Por eso puede tener valores extremos (máximo ≈ 618 MXN/t·km, casi siempre en rutas muy cortas).

## D. Rangos de referencia (versión actual)

| Columna | Mínimo | Mediana | Máximo |
|---|---|---|---|
| `Peso Total` (kg) | 2,920 | 30,875 | 51,362 |
| `Monto total` (MXN) | 1,529 | 20,061 | 185,000 |
| `Tiempo_Viaje_Horas` | 0.2 | 35.0 | 218.2 |
| `Porcentaje_Utilizacion_Real` (%) | 9.1 | 81.4 | 119.1 |
| `Costo_Ton_Real` (MXN/t) | 56 | 689 | 5,343 |
| `Sobrecosto_Ton` (MXN/t) | −235 | 129 | 566 |
| `Kilometros_Ruta` (km) | 1.5 | 499 | 4,054 |
