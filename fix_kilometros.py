
import pandas as pd
import numpy as np
from pathlib import Path

DS_FILE_ADRESS = Path()
DATA_DIR = DS_FILE_ADRESS/'data'/'plata'
DATA_ADRESS = DATA_DIR/'viajes_foraneos_oro.csv'

# Cargar la Capa Oro y el catálogo
df = pd.read_csv(DATA_ADRESS)
df_cat = pd.read_csv('catalogo_distancias.csv')

# Limpiar y convertir a numérico los kilómetros en el catálogo
df_cat['Kilometros_Ruta'] = pd.to_numeric(df_cat['Kilometros_Ruta'], errors='coerce')

# Crear una tabla de referencia cruzada (mediana de distancia por Ciudad Destino)
valid_cat = df_cat.dropna(subset=['Kilometros_Ruta'])
medianas_destino = valid_cat.groupby('Ciudad Destino')['Kilometros_Ruta'].median().to_dict()

# Rellenar los nulos en el catálogo usando la mediana de la ciudad destino
df_cat['Kilometros_Ruta_Imputado'] = df_cat['Kilometros_Ruta'].fillna(df_cat['Ciudad Destino'].map(medianas_destino))

# Hacer un merge inteligente con el dataframe principal (viajes_foraneos_oro.csv)
# Si Kilometros_Ruta en df es NaN o 0, lo rellenamos con el valor imputado del catálogo
df = df.merge(df_cat[['PLANTA_ORIGEN', 'Ciudad Destino', 'Kilometros_Ruta_Imputado']], 
              on=['PLANTA_ORIGEN', 'Ciudad Destino'], 
              how='left', 
              suffixes=('', '_cat'))

# Actualizar Kilometros_Ruta donde falte
if 'Kilometros_Ruta_Imputado' in df.columns:
    df['Kilometros_Ruta'] = df['Kilometros_Ruta'].fillna(df['Kilometros_Ruta_Imputado'])
    df.drop(columns=['Kilometros_Ruta_Imputado'], inplace=True, errors='ignore')

# Fallback global por si acaso: usar la mediana general de la ciudad destino en todo el df
global_dest_medians = df.groupby('Ciudad Destino')['Kilometros_Ruta'].transform('median')
df['Kilometros_Ruta'] = df['Kilometros_Ruta'].fillna(global_dest_medians)

# Recalcular Tonelada-Kilometro y Costo_Ton_Km de forma impecable
df['Tonelada_Kilometro'] = df['Toneladas_Reales'] * df['Kilometros_Ruta']
df['Costo_Ton_Km'] = df['Monto total'] / df['Tonelada_Kilometro'].replace(0, np.nan)

# Guardar de vuelta la Capa Oro limpia
df.to_csv(DATA_ADRESS, index=False)
print("¡Capa Oro actualizada con éxito! Nulos restantes en Kilometros_Ruta:", df['Kilometros_Ruta'].isna().sum())
