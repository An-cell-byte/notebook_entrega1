"""
ETL plata -> oro (v2) para viajes foráneos.

Principios (cada uno corrige un problema detectado en data_engineer.py):
  1. NUNCA se imputan kilómetros con medianas. Si no hay dato confiable queda NaN y
     se marca la fuente; la lista de rutas por completar sale en rutas_pendientes.csv.
  2. NUNCA se descartan outliers estadísticos: se marcan con Flag_*. Solo se rechazan
     (a viajes_rechazados.csv, con motivo) los registros físicamente imposibles.
  3. El tipo de camión se clasifica por el texto declarado (normalizado). Ya no se
     reclasifica por el peso de la carga (era circular) ni cae por defecto a "2 ejes".
  4. Las capacidades viven en capacidades_config.csv (editable, con campo de verificación
     contra la NOM-012-SCT-2).
  5. El script no sobrescribe su entrada y deja un reporte de calidad auditable.
Uso:
  python etl_oro.py --plata data/plata/viajes_foraneos_plata.csv --sep ";" \
      --catalogo catalogo_distancias.csv --salida data/oro_v2
"""
import argparse, json, re, unicodedata
from pathlib import Path
import numpy as np
import pandas as pd

REQUERIDAS = ['ID_VIAJE', 'Ciudad Destino', 'PLANTA_ORIGEN', 'FECHA_EGRESO',
              'FECHA_VIAJE_FINALIZADO', 'Programado (Peso)', 'Peso Total',
              'Monto total', 'FAMILIA_CAMION_DESC', 'Transportista']

# Umbrales de plausibilidad (se reportan; ajustables)
VEL_MAX_KMH = 90      # velocidad media implícita (incluye esperas): arriba de esto es imposible
VEL_MIN_KMH = 3       # abajo de esto el km casi seguro es erróneo
KM_MIN = 5
MAD_Z = 5.0
MIN_N_GRUPO = 8

# Reglas en orden: la primera que coincide gana
REGLAS_TIPO = [
    (r'\bFULL\b',               'T3-S2-R4 (Full)'),
    (r'PORTACINTA|BIG COIL',    'T3-S3 (Portacintas/Big Coil)'),
    (r'53 PIES',                'Plataforma larga 53 pies'),
    (r'48 PIES',                'Plataforma larga 48 pies'),
    (r'TORTONETA',              'Tortoneta'),
    (r'\bTORTON\b',             'Torton'),
    (r'CAMIONETA',              'Camioneta 3.5'),
    (r'CAMA BAJA',              'Cama Baja Doble Piso'),
    (r'\bHEAVY\b',              'Heavy'),
    (r'3 EJES',                 'T3-S3 (3 Ejes)'),
    (r'2 EJES',                 'T3-S2 (2 Ejes)'),
]

CAPACIDADES_DEFAULT = pd.DataFrame([
    ('T3-S2-R4 (Full)', 51500), ('T3-S3 (3 Ejes)', 38500),
    ('T3-S3 (Portacintas/Big Coil)', 38500), ('T3-S2 (2 Ejes)', 32000),
    ('Plataforma larga 48 pies', 25000), ('Plataforma larga 53 pies', 24000),
    ('Torton', 20000), ('Tortoneta', 12000), ('Camioneta 3.5', 3500),
    ('Cama Baja Doble Piso', 35000), ('Heavy', 40000),
], columns=['Nomenclatura_Inferida', 'Capacidad_Max_kg'])
CAPACIDADES_DEFAULT['Verificado_NOM012'] = False
CAPACIDADES_DEFAULT['Fuente'] = 'heredado de data_engineer.py (carga útil supuesta); pendiente de verificar'

CORRECCIONES_DESTINO = {  # normalizado -> nombre corregido
    'CHILPANCILGO': 'Chilpancingo',
    'S CRIST DE LAS CASAS': 'San Cristóbal de las Casas',
}


def norm(s):
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode()
    return re.sub(r'\s+', ' ', s).strip().upper()


def clasificar(familia: pd.Series) -> pd.Series:
    t = familia.map(norm)
    out = pd.Series('SIN_CLASIFICAR', index=familia.index, dtype=object)
    asignado = pd.Series(False, index=familia.index)
    for patron, nombre in REGLAS_TIPO:
        m = t.str.contains(patron, regex=True) & ~asignado
        out[m] = nombre
        asignado |= m
    return out


def flag_mad(valor: pd.Series, grupo: pd.Series, thr=MAD_Z, min_n=MIN_N_GRUPO) -> pd.Series:
    """Outlier robusto (z-MAD sobre log) dentro de cada grupo; solo marca, no borra."""
    x = np.log(valor.where(valor > 0))
    med = x.groupby(grupo).transform('median')
    mad = (x - med).abs().groupby(grupo).transform('median')
    n = x.groupby(grupo).transform('count')
    z = 0.6745 * (x - med) / mad.clip(lower=0.05)  # piso: evita MAD=0 en rutas con tarifa fija
    return ((z.abs() > thr) & (n >= min_n)).fillna(False)


# ---------------------------------------------------------------- etapas
def validar_esquema(df):
    faltan = [c for c in REQUERIDAS if c not in df.columns]
    if faltan:
        raise ValueError(f'Faltan columnas en la capa de plata: {faltan}')


def limpiar_y_rechazar(df, rep):
    df = df.copy()
    for c in ['Ciudad Destino', 'PLANTA_ORIGEN', 'Transportista', 'FAMILIA_CAMION_DESC']:
        df[c] = df[c].astype('string').str.strip()
    corr = df['Ciudad Destino'].map(norm).map(CORRECCIONES_DESTINO)
    rep['destinos_corregidos'] = int(corr.notna().sum())
    df['Ciudad Destino'] = corr.fillna(df['Ciudad Destino'])
    for col in ['Ciudad Destino', 'PLANTA_ORIGEN']:
        k = df[col].map(lambda v: norm(v) if pd.notna(v) else v)
        canon = df.groupby(k)[col].agg(lambda x: x.value_counts().index[0])
        antes = df[col].nunique()
        df[col] = k.map(canon).where(k.notna(), df[col])
        rep[f'{col}_grafias_unificadas'] = int(antes - df[col].nunique())

    for c in ['FECHA_EGRESO', 'FECHA_VIAJE_FINALIZADO']:
        df[c] = pd.to_datetime(df[c], errors='coerce')
    for c in ['Programado (Peso)', 'Peso Total', 'Monto total']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df['Tiempo_Viaje_Horas'] = (df['FECHA_VIAJE_FINALIZADO'] - df['FECHA_EGRESO']).dt.total_seconds() / 3600

    motivo = pd.Series('', index=df.index, dtype=object)
    def marca(mask, txt):
        nuevo = mask & (motivo == '')
        motivo[nuevo] = txt
    marca(df['ID_VIAJE'].isna(), 'ID_VIAJE nulo')
    marca(df['ID_VIAJE'].duplicated(keep='first'), 'ID_VIAJE duplicado')
    marca(df['FECHA_EGRESO'].isna() | df['FECHA_VIAJE_FINALIZADO'].isna(), 'fecha inválida')
    marca(df['Tiempo_Viaje_Horas'] <= 0, 'tiempo de viaje <= 0')
    marca(df['Peso Total'].isna() | (df['Peso Total'] <= 0), 'peso nulo o <= 0')
    marca(df['Monto total'].isna() | (df['Monto total'] <= 0), 'monto nulo o <= 0')
    marca(df['PLANTA_ORIGEN'].isna() | df['Ciudad Destino'].isna(), 'origen o destino nulo')
    rech = df[motivo != ''].assign(Motivo_Rechazo=motivo[motivo != ''])
    rep['rechazados_por_motivo'] = rech['Motivo_Rechazo'].value_counts().to_dict()
    return df[motivo == ''].copy(), rech


def metricas_capacidad(df, capacidades, rep):
    df = df.copy()
    df['Nomenclatura_Inferida'] = clasificar(df['FAMILIA_CAMION_DESC'])
    rep['sin_clasificar'] = int((df['Nomenclatura_Inferida'] == 'SIN_CLASIFICAR').sum())
    df = df.merge(capacidades[['Nomenclatura_Inferida', 'Capacidad_Max_kg']],
                  on='Nomenclatura_Inferida', how='left', validate='m:1')
    df['Programado_kg'] = df['Programado (Peso)'] * 1000
    df['Discrepancia_Peso_kg'] = df['Programado_kg'] - df['Peso Total']
    df['Toneladas_Reales'] = df['Peso Total'] / 1000
    df['Toneladas_Maximas'] = df['Capacidad_Max_kg'] / 1000
    df['Porcentaje_Utilizacion_Real'] = df['Peso Total'] / df['Capacidad_Max_kg'] * 100
    df['Capacidad_Sobra_kg'] = df['Capacidad_Max_kg'] - df['Peso Total']
    df['Excede_Capacidad'] = df['Porcentaje_Utilizacion_Real'] > 100
    df['Costo_Ton_Real'] = df['Monto total'] / df['Toneladas_Reales']
    # OJO: supone que la misma tarifa movería la capacidad plena (consolidación total).
    # Es una cota superior laxa, no un ahorro ejecutable.
    df['Costo_Ton_Optimo'] = df['Monto total'] / df['Toneladas_Maximas']
    df['Sobrecosto_Ton'] = df['Costo_Ton_Real'] - df['Costo_Ton_Optimo']
    rep['excede_capacidad'] = int(df['Excede_Capacidad'].sum())
    return df


def integrar_distancias(df, ruta_catalogo, rep):
    df = df.copy()
    df['_o'] = df['PLANTA_ORIGEN'].map(norm)
    df['_d'] = df['Ciudad Destino'].map(norm)
    if ruta_catalogo and Path(ruta_catalogo).exists():
        cat = pd.read_csv(ruta_catalogo)
        cat['Kilometros_Ruta'] = pd.to_numeric(cat['Kilometros_Ruta'], errors='coerce')
        if 'Km_Fuente' not in cat.columns:
            cat['Km_Fuente'] = 'catalogo'
        cat['Ciudad Destino'] = cat['Ciudad Destino'].map(lambda v: CORRECCIONES_DESTINO.get(norm(v), v))
        cat['_o'] = cat['PLANTA_ORIGEN'].map(norm)
        cat['_d'] = cat['Ciudad Destino'].map(norm)
        cat = cat.sort_values('Kilometros_Ruta').drop_duplicates(['_o', '_d', 'Kilometros_Ruta'], keep='first')
        dup = cat[cat.duplicated(['_o', '_d'], keep=False) & cat['Kilometros_Ruta'].notna()]
        if len(dup):
            raise ValueError(f'catálogo con km contradictorios para la misma ruta:\n{dup.head()}')
        cat = cat.sort_values('Kilometros_Ruta', na_position='last').drop_duplicates(['_o', '_d'], keep='first')
        n0 = len(df)
        df = df.merge(cat[['_o', '_d', 'Kilometros_Ruta', 'Km_Fuente']], on=['_o', '_d'],
                      how='left', validate='m:1')
        assert len(df) == n0, 'el merge de distancias multiplicó filas'
    else:
        df['Kilometros_Ruta'], df['Km_Fuente'] = np.nan, np.nan
        rep['aviso_catalogo'] = 'no se encontró catálogo de distancias'
    df['Km_Fuente'] = df['Km_Fuente'].where(df['Kilometros_Ruta'].notna(), 'faltante')

    ruta = df['PLANTA_ORIGEN'] + ' | ' + df['Ciudad Destino']
    df['Ruta_ID'] = ruta
    t_med = df.groupby('Ruta_ID')['Tiempo_Viaje_Horas'].transform('median')
    df['Vel_Implicita_kmh'] = df['Kilometros_Ruta'] / t_med
    df['Km_Sospechoso'] = df['Kilometros_Ruta'].notna() & (
        (df['Vel_Implicita_kmh'] > VEL_MAX_KMH) | (df['Vel_Implicita_kmh'] < VEL_MIN_KMH)
        | (df['Kilometros_Ruta'] < KM_MIN))
    df['Km_Confiable'] = df['Kilometros_Ruta'].notna() & ~df['Km_Sospechoso']
    df['Tonelada_Kilometro'] = df['Toneladas_Reales'] * df['Kilometros_Ruta'].where(df['Km_Confiable'])
    df['Costo_Ton_Km'] = df['Monto total'] / df['Tonelada_Kilometro']
    df = df.drop(columns=['_o', '_d'])
    rep['km'] = {'viajes_km_confiable': int(df['Km_Confiable'].sum()),
                 'viajes_km_faltante': int((df['Km_Fuente'] == 'faltante').sum()),
                 'viajes_km_sospechoso': int(df['Km_Sospechoso'].sum())}
    return df


def marcar_outliers(df, rep):
    df = df.copy()
    df['Flag_Outlier_Costo_Ton'] = flag_mad(df['Costo_Ton_Real'], df['Ruta_ID'])
    df['Flag_Outlier_Tiempo'] = flag_mad(df['Tiempo_Viaje_Horas'], df['Ruta_ID'])
    df['Flag_Util_Baja_70'] = df['Porcentaje_Utilizacion_Real'] < 70
    rep['flags'] = {c: int(df[c].sum()) for c in
                    ['Flag_Outlier_Costo_Ton', 'Flag_Outlier_Tiempo', 'Flag_Util_Baja_70']}
    return df


def ventana(df, rep):
    mes = df['FECHA_EGRESO'].dt.to_period('M').astype(str)
    df['Mes_Egreso'] = mes
    df['Semana_Egreso'] = df['FECHA_EGRESO'].dt.to_period('W').astype(str)
    cnt = mes.value_counts().sort_index()
    mediana = cnt.median()
    rep['ventana'] = {'egreso_min': str(df['FECHA_EGRESO'].min()), 'egreso_max': str(df['FECHA_EGRESO'].max()),
                      'viajes_por_mes': cnt.to_dict(),
                      'meses_con_posible_hueco': [m for m, c in cnt.items() if c < 0.8 * mediana]}
    return df


def rutas_pendientes(df):
    g = df.groupby('Ruta_ID').agg(PLANTA_ORIGEN=('PLANTA_ORIGEN', 'first'), Ciudad_Destino=('Ciudad Destino', 'first'),
                                  Viajes=('ID_VIAJE', 'size'), Kilometros_Ruta=('Kilometros_Ruta', 'first'),
                                  Vel_Implicita_kmh=('Vel_Implicita_kmh', 'first'),
                                  Faltante=('Km_Fuente', lambda s: (s == 'faltante').all()),
                                  Sospechoso=('Km_Sospechoso', 'any'))
    g = g[g.Faltante | g.Sospechoso].sort_values('Viajes', ascending=False)
    g['Pct_Acumulado_Viajes'] = (g.Viajes.cumsum() / g.Viajes.sum() * 100).round(1)
    return g.reset_index()


def ejecutar(plata, sep, catalogo, salida, capacidades_csv=None):
    salida = Path(salida); salida.mkdir(parents=True, exist_ok=True)
    rep = {}
    df = pd.read_csv(plata, sep=sep)
    validar_esquema(df)
    rep['filas_plata'] = len(df)
    capacidades = pd.read_csv(capacidades_csv) if capacidades_csv and Path(capacidades_csv).exists() else CAPACIDADES_DEFAULT
    if not capacidades.get('Verificado_NOM012', pd.Series([False])).all():
        rep['aviso_capacidades'] = 'hay capacidades sin verificar contra NOM-012-SCT-2'
    df, rech = limpiar_y_rechazar(df, rep)
    df = metricas_capacidad(df, capacidades, rep)
    df = integrar_distancias(df, catalogo, rep)
    df = marcar_outliers(df, rep)
    df = ventana(df, rep)
    rep['filas_oro'] = len(df)
    assert rep['filas_oro'] + len(rech) == rep['filas_plata'], 'las filas no cuadran'
    df.to_csv(salida / 'viajes_foraneos_oro.csv', index=False, encoding='utf-8')
    rech.to_csv(salida / 'viajes_rechazados.csv', index=False, encoding='utf-8')
    rutas_pendientes(df).to_csv(salida / 'rutas_pendientes.csv', index=False, encoding='utf-8')
    capacidades.to_csv(salida / 'capacidades_config.csv', index=False)
    (salida / 'reporte_calidad.json').write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    return df, rep


if __name__ == '__main__':
    
    DS_FILE_ADRESS = Path()
    DATA_DIR = DS_FILE_ADRESS/'data'/'plata'
    DATA_ADRESS = DATA_DIR/'viajes_foraneos_plata.csv'
    
    ap = argparse.ArgumentParser()
    ap.add_argument('--plata', required=True); ap.add_argument('--sep', default=';')
    ap.add_argument('--catalogo', default='catalogo_distancias.csv')
    ap.add_argument('--salida', default='data/oro_v2'); ap.add_argument('--capacidades', default=None)
    a = ap.parse_args()
    _, r = ejecutar(a.plata, a.sep, a.catalogo, a.salida, a.capacidades)
    print(json.dumps(r, indent=2, ensure_ascii=False, default=str))
