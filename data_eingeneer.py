import pandas as pd
import numpy as np
import os
import requests
import time
from pathlib import Path
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

DS_FILE_ADRESS = Path()
DATA_DIR = DS_FILE_ADRESS/'data'/'plata'
DATA_ADRESS = DATA_DIR/'viajes_foraneos_plata.csv'
        
# --- MÓDULOS DE TIEMPO Y CAPACIDAD ---

def calcular_tiempo_viaje(df, col_egreso='FECHA_EGRESO', col_llegada='FECHA_VIAJE_FINALIZADO'):
    df = df.copy()
    df[col_egreso] = pd.to_datetime(df[col_egreso], errors='coerce')
    df[col_llegada] = pd.to_datetime(df[col_llegada], errors='coerce')
    df['Tiempo_Viaje_Horas'] = (df[col_llegada] - df[col_egreso]).dt.total_seconds() / 3600
    return df

def calcular_discrepancia_peso(df, col_programado='Programado (Peso)', col_real='Peso Total'):
    df = df.copy()
    df['Programado_kg'] = df[col_programado] * 1000
    df['Discrepancia_Peso_kg'] = df['Programado_kg'] - df[col_real]
    df['Ineficiencia_Capacidad'] = df['Discrepancia_Peso_kg'] > 0
    return df

def inferir_vehiculo_y_costos(df):
    df = df.copy()
    LIMITE_2_EJES = 32000
    LIMITE_3_EJES = 38500
    LIMITE_FULL = 46000
    
    condiciones = [
        (df['Programado_kg'] > LIMITE_3_EJES),
        (df['Programado_kg'] > LIMITE_2_EJES) & (df['Programado_kg'] <= LIMITE_3_EJES),
        (df['Programado_kg'] <= LIMITE_2_EJES) & (df['FAMILIA_CAMION_DESC'].astype(str).str.contains('3 EJES', case=False, na=False)),
        (df['Programado_kg'] <= LIMITE_2_EJES) & (df['FAMILIA_CAMION_DESC'].astype(str).str.contains('2 EJES', case=False, na=False))
    ]
    
    nomenclaturas = ['T3-S2-R4 (Full)', 'T3-S3 (3 Ejes)', 'T3-S3 (3 Ejes)', 'T3-S2 (2 Ejes)']
    df['Nomenclatura_Inferida'] = np.select(condiciones, nomenclaturas, default='Desconocido')
    
    capacidades = [LIMITE_FULL, LIMITE_3_EJES, LIMITE_3_EJES, LIMITE_2_EJES]
    df['Capacidad_Max_kg'] = np.select(condiciones, capacidades, default=LIMITE_2_EJES)
    
    df['Porcentaje_Utilizacion_Real'] = (df['Peso Total'] / df['Capacidad_Max_kg']) * 100
    df['Capacidad_Sobra_kg'] = df['Capacidad_Max_kg'] - df['Peso Total']
    
    df['Toneladas_Reales'] = df['Peso Total'] / 1000
    df['Toneladas_Maximas'] = df['Capacidad_Max_kg'] / 1000
    
    df['Costo_Ton_Real'] = df['Monto total'] / df['Toneladas_Reales'].replace(0, np.nan)
    df['Costo_Ton_Optimo'] = df['Monto total'] / df['Toneladas_Maximas']
    df['Sobrecosto_Ton'] = df['Costo_Ton_Real'] - df['Costo_Ton_Optimo']
    
    return df

# --- MÓDULOS DE DISTANCIA Y GEOLOCALIZACIÓN ---

def obtener_coordenadas(ubicaciones):
    geolocator = Nominatim(user_agent="ternium_logistics_project")
    diccionario_coords = {}
    print(f"Geocodificando {len(ubicaciones)} ubicaciones únicas...")
    for ciudad in ubicaciones:
        busqueda = f"{ciudad}, México"
        try:
            location = geolocator.geocode(busqueda, timeout=10)
            diccionario_coords[ciudad] = (location.latitude, location.longitude) if location else (None, None)
            time.sleep(1) 
        except GeocoderTimedOut:
            diccionario_coords[ciudad] = (None, None)
            time.sleep(2)
    return diccionario_coords

def calcular_distancia_osrm(coord_origen, coord_destino):
    if None in coord_origen or None in coord_destino:
        return None
    lon1, lat1 = coord_origen[1], coord_origen[0]
    lon2, lat2 = coord_destino[1], coord_destino[0]
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data['code'] == 'Ok':
                return data['routes'][0]['distance'] / 1000
    except requests.exceptions.RequestException:
        pass
    return None

def integrar_distancias(df, archivo_catalogo='catalogo_distancias.csv'):
    df = df.copy()
    if os.path.exists(archivo_catalogo):
        print(f"Cargando catálogo de distancias existente desde {archivo_catalogo}...")
        df_distancias = pd.read_csv(archivo_catalogo)
    else:
        print("Generando catálogo de distancias por primera vez (esto tomará unos minutos)...")
        rutas = df[['PLANTA_ORIGEN', 'Ciudad Destino']].drop_duplicates().dropna()
        lugares_unicos = set(rutas['PLANTA_ORIGEN']).union(set(rutas['Ciudad Destino']))
        coords_dict = obtener_coordenadas(lugares_unicos)
        
        print("Calculando kilómetros por ruta con OSRM...")
        distancias = []
        for _, row in rutas.iterrows():
            origen = row['PLANTA_ORIGEN']
            destino = row['Ciudad Destino']
            km = calcular_distancia_osrm(coords_dict.get(origen, (None, None)), coords_dict.get(destino, (None, None)))
            distancias.append({'PLANTA_ORIGEN': origen, 'Ciudad Destino': destino, 'Kilometros_Ruta': km})
            time.sleep(0.1)
            
        df_distancias = pd.DataFrame(distancias)
        df_distancias.to_csv(archivo_catalogo, index=False)
        print("Catálogo de distancias guardado exitosamente.")

    # Cruzar distancias con el dataset principal
    df = pd.merge(df, df_distancias, on=['PLANTA_ORIGEN', 'Ciudad Destino'], how='left')
    
    # Calcular Costo por Tonelada-Kilómetro
    df['Tonelada_Kilometro'] = df['Toneladas_Reales'] * df['Kilometros_Ruta']
    df['Costo_Ton_Km'] = df['Monto total'] / df['Tonelada_Kilometro'].replace(0, np.nan)
    
    return df

# --- LIMPIEZA Y EXPORTACIÓN ---

def limpiar_outliers_iqr(df, columnas):
    df_limpio = df.copy()
    for col in columnas:
        Q1 = df_limpio[col].quantile(0.25)
        Q3 = df_limpio[col].quantile(0.75)
        IQR = Q3 - Q1
        df_limpio = df_limpio[(df_limpio[col] >= (Q1 - 1.5 * IQR)) & (df_limpio[col] <= (Q3 + 1.5 * IQR))]
    return df_limpio

def exportar_capa_oro(df, ruta_salida=DATA_DIR/'viajes_foraneos_oro.csv'):
    try:
        df.to_csv(ruta_salida, sep=',', index=False, encoding='utf-8')
        print(f"\n[ÉXITO] Archivo Capa Oro exportado correctamente: {ruta_salida}")
        return True
    except Exception as e:
        print(f"\n[ERROR] No se pudo guardar el archivo Capa Oro: {str(e)}")
        return False

def ejecutar_pipeline_completo(ruta_archivo, sep=';', ruta_salida_oro=DATA_DIR/'viajes_foraneos_oro.csv'):
    print(f"Iniciando pipeline Medallion (Plata -> Oro) para: {ruta_archivo}")
    df = pd.read_csv(ruta_archivo, sep=sep)
    
    print("1. Calculando tiempos de viaje...")
    df = calcular_tiempo_viaje(df)
    
    print("2. Calculando discrepancias de peso...")
    df = calcular_discrepancia_peso(df)
    
    print("3. Infiriendo vehículos y estimando costos base...")
    df = inferir_vehiculo_y_costos(df)
    
    print("4. Integrando API de distancias y métricas Ton-Km...")
    df = integrar_distancias(df)
    
    print("5. Limpiando nulos y outliers...")
    df = df.dropna(subset=['Tiempo_Viaje_Horas', 'Discrepancia_Peso_kg', 'Costo_Ton_Real'])
    # Se añade Costo_Ton_Km a la limpieza si la distancia existe
    df_final = limpiar_outliers_iqr(df, ['Tiempo_Viaje_Horas', 'Discrepancia_Peso_kg', 'Sobrecosto_Ton'])
    
    print("6. Exportando a Capa Oro...")
    exportar_capa_oro(df_final, ruta_salida_oro)
    return df_final

if __name__ == '__main__':

    df_oro = ejecutar_pipeline_completo(DATA_ADRESS)
    
    if 'Costo_Ton_Km' in df_oro.columns:
        print("\nVista previa de métricas de transporte (Capa Oro):")
        print(df_oro[['PLANTA_ORIGEN', 'Ciudad Destino', 'Kilometros_Ruta', 'Costo_Ton_Km', 'Sobrecosto_Ton']].head().to_string())