import pandas as pd
import sqlite3
import datetime
import os
import logging

# 1. Configuración de Logging para Idempotencia y Trazabilidad
timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
logging.basicConfig(
    filename=f'etl_pipeline_{timestamp}.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

def extract_data(file_paths):
    dfs = {}
    for name, path in file_paths.items():
        try:
            # Usamos read_csv en lugar de read_excel. low_memory=False ayuda con tipos mixtos.
            dfs[name] = pd.read_csv(path, low_memory=False, encoding='utf-8-sig')
            # Limpiar espacios en blanco al inicio o final de los nombres de las columnas
            dfs[name].columns = dfs[name].columns.str.strip()
            logging.info(f"Archivo {name} cargado exitosamente. Filas: {len(dfs[name])}")
        except Exception as e:
            # Intento de fallback con otra codificación muy común en caso de error
            try:
                dfs[name] = pd.read_csv(path, low_memory=False, encoding='latin1')
                dfs[name].columns = dfs[name].columns.str.strip()
                logging.info(f"Archivo {name} cargado exitosamente (latin1). Filas: {len(dfs[name])}")
            except Exception as inner_e:
                logging.error(f"Error cargando {path}: {inner_e}")
    return dfs

def standardize_text(df, columns):
    """Estandariza los nombres a mayúsculas y elimina espacios innecesarios"""
    for col in columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()
    return df

def standardize_dates(df, columns):
    """Convierte columnas a formato datetime unificado"""
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    return df

def process_bronze_to_silver(dfs):
    silver_dfs = {}
    quarantine_dfs = []
    
    for name, df in dfs.items():
        original_len = len(df)
        
        # Asumimos que la columna clave se llama 'ID_VIAJE'. 
        if 'ID_VIAJE' not in df.columns:
            logging.warning(f"ID_VIAJE no encontrado en {name}. Archivo saltado.")
            continue
            
        # CUARENTENA 1: Nulos en ID_VIAJE
        q_nulls = df[df['ID_VIAJE'].isnull()].copy()
        if not q_nulls.empty:
            q_nulls['Razon_Rechazo'] = 'ID_VIAJE es nulo'
            q_nulls['Origen_Datos'] = name
            quarantine_dfs.append(q_nulls)
            
        df = df.dropna(subset=['ID_VIAJE']).copy()
        
        # CUARENTENA 2: Duplicados en ID_VIAJE
        q_dups = df[df.duplicated(subset=['ID_VIAJE'], keep='first')].copy()
        if not q_dups.empty:
            q_dups['Razon_Rechazo'] = 'ID_VIAJE duplicado (se conservó el primero)'
            q_dups['Origen_Datos'] = name
            quarantine_dfs.append(q_dups)
            
        df = df.drop_duplicates(subset=['ID_VIAJE'], keep='first').copy()
        
        # ESTANDARIZACIÓN
        cols_to_upper = ['PLANTA', 'PLANTA_ORIGEN', 'CIUDAD DESTINO', 'ESTADO DESTINO', 'DESTINO', 'FAMILIA_CAMION_DESC']
        df = standardize_text(df, cols_to_upper)
        
        date_cols = ['FECHA_LLEGADA', 'FECHA_SALIDA', 'FECHA_VIAJE_FINALIZADO', 'FECHA']
        df = standardize_dates(df, date_cols)
        
        silver_dfs[name] = df
        logging.info(f"{name}: {original_len} filas crudas -> {len(df)} filas Silver. {len(q_nulls) + len(q_dups)} a cuarentena.")
        
    quarantine_master = pd.concat(quarantine_dfs, ignore_index=True) if quarantine_dfs else pd.DataFrame()
    return silver_dfs, quarantine_master

def load_to_sqlite_and_join(silver_dfs, db_name="ternium_silver.db"):
    conn = sqlite3.connect(db_name)
    
    for name, df in silver_dfs.items():
        df.to_sql(name, conn, if_exists='replace', index=False)
        logging.info(f"Tabla {name} cargada a SQLite.")
        
    tables = list(silver_dfs.keys())
    if not tables:
        return pd.DataFrame(), conn

    # Unificación en Pandas usando 'costos' como base
    base_table = 'costos' if 'costos' in tables else tables[0]
    unified_df = silver_dfs[base_table].copy()
    
    other_tables = [t for t in tables if t != base_table]
    for table in other_tables:
        # Se utilizan sufijos para garantizar que NINGUNA columna se sobreescriba o borre
        # Si 'Peso' o 'Costo' existen en varios CSV, se conservarán como 'Peso', 'Peso_tiempos', etc.
        unified_df = pd.merge(
            unified_df, 
            silver_dfs[table], 
            on='ID_VIAJE', 
            how='left', 
            suffixes=('', f'_{table}')
        )
        
    try:
        unified_df.to_sql('viajes_unificados', conn, if_exists='replace', index=False)
        logging.info(f"Join exitoso. Total de filas unificadas: {len(unified_df)}")
    except Exception as e:
        logging.error(f"Error guardando tabla unificada en SQLite: {e}")
            
    return unified_df, conn

def validate_silver(df):
    if df.empty:
        logging.error("VALIDACIÓN FALLIDA: El DataFrame resultante está vacío.")
        return False
    
    if 'ID_VIAJE' not in df.columns:
        logging.error("VALIDACIÓN FALLIDA: Falta la columna clave ID_VIAJE.")
        return False
        
    if df['ID_VIAJE'].duplicated().any():
        dups = df['ID_VIAJE'].duplicated().sum()
        logging.error(f"VALIDACIÓN FALLIDA: Existen {dups} ID_VIAJE duplicados tras el Join.")
        return False
        
    logging.info("VALIDACIÓN EXITOSA: La capa Silver cumple con los requisitos estructurales.")
    return True

if __name__ == "__main__":
    file_paths = {
        'detalles_viajes': 'data/Detalles viajes foraneos ultimo año.csv',
        'ciclos': 'data/Detalle Ciclos de Viajes Despachados.csv',
        'tiempos': 'data/Tiempos Viajes Foraneos.csv',
        'costos': 'data/Viajes con Costos V2.csv'
    }
    
    print(f"Iniciando pipeline ETL a las {timestamp}...")
    
    dfs = extract_data(file_paths)
    silver_dfs, quarantine_df = process_bronze_to_silver(dfs)
    
    if not quarantine_df.empty:
        q_filename = f'cuarentena_rechazados_{timestamp}.csv'
        quarantine_df.to_csv(q_filename, index=False)
        print(f"-> {len(quarantine_df)} registros enviados a cuarentena. Archivo: {q_filename}")
        
    unified_silver, db_conn = load_to_sqlite_and_join(silver_dfs, db_name='ternium_silver.db')
    
    if not unified_silver.empty:
        is_valid = validate_silver(unified_silver)
        
        silver_filename = f'silver_viajes_unificados_{timestamp}.csv'
        unified_silver.to_csv(silver_filename, index=False)
        print(f"-> Datos Silver unificados y guardados en {silver_filename} (Filas: {len(unified_silver)})")
        print(f"-> Estatus de Validación: {'APROBADO' if is_valid else 'FALLIDO (ver logs)'}")
        
    print(f"Revisar el archivo 'etl_pipeline_{timestamp}.log' para detalles técnicos.")
    db_conn.close()
