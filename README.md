# Proyecto Ternium – Eficiencia en viajes foráneos

Análisis de los viajes foráneos de Ternium para medir qué tan bien se aprovecha la capacidad de los camiones y cuánto cuesta no aprovecharla. Los datos se procesan con una arquitectura **Medallion** de tres capas:

| Capa | Qué contiene | Dónde vive |
|---|---|---|
| **Bronce** | Archivos originales entregados por Ternium (`.xlsx` / `.csv`) | `data/` |
| **Plata** | Las 3 tablas principales unidas, una fila por viaje, tipos de dato corregidos | `data/plata/viajes_foraneos_plata.csv` |
| **Oro** | Plata + métricas de tiempo, capacidad, costo y distancia, sin outliers | `data/plata/viajes_foraneos_oro.csv` |

> El significado de cada columna de la capa oro está en [data/plata/Glosario_tabla_oro.md](data/plata/Glosario_tabla_oro.md).

---

## Flujo del pipeline

```
data/*.xlsx  (BRONCE)
   │
   ▼  1. limpieza_viajes_foraneos.py
data/Detalles viajes foraneos ultimo año.csv   (limpio)
   │  + data/Tiempos Viajes Foraneos.csv
   │  + data/Viajes con Costos V2.csv
   ▼  2. capa_plata.py
data/plata/viajes_foraneos_plata.csv           (PLATA)
   │
   ▼  3. data_engineer.py   ← usa catalogo_distancias.csv
data/plata/viajes_foraneos_oro.csv             (ORO)
   │
   ▼  4. imputación_rutas_capa_oro.ipynb   (rellena kilómetros faltantes)
data/plata/viajes_foraneos_oro.csv             (ORO final)
   │
   ├─▶ 5. componente_1.ipynb   → utilización, costos, right-sizing por reglas y bootstrap del ahorro
   │
   └─▶ 6. componente_2.ipynb   → consolidación, regresión OLS, línea base, clusters, modelos ML y bootstrap del ahorro

Independiente: Componente_2_Ternium.ipynb → análisis exploratorio → resultados_ternium/
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
python -m pip install "numpy>=2.5.4,<3.0.0" "matplotlib>=3.11.2,<4.0.0" "scikit-learn>=1.9.1,<2.0.0" "pandas>=3.0.6,<4.0.0" "openpyxl>=3.1.5,<4.0.0" "requests>=2.34.2,<3.0.0" "geopy>=2.5.0,<3.0.0" "scipy>=1.18.1,<2.0.0" "seaborn>=0.13.2,<0.14.0" "tabulate>=0.10.0,<0.11.0" "statsmodels>=0.15.0,<0.16.0" "xgboost>=3.4.1,<4.0.0" ipykernel
```

Después, en VS Code, selecciona `venv\Scripts\python.exe` como kernel de los notebooks. Si aparece `ModuleNotFoundError` (por ejemplo, `No module named 'seaborn'`), la dependencia no está instalada en el kernel que estás usando.

### 2. Correr el pipeline (desde la raíz del proyecto)

```bash
poetry run python limpieza_viajes_foraneos.py   # Bronce → CSV limpio de Detalles
poetry run python capa_plata.py                 # → capa plata
poetry run python data_engineer.py              # → capa oro
```

Después abre y ejecuta, en este orden:

1. `imputación_rutas_capa_oro.ipynb`: completa `Kilometros_Ruta` y recalcula el costo por tonelada-kilómetro.
2. `componente_1.ipynb`: utilización, costos y right-sizing por reglas.
3. `componente_2.ipynb`: modelos de costo (OLS, Random Forest, XGBoost) y ahorro simulado.

> **Importante:** cada vez que vuelvas a correr `data_engineer.py`, tienes que volver a correr también el notebook de imputación. Si no, la capa oro queda con kilómetros vacíos.
>
> `data_engineer.py` y los scripts `fix_kilometros*.py` usan rutas relativas, así que deben ejecutarse **desde la raíz del proyecto**.

---

## Estructura del proyecto

### Pipeline principal

| Archivo | Función |
|---|---|
| [limpieza_viajes_foraneos.py](limpieza_viajes_foraneos.py) | Lee `Detalles viajes foraneos ultimo año.xlsx`. Quita las filas basura (totales y filtros), los pesos imposibles (≤ 0 t o > 80 t) y los viajes repetidos. Marca los destinos en Texas como `Extranjero/Texas` y guarda un CSV limpio. |
| [capa_plata.py](capa_plata.py) | Une **Detalles**, **Tiempos** y **Costos** por `ID_VIAJE` con un *inner join*, así que solo quedan los viajes presentes en las tres tablas. Selecciona columnas, convierte números con formato español (`30.470,000` → `30470.0`) y fechas, y genera la capa plata. |
| [data_engineer.py](data_engineer.py) | Pasa de plata a oro. Calcula la duración del viaje, la discrepancia de peso, el tipo de camión inferido y su capacidad, el % de utilización, el costo por tonelada, el sobrecosto, los km por ruta y el costo por ton-km. Elimina outliers con IQR. |
| [catalogo_distancias.csv](catalogo_distancias.csv) | Kilómetros por ruta (planta origen → ciudad destino). Se obtuvieron con **Nominatim** (coordenadas) y **OSRM** (distancia en carretera). Si el archivo existe, `data_engineer.py` lo reutiliza y no vuelve a consultar las APIs. |
| [imputación_rutas_capa_oro.ipynb](imputación_rutas_capa_oro.ipynb) | Rellena los km faltantes en la capa oro en cascada: mediana por ciudad destino → mediana por planta origen → mediana global. Luego recalcula `Tonelada_Kilometro` y `Costo_Ton_Km`. |
| [componente_1.ipynb](componente_1.ipynb) | Entregable 2, componente 1. Utilización de los camiones, costos por viaje / tonelada / ton-km y *right-sizing* por reglas. Ver [detalle abajo](#componente-1-utilización-costos-y-right-sizing-por-reglas). |
| [componente_2.ipynb](componente_2.ipynb) | Entregable 2, componente 2. Consolidación y ciclos de camiones, efecto causal del tipo de camión sobre el costo, línea base, clusters de destinos, modelos predictivos y *right-sizing* simulado con ML. Ver [detalle abajo](#componente-2-modelos-de-costo-y-ahorro-simulado). |

### Análisis exploratorio

| Archivo | Función |
|---|---|
| [Componente_2_Ternium.ipynb](Componente_2_Ternium.ipynb) | Análisis estadístico sobre los archivos de bronce: unidad de observación, distribuciones y anomalías, sesgo de selección (χ²), correlaciones de Spearman con corrección de Holm, línea base y PCA. |
| [resultados_ternium/](resultados_ternium/) | Tablas (`.csv`, `.json`) y figuras (`.png`) generadas por `Componente_2_Ternium.ipynb`. |

### Datos

| Archivo | Descripción |
|---|---|
| `data/Detalles viajes foraneos ultimo año.*` | Viajes programados: destino, camión y peso programado (t). |
| `data/Tiempos Viajes Foraneos.*` | Eventos del viaje: planta de origen, fechas de egreso y finalización, familia de camión. Tiene una fila por parada. |
| `data/Viajes con Costos V2.*` | Costos: transportista, tipo de transporte, peso real (kg), monto pagado (MXN) y placas. |
| `data/Detalle Ciclos de Viajes Despachados.*` | Ciclos de despacho. No entra en el pipeline actual; solo se usa en el análisis exploratorio. |

### Archivos auxiliares o heredados

| Archivo | Situación |
|---|---|
| [fix_kilometros.py](fix_kilometros.py), [fix_kilometros_2.py](fix_kilometros_2.py) | Versión en script de lo que hace `imputación_rutas_capa_oro.ipynb`. |
| [distancia_rutas.py](distancia_rutas.py) | Generador independiente del catálogo de distancias. Su lógica ya está integrada en `data_engineer.py`. |
| [etl_ternium_silver_csv.py](etl_ternium_silver_csv.py) | ETL anterior de la capa plata (SQLite, cuarentena y logs). Lo reemplazó `capa_plata.py`. |
| `ternium_silver.db` | Base SQLite generada por el ETL anterior. Ya no se usa. |
| [pyproject.toml](pyproject.toml), `poetry.lock` | Dependencias del proyecto. |

---

## Componentes del entregable

Los dos notebooks leen `data/plata/viajes_foraneos_oro.csv`. Las cifras de abajo son las del último resultado guardado en cada notebook.

### Componente 1: utilización, costos y right-sizing por reglas

[componente_1.ipynb](componente_1.ipynb)

| Paso | Qué hace |
|---|---|
| 1. Tipos de camión | Reclasifica los camiones por peso programado según los límites legales de la NOM-012 (2 ejes: 32,000 kg · 3 ejes: 38,500 kg · Full: 46,000 kg). Separa los **Portacintas / Big Coil** del resto de los 3 ejes. |
| 2. Utilización | Calcula `u_peso` = carga real / capacidad legal. Grafica la utilización de las cargas `Largos`, que se llenan por largo antes que por peso. |
| 3. Dimensión que amarra | `u_efectiva = max(u_peso, u_volumen)` e identifica si el viaje se limita por **peso** o por **volumen/largo**. `u_volumen` es un supuesto (1.0 para `Largos`, 0.85 × `u_peso` para el resto), no un dato medido. |
| 4. Distribución de `u_peso` | Tabla y boxplot por tipo de camión, solo para los viajes que se limitan por peso. |
| 5. Distancias | Cortes por terciles: corta (≤ 475 km), media (476–797 km) y larga (> 797 km). |
| 6. Costos | Mediana del costo por viaje, por tonelada y por ton-km según tipo de camión y distancia. El orden de qué camión es "más barato" cambia según la métrica. |
| 7. Real vs. óptimo | Compara el costo por tonelada **real (con ociosidad)**, `Monto total / Toneladas_Reales`, contra el **óptimo**, `Monto total / Toneladas_Maximas`, es decir, el camión lleno al 100%. Lo mismo por ton-km. |
| 8. Ahorro evitable | Suma `Sobrecosto_Ton × Toneladas_Reales` por tipo de camión. Es una **cota superior**: supone que todos los camiones podían ir llenos. |
| 9. Right-sizing | Asigna el camión más chico donde cabe la carga con 5% de holgura (filtro físico). Solo hace el cambio si la tarifa mediana de ese camión en ese tramo de distancia es menor que lo que se pagó (filtro financiero). |
| 10. Bootstrap | Ahorro ejecutable con intervalo de confianza del 95%, remuestreando **rutas** (planta origen – ciudad destino) como conglomerados, 1,000 iteraciones. |

**Resultados principales**

- Ahorro evitable (cota superior), en millones de MXN: 3 ejes 148.88 · 2 ejes 53.62 · Portacintas 27.87 · Torton 5.23 · Full 2.43.
- Right-sizing: **3,828 viajes** se pueden reasignar a un camión más barato.
- Ahorro ejecutable: **$44.08 M MXN** en promedio, con IC 95% de **$33.86 M a $54.61 M**.

### Componente 2: modelos de costo y ahorro simulado

[componente_2.ipynb](componente_2.ipynb)

| Paso | Qué hace |
|---|---|
| 1. Consolidación | Busca viajes de la misma placa, el mismo día y con distinto destino, cuya carga junta cabría en un solo camión. Solo hay **4 casos**, así que casi no hay potencial de consolidación. |
| 2. Ciclos / backhaul | Mide las horas entre el fin de un viaje y el siguiente egreso de la misma placa. Mediana de **20.9 h**. **28,005** conexiones son de menos de 24 h, y en el **54.4%** de los casos el camión vuelve a cargar en la misma planta. |
| 3. Regresión OLS | `Costo ~ Camion + Peso_Programado + Ruta` (efecto fijo por ruta, top 50 rutas, 31,803 viajes). Base de comparación: 3 ejes. En la misma ruta, un **2 ejes cuesta $6,060 menos**, un **Full $5,873 más** y un **Portacintas $1,058 más**. 44 de las 50 rutas usan más de un tipo de camión. |
| 4. Sensibilidad | Mide qué tan robusto es el efecto del 2 ejes ante variables omitidas: R² parcial 19.5%, valor de robustez 44.2%, valor-E 13.89. Un confusor oculto tendría que ser muy fuerte para anular el efecto. |
| 5. Línea base | 55,388 viajes · 1,648,920 t · **$1,343.59 M MXN** de gasto total · $24,258 por viaje · $814.83 por tonelada. |
| 6. Clusters de destino | K-Means (k = 4) sobre número de viajes, costo promedio y distancia promedio por ciudad destino. El cluster se usa como variable en los modelos. |
| 7. Random Forest | Predice el costo del viaje con peso, km, cluster, tipo de camión y planta. Partición temporal: entrenamiento ene–ago, validación sep, prueba oct–dic. Con ajuste de hiperparámetros (`RandomizedSearchCV` + `PredefinedSplit`): **R² = 0.946**, RMSE ≈ $3,858 por viaje, y el gasto total predicho queda a −2.6% del real. |
| 8. XGBoost | Modelo de comparación: R² = 0.939, RMSE ≈ $4,124. Queda un poco por debajo del Random Forest, que es el que se usa en la simulación. |
| 9. Right-sizing en Q4 | Pasa los 3 ejes con ≤ 30,400 kg a 2 ejes, y los 2 ejes con > 30,400 kg a 3 ejes. Después vuelve a cotizar los viajes con el Random Forest: 1,420 viajes cambian y el ahorro es de **$1.11 M** en el trimestre (−0.89%). |
| 10. Bootstrap anual | Aplica la misma política a todo el año. El ahorro de cada viaje es lo que se pagó menos el costo predicho, contando solo los ahorros positivos y restando el sobrecosto de los viajes que deben subir a 3 ejes. Bootstrap por rutas: **$13.67 M MXN**, con IC 95% de **$9.56 M a $18.53 M**. |

**Por qué los ahorros de los dos componentes no coinciden.** El componente 1 usa la tarifa mediana por tipo de camión y distancia, y considera cambios hacia cualquier camión más chico. El componente 2 solo evalúa el cambio de 3 ejes a 2 ejes y calcula el costo con un modelo que controla por ruta, peso y planta. Por eso su estimación es más conservadora.

---

## Notas y limitaciones

- **La capa oro se guarda en `data/plata/`**, no en una carpeta `data/oro/`. Así lo esperan todos los scripts.
- **El tipo de camión se infiere.** `FAMILIA_CAMION_DESC` contiene errores de captura, así que `data_engineer.py` asigna la unidad con reglas basadas en el peso programado y la descripción. Ver el glosario.
- **El inner join reduce la muestra.** Solo quedan los viajes presentes en las tres fuentes y luego se eliminan outliers. La capa oro actual tiene **55,388 viajes**.
- **No hay contrafactual explícito.** Los datos no registran el costo ni la disponibilidad de los camiones que *no* se usaron, así que los ahorros son estimaciones bajo supuestos.
- **Kilómetros incompletos en los resultados guardados.** Los resultados actuales de los notebooks muestran **17,666 viajes sin `Kilometros_Ruta`**, es decir, se corrieron sin el notebook de imputación. Los modelos del componente 2 descartan esos viajes, así que se entrenaron con ~37,700 viajes. Corre `imputación_rutas_capa_oro.ipynb` antes de los componentes para usar la muestra completa.
- **`u_volumen` es un supuesto.** No hay datos de volumen ni de largo, así que la dimensión que amarra del componente 1 se basa en una regla, no en una medición.
- **`GRUPO_PLANTA_ORIGEN` de respaldo.** Si la columna no existe, el componente 1 la genera **al azar** (semilla 42). Con la capa oro actual sí existe, pero conviene revisarlo si cambia el pipeline.
- **Celdas repetidas en el componente 2.** Algunas celdas repiten el código de la anterior (consolidación, preparación de variables, línea base). La primera celda también define variables de entorno para `libomp` en macOS (Homebrew); en Windows no tienen efecto.
