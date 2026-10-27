
import pandas as pd
from pathlib import Path
import numpy as np

def calcular_tiempo_viaje(df, col_egreso='FECHA_EGRESO', col_llegada='FECHA_VIAJE_FINALIZADO'):

    df = df.copy()
    df[col_egreso] = pd.to_datetime(df[col_egreso], errors='coerce')
    df[col_llegada] = pd.to_datetime(df[col_llegada], errors='coerce')
    df['Tiempo_Viaje_Horas'] = (df[col_llegada] - df[col_egreso]).dt.total_seconds() / 3600
    return df

def calcular_discrepancia_peso(df, col_programado='Programado (Peso)', col_real='Peso Total'):
    """
    Estandariza unidades (toneladas a kg) y calcula la discrepancia de peso.
    """
    df = df.copy()
    df['Programado_kg'] = df[col_programado] * 1000
    df['Discrepancia_Peso_kg'] = df['Programado_kg'] - df[col_real]
    df['Ineficiencia_Capacidad'] = df['Discrepancia_Peso_kg'] > 0
    return df

def inferir_vehiculo_y_costos(df):
    """
    Infiere el tipo de camión real y calcula la capacidad de sobra junto con 
    los indicadores de costo por tonelada.
    """
    df = df.copy()
    
    # 1. Definir los límites teóricos de Carga Útil (Payload)
    LIMITE_2_EJES = 32000
    LIMITE_3_EJES = 38500
    LIMITE_FULL = 46000
    
    # 2. Motor de Inferencia
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
    
    # 3. Capacidad de Sobra y Utilización
    df['Porcentaje_Utilizacion_Real'] = (df['Peso Total'] / df['Capacidad_Max_kg']) * 100
    df['Capacidad_Sobra_kg'] = df['Capacidad_Max_kg'] - df['Peso Total']
    
    # 4. Cálculo de Costos por Tonelada
    # Convertimos los kilogramos a toneladas para hacer la división
    df['Toneladas_Reales'] = df['Peso Total'] / 1000
    df['Toneladas_Maximas'] = df['Capacidad_Max_kg'] / 1000
    
    # Costo por tonelada basado en lo que realmente se movió (evitando división por cero)
    df['Costo_Ton_Real'] = df['Monto total'] / df['Toneladas_Reales'].replace(0, np.nan)
    
    # Costo por tonelada ideal (si el camión se hubiera llenado a tope)
    df['Costo_Ton_Optimo'] = df['Monto total'] / df['Toneladas_Maximas']
    
    # Sobrecosto (cuánto se pagó de más por cada tonelada debido a llevar espacio vacío)
    df['Sobrecosto_Ton'] = df['Costo_Ton_Real'] - df['Costo_Ton_Optimo']
    
    return df

def limpiar_outliers_iqr(df, columnas):
    """
    Filtra valores atípicos (outliers) usando el método del Rango Intercuartílico (IQR).
    """
    df_limpio = df.copy()
    for col in columnas:
        Q1 = df_limpio[col].quantile(0.25)
        Q3 = df_limpio[col].quantile(0.75)
        IQR = Q3 - Q1
        
        # Definir los límites
        limite_inferior = Q1 - 1.5 * IQR
        limite_superior = Q3 + 1.5 * IQR
        
        # Aplicar el filtro para mantener solo los datos dentro del rango normal
        df_limpio = df_limpio[(df_limpio[col] >= limite_inferior) & (df_limpio[col] <= limite_superior)]
        
    return df_limpio

def exportar_capa_oro(df, ruta_salida='viajes_foraneos_oro.csv'):
    """
    Guarda el DataFrame procesado en un nuevo archivo CSV (Capa Oro),
    asegurando el formato correcto para análisis posterior.
    """
    try:
        # Guardamos usando el separador estándar por comas para mayor compatibilidad
        df.to_csv(ruta_salida, sep=',', index=False, encoding='utf-8')
        tamaño_mb = os.path.getsize(ruta_salida) / (1024 * 1024)
        print(f"\n[ÉXITO] Archivo Capa Oro exportado correctamente: {ruta_salida} ({tamaño_mb:.2f} MB)")
        return True
    except Exception as e:
        print(f"\n[ERROR] No se pudo guardar el archivo Capa Oro: {str(e)}")
        return False

def ejecutar_pipeline_transformacion(ruta_archivo, sep=';',ruta_salida_oro='viajes_foraneos_oro.csv'):
    """
    Ejecuta el pipeline completo de limpieza y transformaciones.
    """
    print(f"Cargando dataset: {ruta_archivo}")
    df = pd.read_csv(ruta_archivo, sep=sep)
    
    print("Calculando tiempo de viaje...")
    df = calcular_tiempo_viaje(df)
    
    print("Calculando discrepancia de peso...")
    df = calcular_discrepancia_peso(df)
    
    print("Infiriendo vehículos y calculando costos de capacidad...")
    df = inferir_vehiculo_y_costos(df)
    
    df = df.dropna(subset=['Tiempo_Viaje_Horas', 'Discrepancia_Peso_kg'])
    
    print("Limpiando outliers...")
    df_final = limpiar_outliers_iqr(df, ['Tiempo_Viaje_Horas', 'Discrepancia_Peso_kg'])
    
    print("Exportando a Capa Oro...")
    exportar_capa_oro(df_final, ruta_salida_oro)
    
    return df_final

if __name__ == '__main__':
    
    DS_FILE_ADRESS = Path()
    DATA_ADRESS = DS_FILE_ADRESS/'data'/'plata'/'viajes_foraneos_plata.csv'
    
    df_limpio = ejecutar_pipeline_transformacion(DATA_ADRESS)
    
    columnas_interes = ['Nomenclatura_Inferida', 'Capacidad_Sobra_kg', 'Costo_Ton_Real', 'Costo_Ton_Optimo', 'Sobrecosto_Ton']
    print("\nVista previa de las nuevas variables de costos y capacidad:")
    print(df_limpio[columnas_interes].head().round(2).to_string())
