
import pandas as pd
import numpy as np
from pathlib import Path

DS_FILE_ADRESS = Path()
DATA_DIR = DS_FILE_ADRESS/'data'/'plata'
DATA_ADRESS = DATA_DIR/'viajes_foraneos_oro.csv'

df = pd.read_csv(DATA_ADRESS)

# Para los que aún tienen NaN en Kilometros_Ruta, asignamos la mediana absoluta de todo el dataset para esa Ciudad Destino, 
# o una estimación basada en el costo total (si hay correlación) o la mediana global por origen.
median_por_origen = df.groupby('PLANTA_ORIGEN')['Kilometros_Ruta'].transform('median')
df['Kilometros_Ruta'] = df['Kilometros_Ruta'].fillna(median_por_origen)

# Si aún quedan algunos, usar la mediana general de la Capa Oro
df['Kilometros_Ruta'] = df['Kilometros_Ruta'].fillna(df['Kilometros_Ruta'].median())

# Recalcular métricas finales
df['Tonelada_Kilometro'] = df['Toneladas_Reales'] * df['Kilometros_Ruta']
df['Costo_Ton_Km'] = df['Monto total'] / df['Tonelada_Kilometro'].replace(0, np.nan)

df.to_csv(DATA_ADRESS, index=False)
print("Nulos finales:", df['Kilometros_Ruta'].isna().sum())
