# Proyecto Ternium – Eficiencia en viajes foráneos

Análisis de los viajes foráneos de Ternium: qué tan llenos van los camiones, cuánto cuesta la capacidad que viaja vacía y cuánto se ahorraría si cada carga fuera en la unidad adecuada (*right-sizing*).

Los datos se procesan con una arquitectura **Medallion** de tres capas. La capa oro vigente es la **v2**.

| Capa | Qué contiene | Dónde vive |
|---|---|---|
| **Bronce** | Archivos originales entregados por Ternium | `data/*.csv` |
| **Plata** | Las 3 tablas principales unidas, una fila por viaje, tipos de dato corregidos (71,967 viajes) | `data/plata/viajes_foraneos_plata.csv` |
| **Oro v2 (vigente)** | Plata + capacidad, costo, km validados y marcas de calidad. No borra outliers: los marca | `data/oro_v2/viajes_foraneos_oro.csv` |
| Oro v1 (heredada) | Versión anterior (55,388 viajes): borraba outliers con IQR e imputaba km con medianas. Se conserva solo como referencia | `data/plata/viajes_foraneos_oro_ANTIGUO.csv` |

> El significado de cada columna del oro v2 está en [data/oro_v2/Glosario_tabla_oro.md](data/oro_v2/Glosario_tabla_oro.md).

> **Ventana de los datos:** egresos del 2026-01-01 al 2026-08-31 (ocho meses). Septiembre tiene solo 23 viajes y queda fuera. Julio tiene menos viajes que el resto (~6,900 contra ~9,000) y falta confirmar si es un hueco de extracción.

---

## Flujo del proyecto

```
data/*.csv  (BRONCE)
   │
   │  ── data_processing/ ──
   ▼  1. limpieza_viajes_foraneos.py    (Detalles: .xlsx → .csv limpio)
   ▼  2. capa_plata.py                  (une Detalles + Tiempos + Costos)
data/plata/viajes_foraneos_plata.csv           (PLATA, separador ";")
   │
   │  3. distancias_v2.py   ← config/plantas.csv, config/destinos_canonicos.csv, caché en data/distancias_v2/
   │        └─▶ data/distancias_v2/catalogo_distancias_v2.csv   (km por ruta)
   ▼  4. etl_oro.py
data/oro_v2/viajes_foraneos_oro.csv            (ORO v2) + rechazados, rutas pendientes, capacidades, reporte
   │
   │  ── analisis_estadistico_IA/ ──
   │  ternium_comun.py: universo, capacidades, bootstrap y estilo compartidos
   │  componente_3_optimizacion.py: optimizador MILP compartido (copia de la sección 6 del Componente 2)
   │
   ├─▶ componente_1.ipynb   → línea base: utilización, costo de la capacidad ociosa, right-sizing por reglas
   ├─▶ componente_2.ipynb   → DAG, efecto causal del tipo de camión, modelo de elección, optimización y simulador
   ├─▶ componente_3.ipynb   → comparación de enfoques (actual, heurística, MILP, consolidación) y casos raros
   └─▶ componente_4.py      → ahorro creíble: cascada de supuestos, escenarios, anualización y piloto
                              └─▶ resultados_ternium/componente_4_*
```

---

## Cómo ejecutarlo

### 1. Instalar dependencias

El proyecto usa [Poetry](https://python-poetry.org/) y Python ≥ 3.13.

```bash
poetry install --no-root
```

**Alternativa sin Poetry (venv + pip):**

```powershell
py -m venv venv
venv\Scripts\activate
python -m pip install -r requirements.txt ipykernel
```

Después, en VS Code, selecciona `venv\Scripts\python.exe` como kernel de los notebooks. Si aparece `ModuleNotFoundError` (por ejemplo, `No module named 'seaborn'`), la dependencia no está instalada en el kernel que estás usando.

### 2. Correr los componentes (lo normal)

Los datos de `data/oro_v2/` ya están en el repo, así que **no hace falta correr el pipeline** para trabajar con los componentes. En este orden:

1. [componente_1.ipynb](analisis_estadistico_IA/componente_1.ipynb)
2. [componente_2.ipynb](analisis_estadistico_IA/componente_2.ipynb). La celda de estabilidad de la sección 6.2 tarda ~11 min (400 réplicas del optimizador).
3. [componente_3.ipynb](analisis_estadistico_IA/componente_3.ipynb)
4. `python analisis_estadistico_IA/componente_4.py`. Escribe tablas, figuras, `componente_4_salida.txt` y `componente_4_documento.html` en `resultados_ternium/`.

Los notebooks viven en `analisis_estadistico_IA/`, pero `data/`, `config/` y `resultados_ternium/` están en la raíz. Por eso la primera celda de cada notebook cambia el directorio de trabajo a la raíz y agrega `analisis_estadistico_IA/` y `data_processing/` al path de Python. Los scripts (`componente_4.py` y los de `data_processing/`) hacen lo mismo, así que se pueden correr desde cualquier carpeta.

### 3. Regenerar las capas (solo si cambian los datos de bronce)

```bash
poetry run python data_processing/limpieza_viajes_foraneos.py   # necesita data/Detalles viajes foraneos ultimo año.xlsx (no está en el repo)
poetry run python data_processing/capa_plata.py                 # → data/plata/viajes_foraneos_plata.csv
poetry run python data_processing/etl_oro.py --plata data/plata/viajes_foraneos_plata.csv   # → data/oro_v2/
```

`etl_oro.py` usa por defecto el catálogo `data/distancias_v2/catalogo_distancias_v2.csv`, el separador `;` y la salida `data/oro_v2`. Con la plata y el catálogo actuales **reproduce exactamente** el contenido de `data/oro_v2/`: las mismas columnas, valores, rechazados y capacidades. En `rutas_pendientes.csv` solo puede cambiar el orden de las rutas empatadas.

**Si aparecen rutas nuevas** (destinos o plantas que no están en el catálogo), hay que actualizar las distancias antes de la corrida final:

```bash
poetry run python data_processing/distancias_v2.py --solo-tablas   # agrega los lugares nuevos a config/ (respaldo en *.bak.csv)
#   → completa a mano en config/plantas.csv y config/destinos_canonicos.csv: ciudad, estado y Confirmado = True
poetry run python data_processing/distancias_v2.py                 # geocodifica (Nominatim) y calcula km (OSRM); solo consulta lo que no está en caché
poetry run python data_processing/etl_oro.py --plata data/plata/viajes_foraneos_plata.csv   # vuelve a generar el oro con el catálogo nuevo
```

`distancias_v2.py` toma la lista de rutas del oro existente (`--oro`, por defecto `data/oro_v2/viajes_foraneos_oro.csv`). Por eso, cuando hay rutas nuevas, primero se corre `etl_oro.py` una vez (esas rutas quedan con `Km_Fuente = 'faltante'`), luego `distancias_v2.py` y después `etl_oro.py` otra vez.

> No abras ni guardes los CSV con Excel. El oro v2 del repo ya pasó por eso: las fechas cambiaron de `2026-01-08 16:57:00` a `1/8/2026 16:57` y perdieron los segundos. Los componentes lo leen bien, pero si vuelves a correr `etl_oro.py` las fechas regresan al formato completo.

---

## ETL plata → oro v2 (`etl_oro.py`)

### Principios

1. **Nunca se imputan kilómetros con medianas.** Si no hay un dato confiable, el km queda vacío y su origen se anota en `Km_Fuente`.
2. **Nunca se borran outliers estadísticos: se marcan** (`Flag_*`). Solo se rechazan, con motivo, los registros físicamente imposibles (`viajes_rechazados.csv`; hoy son 0).
3. **El tipo de camión sale del texto declarado** (`FAMILIA_CAMION_DESC`, o `Tipo Camión` si la familia viene vacía). Ya no se reclasifica por el peso de la carga, que era circular, ni cae por defecto a "2 ejes".
4. **Las capacidades se pueden editar**: se guardan en `capacidades_config.csv`, con un campo que indica si están verificadas contra la NOM-012-SCT-2.
5. **El script no sobrescribe su entrada** y deja un reporte de calidad que se puede auditar.

### Salidas (en `--salida`, por defecto `data/oro_v2/`)

| Archivo | Contenido |
|---|---|
| `viajes_foraneos_oro.csv` | La capa oro: 71,967 viajes × 47 columnas |
| `viajes_rechazados.csv` | Registros imposibles, con `Motivo_Rechazo` |
| `rutas_pendientes.csv` | Rutas con km faltante o sospechoso, ordenadas por número de viajes, con su `Fuente` y el % acumulado |
| `capacidades_config.csv` | Capacidades usadas por tipo de unidad. Se puede editar y volver a pasar con `--capacidades` |
| `reporte_calidad.json` | Conteos de cada paso: rechazados, sin clasificar, exceden capacidad, discrepancias de peso, km por fuente, flags y viajes por mes |

### Qué cambió respecto al ETL v1 (`data_engineer.py`)

| Antes (v1) | Ahora (v2) |
|---|---|
| Los outliers detectados con IQR **se borraban** (~23 % de los viajes, incluidos los largos y los más ineficientes) | Se **marcan** (`Flag_Outlier_*`, z-MAD dentro de cada ruta); solo se rechazan los imposibles |
| Tipo "Full" si `Programado_kg > 38,500` (circular) | El tipo sale solo del texto declarado; el exceso de carga queda en `Excede_Capacidad` |
| Un texto sin clasificar caía en "2 ejes" | Queda como `SIN_CLASIFICAR` y se cuenta en el reporte (hoy son 0) |
| Familia vacía → sin tipo | Se usa `Tipo Camión` como respaldo (5 viajes de plataforma 40 pies) |
| `'CAMIONETA 3.5'` nunca coincidía con `CAMIONETA 35` | Regla corregida (capacidad de 3,500 kg) |
| Km nulos → mediana por destino, origen o global | Nunca se imputa. `Km_Fuente` dice por qué falta (`faltante`, `multidestino`, `region`, `sin_geocodificar_destino`) |
| Km imposibles entraban a `Costo_Ton_Km` | `Km_Sospechoso` (velocidad implícita > 90 o < 3 km/h, o km < 5) y `Km_Estimado` (línea recta × factor) dejan `Costo_Ton_Km` en NaN; `Costo_Ton_Km_Bruto` conserva el cálculo sin filtro |
| Pesos programados absurdos sin marcar | `Flag_Discrepancia_Peso`: diferencia de más de 1,000 kg entre el peso programado y el real |
| Capacidades en el código, sin fuente | `capacidades_config.csv` con `Verificado_NOM012` |
| Ortografía de destinos sin control | Grafías unificadas y correcciones aplicadas también al catálogo |
| `Ineficiencia_Capacidad` | Eliminada; se usa `Flag_Util_Baja_70` |

### De dónde sale cada columna del oro v2

| Columnas | Origen |
|---|---|
| `ID_VIAJE`, `Ciudad Destino`, `ID Camión`, `Tipo Camión`, `Programado (Peso)`, `PLANTA_ORIGEN`, `GRUPO_PLANTA_ORIGEN`, `FECHA_EGRESO`, `FAMILIA_CAMION_DESC`, `FECHA_VIAJE_FINALIZADO`, `Planta Origen`, `Transportista`, `Desc TpoTrn`, `Peso Total`, `Monto total`, `Placas` | Vienen de la capa plata (`capa_plata.py`; las columnas de Detalles pasan antes por `limpieza_viajes_foraneos.py`). `etl_oro.py` solo unifica las grafías de destino y planta y convierte fechas y números |
| `Kilometros_Ruta`, `Km_Fuente` | Las calcula `distancias_v2.py` en el catálogo. `etl_oro.py` las pega a cada viaje por ruta |
| `Tiempo_Viaje_Horas`, `Nomenclatura_Inferida`, `Capacidad_Max_kg`, `Programado_kg`, `Discrepancia_Peso_kg`, `Toneladas_Reales`, `Toneladas_Maximas`, `Porcentaje_Utilizacion_Real`, `Capacidad_Sobra_kg`, `Excede_Capacidad`, `Costo_Ton_Real`, `Costo_Ton_Optimo`, `Sobrecosto_Ton`, `Flag_Discrepancia_Peso` | `etl_oro.py`: capacidad y costos. `Capacidad_Max_kg` sale de `CAPACIDADES_DEFAULT` o de `--capacidades` |
| `Es_Multidestino`, `Es_Region`, `Ruta_ID`, `Vel_Implicita_kmh`, `Km_Sospechoso`, `Km_Estimado`, `Km_Confiable`, `Tonelada_Kilometro`, `Costo_Ton_Km`, `Costo_Ton_Km_Bruto` | `etl_oro.py`: distancias y su calidad |
| `Flag_Outlier_Costo_Ton`, `Flag_Outlier_Tiempo`, `Flag_Util_Baja_70`, `Mes_Egreso`, `Semana_Egreso` | `etl_oro.py`: marcas de outliers y ventana |

**Ojo:** `Capacidad_Max_kg`, `Porcentaje_Utilizacion_Real`, `Costo_Ton_Optimo` y `Sobrecosto_Ton` usan las capacidades heredadas del v1, que no están verificadas. Los componentes **no las usan**: calculan su propia capacidad (NOM-012 − tara) en `ternium_comun.capacidades()`. `Costo_Ton_Optimo` y `Sobrecosto_Ton` suponen consolidación total: son una cota superior laxa, no un ahorro.

### Pendientes que el ETL no resuelve solo

1. Revisar las rutas de `rutas_pendientes.csv` (km sospechosos).
2. Verificar `capacidades_config.csv` contra la NOM-012-SCT-2 (peso bruto menos tara). La plataforma de 40 pies no tiene capacidad.
3. Decidir si las rutas a Baja California Sur (29 viajes) se miden por tierra (~3,300–4,200 km, lo que da OSRM) o con ferry.

---

## Estructura del proyecto

### Pipeline

| Archivo | Función |
|---|---|
| [limpieza_viajes_foraneos.py](data_processing/limpieza_viajes_foraneos.py) | Limpia `Detalles viajes foraneos ultimo año.xlsx`: quita filas basura (totales, filtros), pesos imposibles (≤ 0 t o > 80 t) y viajes repetidos, y guarda el CSV limpio en `data/`. |
| [capa_plata.py](data_processing/capa_plata.py) | Une **Detalles**, **Tiempos** y **Costos** por `ID_VIAJE` (*inner join*), selecciona y renombra columnas, convierte números con formato español y fechas, y genera la capa plata. |
| [distancias_v2.py](data_processing/distancias_v2.py) | Catálogo de distancias. Geocodifica plantas y destinos por ciudad (Nominatim) y calcula km por carretera (OSRM), con caché. Si OSRM no encuentra ruta, usa línea recta × factor de carretera calibrado (1.252) y lo marca como estimado. Lo ambiguo va a `geocoding_revisar.csv`. |
| [etl_oro.py](data_processing/etl_oro.py) | Plata → oro v2. Ver la [sección del ETL](#etl-plata--oro-v2-etl_oropy). |

### Código compartido por los componentes

| Archivo | Función |
|---|---|
| [ternium_comun.py](analisis_estadistico_IA/ternium_comun.py) | Carga del universo (`cargar_universo`), mapeo de familias a unidades, taras y capacidades (`capacidades`), bootstrap de dos vías transportista × ruta (`bootstrap_conglomerados`) y estilo de figuras. Lo usan C2, C3 y C4. **C1 tiene su propia copia** de estas definiciones: si cambian, hay que actualizar ambos. |
| [componente_3_optimizacion.py](analisis_estadistico_IA/componente_3_optimizacion.py) | Optimizador de right-sizing (tarifas de referencia, factibilidad y MILP por semana). Es una copia de la sección 6 de `componente_2.ipynb` y lo usan C3 y C4. Si cambian las reglas del MILP, hay que actualizar ambos. |

El Componente 2 también importa `clave()` de `distancias_v2.py` (que usa `norm()` de `etl_oro.py`) y lee `config/*.csv` y `data/distancias_v2/cache_geocodificacion.csv` para obtener las coordenadas de plantas y destinos.

### Componentes del entregable

| Archivo | Contenido |
|---|---|
| [componente_1.ipynb](analisis_estadistico_IA/componente_1.ipynb) | Línea base. [Detalle](#componente-1-línea-base). |
| [componente_2.ipynb](analisis_estadistico_IA/componente_2.ipynb) | Efecto causal, modelo de elección, optimización y simulador. [Detalle](#componente-2-efecto-del-tipo-de-camión-optimización-y-simulador). |
| [componente_3.ipynb](analisis_estadistico_IA/componente_3.ipynb) | Comparación de enfoques y casos raros. [Detalle](#componente-3-comparación-de-enfoques-y-casos-raros). |
| [componente_4.py](analisis_estadistico_IA/componente_4.py) | Ahorro creíble y piloto. [Detalle](#componente-4-cuánto-ganaría-ternium-realmente). |

### Configuración y datos

| Archivo | Descripción |
|---|---|
| `data/Detalles viajes foraneos ultimo año.csv` | Viajes programados: destino, camión y peso programado (t). Ya limpio por `limpieza_viajes_foraneos.py`. |
| `data/Tiempos Viajes Foraneos.csv` | Planta de origen, grupo de producto, fechas de egreso y finalización, familia de camión. |
| `data/Viajes con Costos V2.csv` | Transportista, tipo de transporte, peso real (kg), monto pagado (MXN) y placas. |
| `data/Detalle Ciclos de Viajes Despachados.csv` | Ciclos de despacho. No entra en el pipeline; solo lo usa el análisis exploratorio. |
| `config/plantas.csv`, `config/destinos_canonicos.csv` | Ciudad y estado de cada planta (20) y nombre limpio, estado y tipo de cada destino (524), revisados a mano. Son la fuente para geocodificar. Los `*.bak.csv` son respaldos que deja `distancias_v2.py`. |
| `data/distancias_v2/` | Catálogo de distancias, caché de geocodificación y de rutas, `geocoding_revisar.csv`, `rutas_ratio_dudoso.csv` y `reporte_distancias.json`. |
| `data/oro_v2/` | Salidas de `etl_oro.py` (ver arriba). |
| `resultados_ternium/componente_4_*` | Salidas de `componente_4.py`. El resto de esa carpeta son salidas del análisis exploratorio. |

### Documentación

| Archivo | Descripción |
|---|---|
| [CLAUDE.md](CLAUDE.md) | Bitácora del proyecto: decisiones, hallazgos por fecha y pendientes. |
| [sugerencias_ternium.md](sugerencias_ternium.md) | Preguntas abiertas y sugerencias para Ternium, con su estado. |
| `borrador_entrega2_reto.docx` | Borrador del documento de la entrega 2. |

### Archivos heredados

No forman parte del flujo actual. Se conservan como referencia.

| Archivo | Situación |
|---|---|
| `data/plata/viajes_foraneos_oro_ANTIGUO.csv` | Oro v1, renombrado. Solo lo lee la sección "⚠️ Versión anterior" de `componente_2.ipynb`. |
| `ternium_silver.db` | Base SQLite del ETL de plata anterior (`etl_ternium_silver_csv.py`, ya eliminado). Ningún archivo la usa y no se versiona (`*.db` en `.gitignore`). |
| [Componente_2_Ternium.ipynb](analisis_estadistico_IA/Componente_2_Ternium.ipynb) y el resto de `resultados_ternium/` | Análisis exploratorio sobre bronce (χ², Spearman, PCA) y sus salidas. |

El pipeline v1 (`data_engineer.py`, `imputación_rutas_capa_oro.ipynb`, `fix_kilometros*.py`, `distancia_rutas.py`, `catalogo_distancias.csv` y el glosario del oro v1), así como `etl_ternium_silver_csv.py`, se eliminaron del repo; siguen disponibles en el historial de git.

---

## Universo y convenciones comunes

Los cuatro componentes trabajan sobre el **mismo universo**: **58,275 viajes** (81 % de la ventana, 1.67 Mt) en seis unidades.

| Unidad | Familias incluidas | Carga útil para el análisis |
|---|---|---|
| Torton | Torton | 16.9 t (techo operativo P99: no hay tara confirmada) |
| 2 Ejes | Plataforma 2 ejes (neumática, muelles, desacoplada) | 32.0 t |
| Caja Seca 2 Ejes | Caja seca 2 ejes | 30.5 t |
| 3 Ejes | Plataforma 3 ejes (neumática, muelles, corta, ligera, ultra ligera) | 38.5 t |
| Big Coil | Plataforma 3 ejes Big Coil | 37.5 t |
| Full | Full neumática | 51.0 t |

- **Excluidos** (con el motivo registrado en el Componente 1): Cortina y Portacintas común (por indicación de Ternium), Tortoneta, camioneta, Heavy, cama baja y plataformas largas.
- **Capacidad** = peso bruto vehicular de la NOM-012-SCT-2 − tara. Las taras (14.5–16.5 t) son un **supuesto provisional** dentro del rango de 14–17 t que reportó Ternium.
- **Utilización** en peso: u = carga real / capacidad. Como no hay datos de volumen ni de largo, es una cota inferior de la utilización real.
- **Incertidumbre:** bootstrap de **dos vías transportista × ruta** (*pigeonhole*, Owen 2007). La tarifa se negocia por transportista × ruta × unidad, así que los viajes no son independientes.

---

## Componente 1: línea base

[componente_1.ipynb](analisis_estadistico_IA/componente_1.ipynb)

| Sección | Qué hace |
|---|---|
| 1–2. Datos y universo | Carga el oro v2, aplica la ventana ene–ago y arma el universo con la tabla de exclusiones y sus motivos. |
| 3. Unidades por planta | Mezcla de unidades por planta de origen (tabla). |
| 4. Capacidad y utilización | Carga útil por unidad, % de viajes por encima del límite legal, histograma de carga contra capacidad y utilización por unidad y por planta × unidad, con IC. Compara el bootstrap de dos vías con otros esquemas para justificarlo. |
| 5. Costo de la capacidad ociosa | CO = costo del viaje × (1 − u): la parte de la tarifa que paga capacidad no usada. Por unidad, por planta × unidad y como penalización en costo por tonelada-km. Es el **tamaño del problema**, no un ahorro alcanzable. |
| 6. Right-sizing por reglas | Para cada viaje, la unidad más barata que puede llevar la carga en la misma ruta (tarifa mediana, ≥ 5 viajes). Solo se mueve si ahorra ≥ 3 %, y la caja seca no pasa a plataforma abierta. El IC evalúa los mismos movimientos con tarifas remuestreadas. |

**Resultados principales (ene–ago 2026)**

- Utilización: Torton 0.85, 2 Ejes 0.75, 3 Ejes 0.81, Big Coil 0.71, Full 0.95.
- Costo de la capacidad ociosa: **343 M MXN [302–378] = 20.9 % del gasto** (1,636 M). El mayor foco es Juventud con 3 ejes (~60 M).
- Right-sizing: **5,784 viajes (9.9 %)**, ahorro de **38.5 M MXN** (2.35 % del gasto). El grueso es 3 ejes → 2 ejes y Big Coil → 2 ejes. Recupera ~11 % del costo ocioso.

## Componente 2: efecto del tipo de camión, optimización y simulador

[componente_2.ipynb](analisis_estadistico_IA/componente_2.ipynb)

| Sección | Qué hace |
|---|---|
| 1. DAG | Grafo causal tipo de camión → costo. Ajuste: efectos fijos de ruta, peso programado, mes y "es retorno". El transportista es **mediador** (Ternium pide la unidad y después los transportistas ofertan). Verifica con datos las consecuencias del grafo. |
| 2. Retorno | Reconstruye los ciclos de cada placa. Solo ~1 % de los viajes regresa con carga de Ternium. |
| 3. Efecto del tipo de camión | Regresión por pares de unidades, solo en rutas donde operan ambas. Sensibilidad a un confusor omitido (Cinelli y Hazlett) y control negativo. |
| 4. Robustez y falsificación | Siete variantes del análisis, replicación ene–jun vs. jul–ago, efecto mes a mes, placebo por permutación y heterogeneidad entre rutas. |
| 5. Modelo de elección de unidad | Clasificador **HistGradientBoosting** que reproduce qué unidad pide Ternium con la información disponible al pedirla (entrena ene–may, valida jun, prueba jul–ago). La sección 5.1b lo compara con un **Random Forest** con las mismas variables y la misma partición. Marca las decisiones atípicas. |
| 6. Optimización | **MILP** por semana: minimiza el costo con restricciones de capacidad, compatibilidad, materialidad (3 %) y disponibilidad de flota por planta. Incluye la estabilidad ante cambios de tarifas y reglas. |
| 7. Simulador | Política actual (modelo de la sección 5) contra right-sizing (decidido con ene–jun) en jul–ago, fuera de muestra. Antes valida que reproduzca la línea base de C1. |

**Resultados principales**

- **2 ejes vs. 3 ejes:** en la misma ruta, mes y peso, el 2 ejes cuesta **−20.8 % [−24.2, −17.2]** (~5,200 MXN por viaje). Es robusto: se replica todos los meses y pasa el placebo. **2 ejes vs. Big Coil:** −28.8 %. **Torton → 2 ejes no es significativo** (−1.3 % [−19, +21]).
- **Modelo de elección:** acierta el **94.9 % [92.4–96.8]** en jul–ago, contra 81.9 % de la regla "unidad más usada en la ruta". El Random Forest acierta lo mismo (94.5 %), pero sus probabilidades son peores (log-loss 0.180 contra 0.156), y el simulador sortea con esas probabilidades. Solo 3.3 % de los 3 ejes son atípicos: el ahorro viene de **cambiar la política**, no de corregir errores.
- **Optimización con flota:** 4,721 viajes, **31.6 M MXN** en ene–ago. Es sensible a la disponibilidad de flota: con flota P75 baja a 18.8 M.
- **Simulador en jul–ago (fuera de muestra):** **6.2 M MXN [3.3–10.0]** en dos meses (1.5 % del gasto), positivo en el 100 % de las réplicas.

> **Versión anterior (al final del notebook, bajo "⚠️ Versión anterior").** Se conserva solo como referencia y sus resultados **no deben usarse**. Lee el oro v1 y contiene el OLS sobre el top 50 de rutas, los clusters K-Means de destino, un **Random Forest** y un **XGBoost** de regresión del costo y el bootstrap del ahorro. Problemas: clasificación circular de camiones por peso, ahorro fabricado (costo real − predicho, recortado en 0), fuga de información del periodo de prueba en los clusters y etiquetas "Q4", "Oct–Dic" y "anual" que no corresponden a los datos.

## Componente 3: comparación de enfoques y casos raros

[componente_3.ipynb](analisis_estadistico_IA/componente_3.ipynb)

| Sección | Qué hace |
|---|---|
| 1. Cuatro perspectivas | Compara sobre la misma demanda: **actual**, **heurística** (la unidad más frecuente en la ruta o la más chica compatible), **MILP con flota** (el de C2) y **consolidación** First-Fit Decreasing (juntar viajes de 3 ejes del mismo día y ruta hasta 36.575 t). |
| 2. Discusión crítica | Qué supone y qué ignora cada enfoque. |
| 3. Casos raros | 20 viajes que contradicen el patrón (sobrecosto, subcosto, peso alto en 2 ejes e inversión tarifaria), con diagnóstico provisional y la evidencia que habría que pedirle a Ternium. |

**Resultados principales (ene–ago 2026)**

- Heurística: **31.2 M MXN [16.6–54.8]**, el 98.8 % de lo que logra el MILP, aunque no respeta la disponibilidad de flota.
- MILP con flota: **31.6 M MXN [16.7–55.2]**.
- Consolidación: **0.7 M MXN [0.1–1.8]**, con solo 37 viajes eliminados. Las cargas típicas (~29 t) no caben de dos en dos en un 3 ejes.

## Componente 4: ¿cuánto ganaría Ternium realmente?

[componente_4.py](analisis_estadistico_IA/componente_4.py), resultados en `resultados_ternium/componente_4_*`

Parte del número ingenuo (MILP de C3, 31.6 M) y lo reduce paso a paso con supuestos cada vez más realistas, con IC de dos vías transportista × ruta (B = 2,000):

| Paso | Ahorro ene–ago (M MXN) [IC 95 %] | Viajes |
|---|---|---|
| 0. Número ingenuo: MILP con flota (C3) | 31.6 [17.5–52.3] | 4,721 |
| 1. Factibilidad: peso programado confiable y peso real dentro de la capacidad legal | 31.6 [17.5–52.3] | 4,713 |
| 2. Solo movimientos con efecto causal estimado en C2 (3E→2E, Big Coil→2E, Big Coil→3E) | 28.4 [14.4–49.1] | 4,067 |
| 3. Maldición del optimizador: decidir con semanas pares y medir con impares (y al revés) | 28.2 [14.2–48.5] | 4,687 |
| 4. Disponibilidad: unidades por planta y semana = P90 semanal (no el máximo) | 20.8 [11.0–34.0] | 3,270 |
| 5. Respuesta del mercado: la unidad adicional se paga con prima de 6.7 % | **15.6 [8.3–25.1]** | 3,281 |

- **Escenarios:** optimista 30.7 M, **central 15.6 M** y pesimista 5.6 M en ene–ago (0.3–1.9 % del gasto). Anualizado (×12/8): central **23.3 M [12.4–37.6]**. Es la única anualización del proyecto y depende de que sep–dic se comporte como ene–ago.
- **Punto de quiebre:** el ahorro desaparece si la unidad nueva se paga con una prima de **26.6 % [21.6–33.2]**.
- **Validación fuera de muestra** (decide con ene–jun, mide jul–ago): 4.7 M [2.2–8.1].
- **Consolidación con ventanas más amplias:** mismo día 0.7 M, misma semana 2.1 M, mismo mes 3.5 M.
- **Piloto propuesto:** ~930 viajes por grupo (63 bloques ruta × semana), unas **13 semanas**. Las 10 rutas principales concentran el 49 % del ahorro central, empezando por Pesquería → San Luis Potosí y Pesquería → Altamira.

**Las cifras de los componentes no se suman.** Son estimaciones del mismo ahorro con supuestos cada vez más estrictos: C1 (38.5 M, peso real, sin límite de flota) → C2 y C3 (31.6 M, peso programado, con flota) → C4 (15.6 M central, con respaldo causal, disponibilidad realista y prima de mercado). El simulador de C2 (6.2 M) cubre solo jul–ago.

---

## Notas y limitaciones

- **Resultados guardados desactualizados.** En `componente_1.ipynb` cambió el cálculo del IC del right-sizing (ahora evalúa los mismos movimientos con tarifas remuestreadas) y hay una figura nueva sin ejecutar. Los resultados guardados son de la versión anterior, así que el IC del ahorro de C1 se omite arriba hasta volver a correr el notebook. La comparación con Random Forest (sección 5.1b de C2) tampoco tiene resultados guardados; las cifras citadas vienen de su texto de lectura.
- **Capacidades provisionales.** Las taras son un supuesto dentro de 14–17 t. Falta la tara real del Full y del Torton, y `capacidades_config.csv` tiene `Verificado_NOM012 = False`.
- **Techo de ~26 t en 2 ejes.** Las unidades de 2 ejes casi nunca cargan más de ~26 t, aunque la ley permitiría ~31–32 t. Si es una restricción real, el ahorro baja (en C1, con capacidad P95: 27.8 M en lugar de 38.5 M). Está entre las preguntas para Ternium.
- **Solo hay peso.** No hay datos de volumen, largo ni producto. La compatibilidad producto–unidad se aproxima con la ruta y las unidades que ya la operan.
- **Las tarifas históricas no son ofertas.** El ahorro supone que el transportista cobraría la tarifa observada y que hay unidades disponibles. C4 cuantifica ambos supuestos.
- **`FECHA_VIAJE_FINALIZADO` no es la llegada física** (en 37 % de los casos la placa sale a otro viaje antes de esa fecha). Los ciclos se reconstruyen solo con fechas de egreso.
- La primera celda de la versión anterior del Componente 2 define variables de entorno para `libomp` en macOS (Homebrew). En Windows no tienen efecto.
