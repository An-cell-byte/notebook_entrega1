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
   ▼  5. componente_1.ipynb   → right-sizing y estimación de ahorro

Independiente: Componente_2_Ternium.ipynb → análisis exploratorio → resultados_ternium/
```

---

## Cómo ejecutarlo

### 1. Instalar dependencias

El proyecto usa [Poetry](https://python-poetry.org/) y Python ≥ 3.13.

```bash
poetry install
```

### 2. Correr el pipeline (desde la raíz del proyecto)

```bash
poetry run python limpieza_viajes_foraneos.py   # Bronce → CSV limpio de Detalles
poetry run python capa_plata.py                 # → capa plata
poetry run python data_engineer.py              # → capa oro
```

Después abre y ejecuta, en este orden:

1. `imputación_rutas_capa_oro.ipynb`: completa `Kilometros_Ruta` y recalcula el costo por tonelada-kilómetro.
2. `componente_1.ipynb`: análisis de right-sizing.

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
| [componente_1.ipynb](componente_1.ipynb) | Entregable 2, componente 1. Aplica reglas de *right-sizing* físico y financiero sobre la capa oro para estimar el ahorro por viaje si se hubiera asignado el camión adecuado. |

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
| [componente_2.ipynb](componente_2.ipynb) | Notebook vacío reservado. |
| [pyproject.toml](pyproject.toml), `poetry.lock` | Dependencias del proyecto. |

---

## Notas y limitaciones

- **La capa oro se guarda en `data/plata/`**, no en una carpeta `data/oro/`. Así lo esperan todos los scripts.
- **El tipo de camión se infiere.** `FAMILIA_CAMION_DESC` contiene errores de captura, así que `data_engineer.py` asigna la unidad con reglas basadas en el peso programado y la descripción. Ver el glosario.
- **El inner join reduce la muestra.** Solo quedan los viajes presentes en las tres fuentes y luego se eliminan outliers. La capa oro actual tiene **55,388 viajes**.
- **No hay contrafactual explícito.** Los datos no registran el costo ni la disponibilidad de los camiones que *no* se usaron, así que los ahorros son estimaciones bajo supuestos.
