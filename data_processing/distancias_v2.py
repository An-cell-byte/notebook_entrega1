"""
Catálogo de distancias v2 (sin coordenadas de plantas: se trabaja con CIUDADES).

Flujo (desde la raíz del proyecto; las rutas se interpretan desde ahí):
  1. python data_processing/etl_oro.py ...                   -> data/oro_v2/viajes_foraneos_oro.csv
  2. python data_processing/distancias_v2.py --solo-tablas   -> genera config/plantas.csv y config/destinos_canonicos.csv
     (revisas/completas esas tablas a mano; son la fuente única de verdad)
  3. python data_processing/distancias_v2.py                 -> geocodifica + rutea; escribe catalogo_distancias_v2.csv
  4. python data_processing/etl_oro.py ...                   (vuelve a correr el ETL con el catálogo nuevo)

Garantías:
  * Todo lo que consulta a Nominatim/OSRM se guarda en caché (se puede interrumpir y reanudar).
  * Un fallo de red NO se guarda como "sin ruta": se reintenta en la siguiente corrida.
  * Multidestino (coma) y regiones (+) no tienen km puntual: salen con Km_Fuente explícita y NaN.
  * Nunca se imputa por medianas. Si OSRM no encuentra ruta, se usa línea recta x factor de carretera
    calibrado con las rutas que sí salieron de OSRM, y queda marcado como 'estimado_haversine'.
  * Lo ambiguo (nombre que cae en varios estados, estado que no coincide) va a geocoding_revisar.csv.
"""
import argparse, json, math, re, time
from pathlib import Path
import numpy as np
import pandas as pd
from etl_oro import norm

BBOX_MX = (14.0, 33.5, -119.0, -86.0)   # lat_min, lat_max, lon_min, lon_max
FACTOR_DEFAULT = 1.3
ABREV = [(r'\bSta\b', 'Santa'), (r'\bSn\b', 'San'), (r'\bCd\b', 'Ciudad'), (r'\bStgo\b', 'Santiago'),
         (r'\bEdo\b', 'Estado')]
PARTICULAS = {'De', 'Del', 'La', 'Las', 'Los', 'El', 'Y'}

# Sugerencias para nombres truncados o pegados. Son propuestas: quedan con Confirmado=False.
SUGERENCIAS = {
    norm('S Crist de las Casas'): ('San Cristóbal de las Casas', 'Chiapas'),
    norm('Chilpancilgo'): ('Chilpancingo de los Bravo', 'Guerrero'),
    norm('S FelipeTeotlalcingo'): ('San Felipe Teotlalcingo', 'Puebla'),
    norm('S.SALVADOR ATENCO'): ('San Salvador Atenco', 'Estado de México'),
    norm('Benemerito de las A'): ('Benemérito de las Américas', 'Chiapas'),
    norm('San Martin de las P'): ('San Martín de las Pirámides', 'Estado de México'),
    norm('Ixtlahuacan de los M'): ('Ixtlahuacán de los Membrillos', 'Jalisco'),
}
# Plantas: solo se prellena lo que el propio nombre indica. Lo demás lo completas tú.
PISTAS_PLANTAS = {
    'CEDI Mexico': ('Ciudad de México', 'Ciudad de México'), 'CEDI Guadalajara': ('Guadalajara', 'Jalisco'),
    'CEDI Puebla': ('Puebla', 'Puebla'), 'Largos Puebla': ('Puebla', 'Puebla'),
    'CEDI Tuxtla': ('Tuxtla Gutiérrez', 'Chiapas'), 'CEDI Veracruz': ('Veracruz', 'Veracruz'),
    'Largos Apodaca': ('Apodaca', 'Nuevo León'), 'CSI Apodaca': ('Apodaca', 'Nuevo León'),
    'CSC Apodaca': ('Apodaca', 'Nuevo León'), 'Pesquería': ('Pesquería', 'Nuevo León'),
    'CSI San Luis Potosi': ('San Luis Potosí', 'San Luis Potosí'),
}


# ------------------------------------------------------------------ lectura/escritura segura
import os, shutil


def leer_csv_robusto(path, **kw):
    """Lee CSV de Excel/Numbers: BOM UTF-8, separador ; o , y archivo vacío (devuelve None)."""
    p = Path(path)
    if not p.exists():
        return None
    if p.stat().st_size == 0:
        print(f'AVISO: {p} está vacío (0 bytes); se trata como si no existiera.', flush=True)
        return None
    with open(p, encoding='utf-8-sig') as f:
        primera = f.readline()
    sep = ';' if primera.count(';') > primera.count(',') else ','
    try:
        return pd.read_csv(p, sep=sep, encoding='utf-8-sig', **kw)
    except pd.errors.EmptyDataError:
        print(f'AVISO: {p} no tiene columnas; se trata como si no existiera.', flush=True)
        return None


def _alinear_columnas(df, cols):
    """Acepta encabezados en minúsculas, con espacios o guiones (los que deja Excel/Numbers)."""
    k = lambda s: re.sub(r'[\s\-]+', '_', str(s).strip().lower())
    canon = {k(c): c for c in cols}
    return df.rename(columns={c: canon[k(c)] for c in df.columns if k(c) in canon})


def _exigir_columnas(df, cols, path):
    faltan = [c for c in cols if c not in df.columns]
    if faltan:
        raise ValueError(f'{path}: faltan las columnas {faltan}. Columnas encontradas: {list(df.columns)}')


def _es_verdadero(s):
    return s.astype(str).str.strip().str.lower().isin({'true', 'verdadero', '1', 'si', 'sí', 'x'})


def _csv(df, path):
    """Escritura atómica: si se interrumpe, no deja un archivo a medias o vacío."""
    path = Path(path); tmp = path.with_name(path.name + '.tmp')
    df.to_csv(tmp, index=False, encoding='utf-8')
    os.replace(tmp, path)


def _respaldar(path):
    p = Path(path)
    if p.exists() and p.stat().st_size > 0:
        shutil.copyfile(p, p.with_name(p.stem + '.bak' + p.suffix))


# ------------------------------------------------------------------ limpieza de nombres
def tipo_destino(crudo):
    if ',' in crudo: return 'multidestino'
    if '+' in crudo: return 'region'
    return 'puntual'


def limpiar_destino(crudo):
    """Devuelve (nombre_limpio, [motivos_de_revision]). Solo reglas inequívocas."""
    motivos, s = [], str(crudo).strip()
    if '*' in s:
        s = re.sub(r'\*\w*', '', s); motivos.append("sufijo '*' eliminado")
    s = s.replace('.', ' ')
    if not s.isupper():
        s = re.sub(r'(?<=[a-záéíóúñ])(?=[A-ZÁÉÍÓÚÑ])', ' ', s)    # 'FelipeTeotlalcingo' -> 'Felipe Teotlalcingo'
    s = re.sub(r'\s+', ' ', s).strip()
    if s.isupper():
        s = ' '.join(w if w in PARTICULAS else w.capitalize() for w in s.title().split())
    for pat, rep in ABREV:
        s = re.sub(pat, rep, s, flags=re.I)
    toks = s.split()
    if toks and toks[0] == 'S':
        motivos.append("abreviatura 'S' ambigua (San/Santa)")
    if len(toks) > 1 and len(toks[-1]) <= 2 and toks[-1].lower() not in {w.lower() for w in PARTICULAS}:
        motivos.append('posible nombre truncado')
    return s, motivos


def preparar_destinos(conteo_viajes: pd.Series, ruta_csv):
    filas = []
    for crudo, n in conteo_viajes.items():
        limpio, motivos = limpiar_destino(crudo)
        estado, conf = '', False
        sug = SUGERENCIAS.get(norm(crudo))
        if sug:
            limpio, estado = sug; motivos = motivos + ['sugerido: confirmar']
        filas.append({'Destino_Crudo': crudo, 'Viajes': int(n), 'Tipo': tipo_destino(crudo),
                      'Destino_Limpio': limpio, 'Estado': estado, 'Confirmado': conf,
                      'Revisar': '; '.join(motivos)})
    nueva = pd.DataFrame(filas)
    vieja = leer_csv_robusto(ruta_csv, keep_default_na=False)
    if vieja is not None:      # conserva lo que ya editaste
        vieja = _alinear_columnas(vieja, ['Destino_Crudo', 'Destino_Limpio', 'Estado', 'Confirmado'])
        _exigir_columnas(vieja, ['Destino_Crudo', 'Destino_Limpio', 'Estado', 'Confirmado'], ruta_csv)
        vieja = vieja.drop_duplicates('Destino_Crudo', keep='last')
        edit = vieja.set_index('Destino_Crudo')[['Destino_Limpio', 'Estado', 'Confirmado']].astype(object)
        edit['Confirmado'] = _es_verdadero(edit['Confirmado'])
        nueva = nueva.set_index('Destino_Crudo').astype({c: object for c in ['Destino_Limpio', 'Estado', 'Confirmado']})
        comunes = nueva.index.intersection(edit.index)
        for c in ['Destino_Limpio', 'Estado', 'Confirmado']:
            nueva.loc[comunes, c] = edit.loc[comunes, c].values
        nueva = nueva.reset_index()
    nueva['Confirmado'] = _es_verdadero(nueva['Confirmado'])
    return nueva.sort_values('Viajes', ascending=False).reset_index(drop=True)


def preparar_plantas(plantas, ruta_csv):
    filas = [{'PLANTA_ORIGEN': p, 'Ciudad': PISTAS_PLANTAS.get(p, ('', ''))[0],
              'Estado': PISTAS_PLANTAS.get(p, ('', ''))[1], 'Confirmado': False} for p in plantas]
    nueva = pd.DataFrame(filas)
    vieja = leer_csv_robusto(ruta_csv, keep_default_na=False)
    if vieja is not None:
        vieja = _alinear_columnas(vieja, ['PLANTA_ORIGEN', 'Ciudad', 'Estado', 'Confirmado'])
        _exigir_columnas(vieja, ['PLANTA_ORIGEN', 'Ciudad', 'Estado', 'Confirmado'], ruta_csv)
        vieja = vieja.drop_duplicates('PLANTA_ORIGEN', keep='last').set_index('PLANTA_ORIGEN').astype(object)
        vieja['Confirmado'] = _es_verdadero(vieja['Confirmado'])
        nueva = nueva.set_index('PLANTA_ORIGEN').astype({c: object for c in ['Ciudad', 'Estado', 'Confirmado']})
        comunes = nueva.index.intersection(vieja.index)
        for c in ['Ciudad', 'Estado', 'Confirmado']:
            nueva.loc[comunes, c] = vieja.loc[comunes, c].values
        nueva = nueva.reset_index()
    nueva['Confirmado'] = _es_verdadero(nueva['Confirmado'])
    return nueva


# ------------------------------------------------------------------ geografía
def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def en_mexico(c):
    return BBOX_MX[0] <= c['lat'] <= BBOX_MX[1] and BBOX_MX[2] <= c['lon'] <= BBOX_MX[3]


def elegir_candidato(cands, estado):
    cands = [c for c in (cands or []) if en_mexico(c)]
    if not cands: return None, 'sin_resultado'
    if estado:
        filt = [c for c in cands if norm(c.get('state') or '') == norm(estado)]
        if not filt: return None, 'estado_no_coincide'
        return filt[0], 'ok'
    ambiguo = len({norm(c.get('state') or '') for c in cands}) > 1
    return cands[0], ('ambiguo' if ambiguo else 'ok')


def geocoder_nominatim(user_agent='ternium_logistics_project', pausa=1.1):
    from geopy.geocoders import Nominatim
    g = Nominatim(user_agent=user_agent, timeout=10)
    def f(consulta):
        for intento in range(3):
            try:
                time.sleep(pausa)
                r = g.geocode(consulta, exactly_one=False, limit=3, addressdetails=True,
                              country_codes='mx', language='es')
                return [{'lat': x.latitude, 'lon': x.longitude, 'state': x.raw.get('address', {}).get('state'),
                         'display': x.address} for x in (r or [])]
            except Exception:
                time.sleep(2 ** intento)
        return None            # fallo de red: NO se cachea
    return f


def router_osrm(base='http://router.project-osrm.org', pausa=0.25):
    import requests
    s = requests.Session()
    def f(lat1, lon1, lat2, lon2):
        url = f'{base}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false'
        for intento in range(3):
            try:
                time.sleep(pausa)
                r = s.get(url, timeout=15)
                if r.status_code == 200:
                    j = r.json()
                    if j.get('code') == 'Ok': return j['routes'][0]['distance'] / 1000
                    if j.get('code') == 'NoRoute': return float('nan')   # definitivo
                elif r.status_code == 400:
                    return float('nan')
            except requests.RequestException:
                pass
            time.sleep(2 ** intento)
        return None            # fallo temporal: NO se cachea
    return f


# ------------------------------------------------------------------ orquestación
def clave(nombre, estado): return f'{norm(nombre)}|{norm(estado or "")}'


def _cargar_cache(path, cols):
    df = leer_csv_robusto(path, keep_default_na=False)
    return df if df is not None else pd.DataFrame(columns=cols)


def construir_catalogo(oro_csv, plantas_csv, destinos_csv, salida, geocoder=None, router=None, solo_tablas=False):
    salida = Path(salida); salida.mkdir(parents=True, exist_ok=True)
    if not Path(oro_csv).exists() or Path(oro_csv).stat().st_size == 0:
        raise FileNotFoundError(f'No existe o está vacío el oro: {oro_csv}. Corre primero etl_oro.py.')
    oro = pd.read_csv(oro_csv, usecols=['PLANTA_ORIGEN', 'Ciudad Destino'])
    rutas = oro.value_counts().rename('Viajes').reset_index().rename(columns={'Ciudad Destino': 'Destino'})
    for p in (plantas_csv, destinos_csv): Path(p).parent.mkdir(parents=True, exist_ok=True)
    destinos = preparar_destinos(oro['Ciudad Destino'].value_counts(), destinos_csv)
    plantas = preparar_plantas(sorted(oro['PLANTA_ORIGEN'].unique()), plantas_csv)
    _respaldar(destinos_csv); _respaldar(plantas_csv)
    _csv(destinos, destinos_csv); _csv(plantas, plantas_csv)
    rep = {'rutas': len(rutas), 'destinos': len(destinos), 'plantas': len(plantas),
           'plantas_sin_ciudad': plantas.loc[plantas.Ciudad == '', 'PLANTA_ORIGEN'].tolist(),
           'destinos_por_tipo': destinos.Tipo.value_counts().to_dict(),
           'viajes_por_tipo_destino': destinos.groupby('Tipo').Viajes.sum().to_dict(),
           'destinos_a_revisar': int((destinos.Revisar != '').sum())}
    if solo_tablas:
        return None, rep

    # ---- 1) geocodificación con caché
    lugares = {}
    for _, r in plantas[plantas.Ciudad != ''].iterrows():
        lugares[clave(r.Ciudad, r.Estado)] = (r.Ciudad, r.Estado)
    d_fin = {}
    for _, r in destinos.iterrows():
        nombre = r.Destino_Limpio if r.Destino_Limpio else r.Destino_Crudo
        d_fin[r.Destino_Crudo] = (nombre, r.Estado)
        if r.Tipo == 'puntual': lugares[clave(nombre, r.Estado)] = (nombre, r.Estado)
    gpath = salida / 'cache_geocodificacion.csv'
    gcache = _cargar_cache(gpath, ['clave', 'consulta', 'lat', 'lon', 'estado_resultado', 'display', 'estatus'])
    hechos = {r.clave: r for r in gcache.itertuples()}
    nuevos, pendientes_red = [], 0
    faltan = sum(1 for k in lugares if k not in hechos)
    print(f'Geocodificación: {len(lugares) - faltan} en caché, {faltan} por consultar', flush=True)
    for k, (nombre, estado) in lugares.items():
        if k in hechos: continue
        consulta = f'{nombre}, {estado}, México' if estado else f'{nombre}, México'
        cands = geocoder(consulta)
        if cands is None: pendientes_red += 1; continue
        c, estatus = elegir_candidato(cands, estado)
        fila = {'clave': k, 'consulta': consulta, 'lat': c['lat'] if c else '', 'lon': c['lon'] if c else '',
                'estado_resultado': (c or {}).get('state') or '', 'display': (c or {}).get('display') or '', 'estatus': estatus}
        nuevos.append(fila); hechos[k] = fila
        if len(nuevos) % 25 == 0:
            _csv(pd.concat([gcache, pd.DataFrame(nuevos)]), gpath)
            print(f'  geocodificados {len(nuevos)}/{faltan}', flush=True)
    if nuevos:
        gcache = pd.concat([gcache, pd.DataFrame(nuevos)], ignore_index=True)
        _csv(gcache, gpath)
    geo = gcache.drop_duplicates('clave', keep='last').set_index('clave')
    def coord(k):
        if k not in geo.index or geo.loc[k, 'estatus'] not in ('ok', 'ambiguo'): return None
        return float(geo.loc[k, 'lat']), float(geo.loc[k, 'lon'])
    rep['geocodificacion'] = geo.estatus.value_counts().to_dict()
    rep['lugares_pendientes_por_red'] = pendientes_red

    # ---- 2) rutas con caché
    rpath = salida / 'cache_rutas.csv'
    rcache = _cargar_cache(rpath, ['o', 'd', 'km'])
    rdict = {(r.o, r.d): (float(r.km) if str(r.km).strip() != '' else float('nan')) for r in rcache.itertuples()}
    pl = plantas.set_index('PLANTA_ORIGEN')
    tipo = destinos.set_index('Destino_Crudo').Tipo
    filas, nuevas_r = [], []
    print(f'Rutas: {len(rutas)} en total, {len(rdict)} ya en caché', flush=True)
    for r in rutas.itertuples():
        fila = {'PLANTA_ORIGEN': r.PLANTA_ORIGEN, 'Ciudad Destino': r.Destino, 'Viajes': r.Viajes,
                'Kilometros_Ruta': np.nan, 'Km_Fuente': '', 'Ratio_Carretera': np.nan, '_hav': np.nan}
        t = tipo[r.Destino]
        if t != 'puntual':
            fila['Km_Fuente'] = t; filas.append(fila); continue
        p = pl.loc[r.PLANTA_ORIGEN]
        co = coord(clave(p.Ciudad, p.Estado)) if p.Ciudad else None
        nombre, estado = d_fin[r.Destino]; cd = coord(clave(nombre, estado))
        if co is None: fila['Km_Fuente'] = 'sin_origen'; filas.append(fila); continue
        if cd is None: fila['Km_Fuente'] = 'sin_geocodificar_destino'; filas.append(fila); continue
        ko, kd = clave(p.Ciudad, p.Estado), clave(nombre, estado)
        hav = haversine_km(*co, *cd); fila['_hav'] = hav
        if (ko, kd) in rdict: km = rdict[(ko, kd)]
        else:
            km = router(*co, *cd)
            if km is not None:
                rdict[(ko, kd)] = km; nuevas_r.append({'o': ko, 'd': kd, 'km': km})
                if len(nuevas_r) % 50 == 0:
                    _csv(pd.concat([rcache, pd.DataFrame(nuevas_r)]), rpath)
                    print(f'  rutas calculadas en esta corrida: {len(nuevas_r)}', flush=True)
        if km is not None and not math.isnan(km):
            fila['Kilometros_Ruta'] = km; fila['Km_Fuente'] = 'osrm'
            fila['Ratio_Carretera'] = km / hav if hav > 1 else np.nan
        else:
            fila['Km_Fuente'] = 'pendiente_estimar'
        filas.append(fila)
    if nuevas_r:
        _csv(pd.concat([rcache, pd.DataFrame(nuevas_r)]), rpath)
    cat = pd.DataFrame(filas)
    # ---- 3) respaldo: línea recta x factor calibrado (marcado como estimado)
    ok = cat.loc[cat.Km_Fuente == 'osrm', 'Ratio_Carretera'].dropna()
    ok = ok[(ok >= 1.0) & (ok <= 3.0)]
    factor = float(ok.median()) if len(ok) >= 30 else FACTOR_DEFAULT
    m = cat.Km_Fuente == 'pendiente_estimar'
    cat.loc[m, 'Kilometros_Ruta'] = cat.loc[m, '_hav'] * factor
    cat.loc[m, 'Km_Fuente'] = 'estimado_haversine'
    cat = cat.drop(columns=['_hav'])
    rep['factor_carretera'] = round(factor, 3); rep['factor_calibrado_con'] = int(len(ok))
    rep['rutas_por_fuente'] = cat.Km_Fuente.value_counts().to_dict()
    rep['viajes_por_fuente'] = cat.groupby('Km_Fuente').Viajes.sum().to_dict()
    rep['rutas_ratio_dudoso(<1 o >2.5)'] = int(((cat.Ratio_Carretera < 1.0) | (cat.Ratio_Carretera > 2.5)).sum())
    cat[['PLANTA_ORIGEN', 'Ciudad Destino', 'Kilometros_Ruta', 'Km_Fuente', 'Ratio_Carretera', 'Viajes']].to_csv(
        salida / 'catalogo_distancias_v2.csv', index=False, encoding='utf-8')
    # ---- 4) lo que hay que revisar a mano
    rev = geo[geo.estatus != 'ok'].reset_index()
    rev.to_csv(salida / 'geocoding_revisar.csv', index=False, encoding='utf-8')
    dud = cat[(cat.Ratio_Carretera < 1.0) | (cat.Ratio_Carretera > 2.5)].sort_values('Viajes', ascending=False)
    dud.to_csv(salida / 'rutas_ratio_dudoso.csv', index=False, encoding='utf-8')
    (salida / 'reporte_distancias.json').write_text(json.dumps(rep, indent=2, ensure_ascii=False, default=str), encoding='utf-8')
    return cat, rep


if __name__ == '__main__':
    os.chdir(Path(__file__).resolve().parent.parent)   # rutas relativas a la raíz del proyecto, se corra desde donde se corra
    ap = argparse.ArgumentParser()
    ap.add_argument('--oro', default='data/oro_v2/viajes_foraneos_oro.csv')
    ap.add_argument('--plantas', default='config/plantas.csv')
    ap.add_argument('--destinos', default='config/destinos_canonicos.csv')
    ap.add_argument('--salida', default='data/distancias_v2')
    ap.add_argument('--solo-tablas', action='store_true')
    a = ap.parse_args()
    g, r = (None, None) if a.solo_tablas else (geocoder_nominatim(), router_osrm())
    _, rep = construir_catalogo(a.oro, a.plantas, a.destinos, a.salida, g, r, a.solo_tablas)
    print(json.dumps(rep, indent=2, ensure_ascii=False, default=str))
