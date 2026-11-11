# ETL plata → oro (v2)

    python etl_oro.py --plata data/plata/viajes_foraneos_plata.csv --sep ";" \
        --catalogo data/distancias_v2/catalogo_distancias_v2.csv --salida data/oro_v2

Salidas en `--salida`: `viajes_foraneos_oro.csv`, `viajes_rechazados.csv` (con motivo),
`rutas_pendientes.csv` (rutas con km faltante o sospechoso, ordenadas por viajes),
`capacidades_config.csv` (editable), `reporte_calidad.json`.

## Qué cambió respecto a data_engineer.py
| Antes | Ahora |
|---|---|
| Outliers IQR **borraban** viajes (incluidos los largos y los más ineficientes) | Se **marcan** (`Flag_Outlier_*`, z-MAD por ruta); solo se rechazan los físicamente imposibles |
| Tipo "Full" por `Programado_kg > 38500` (circular) | Tipo solo por el texto declarado; el exceso de carga queda en `Excede_Capacidad` |
| Texto sin clasificar caía a "2 ejes" | `SIN_CLASIFICAR` + conteo en el reporte |
| `'CAMIONETA 3.5'` nunca coincidía con `CAMIONETA 35` | Regla corregida (capacidad 3,500 kg) |
| Km nulos → mediana por destino/origen/global | Nunca se imputa: `Km_Fuente='faltante'` |
| Km imposibles entraban a `Costo_Ton_Km` | `Km_Sospechoso` (velocidad implícita > 90 o < 3 km/h, km < 5) → `Costo_Ton_Km` = NaN |
| Capacidades en el código, sin fuente | `capacidades_config.csv` con `Verificado_NOM012` |
| Ortografía de destinos sin control | Grafías unificadas; correcciones también al catálogo |
| `Ineficiencia_Capacidad` (discrepancia > 0 ±100 kg) | Eliminada; usar `Flag_Util_Baja_70` |

Columnas nuevas: `Km_Fuente, Km_Confiable, Km_Sospechoso, Vel_Implicita_kmh, Excede_Capacidad,
Flag_*, Ruta_ID, Mes_Egreso, Semana_Egreso`.

## Pendientes que el ETL no puede resolver solo
1. Completar y corregir kilómetros (ver `rutas_pendientes.csv`).
2. Verificar `capacidades_config.csv` contra la NOM-012-SCT-2 (peso bruto menos tara).
3. `Costo_Ton_Optimo` / `Sobrecosto_Ton` suponen consolidación total: son cota superior laxa, no ahorro.
