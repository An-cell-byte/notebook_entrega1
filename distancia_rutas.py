import pandas as pd
import requests
import time
from pathlib import Path
from geopy.geocoders import Nominatim
from geopy.exc import GeocoderTimedOut

def obtener_coordenadas(ubicaciones):
    """
    Toma una lista de ciudades y devuelve un diccionario con sus coordenadas.
    Incluye un retraso (sleep) obligatorio de 1 segundo para respetar 
    las políticas de uso de la API pública de Nominatim.
    """
    geolocator = Nominatim(user_agent="ternium_logistics_project")
    diccionario_coords = {}
    
    print(f"Geocodificando {len(ubicaciones)} ubicaciones únicas...")
    for ciudad in ubicaciones:
        # Añadimos 'México' para dar contexto al motor de búsqueda
        busqueda = f"{ciudad}, México" 
        try:
            location = geolocator.geocode(busqueda, timeout=10)
            if location:
                diccionario_coords[ciudad] = (location.latitude, location.longitude)
            else:
                diccionario_coords[ciudad] = (None, None)
            
            # Pausa estricta para evitar bloqueos del servidor (Rate Limiting)
            time.sleep(1) 
            
        except GeocoderTimedOut:
            diccionario_coords[ciudad] = (None, None)
            time.sleep(2)
            
    return diccionario_coords

def calcular_distancia_osrm(coord_origen, coord_destino):
    """
    Consulta la API de Open Source Routing Machine (OSRM) para obtener
    la distancia de conducción real en kilómetros.
    """
    if None in coord_origen or None in coord_destino:
        return None
        
    # OSRM espera el formato: longitud,latitud
    lon1, lat1 = coord_origen[1], coord_origen[0]
    lon2, lat2 = coord_destino[1], coord_destino[0]
    
    url = f"http://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
    
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            if data['code'] == 'Ok':
                # OSRM devuelve la distancia en metros, la pasamos a km
                return data['routes'][0]['distance'] / 1000
    except requests.exceptions.RequestException:
        pass
    
    return None

def generar_matriz_distancias(ruta_archivo):
    """
    Función orquestadora: lee la capa de plata, extrae ubicaciones,
    obtiene distancias y exporta el catálogo.
    """
    df = pd.read_csv(ruta_archivo, sep=';')
    
    # 1. Extraer catálogo único para no saturar la API
    rutas = df[['PLANTA_ORIGEN', 'Ciudad Destino']].drop_duplicates().dropna()
    
    # Extraer lista maestra de lugares para geocodificar solo una vez cada ciudad
    lugares_unicos = set(rutas['PLANTA_ORIGEN']).union(set(rutas['Ciudad Destino']))
    coords_dict = obtener_coordenadas(lugares_unicos)
    
    # 2. Calcular distancia para cada par origen-destino
    print("\nCalculando distancias de conducción vía OSRM...")
    distancias = []
    
    for _, row in rutas.iterrows():
        origen = row['PLANTA_ORIGEN']
        destino = row['Ciudad Destino']
        
        c_origen = coords_dict.get(origen, (None, None))
        c_destino = coords_dict.get(destino, (None, None))
        
        km = calcular_distancia_osrm(c_origen, c_destino)
        
        distancias.append({
            'PLANTA_ORIGEN': origen,
            'Ciudad Destino': destino,
            'Kilometros_Ruta': km
        })
        # Pequeña pausa para no saturar OSRM
        time.sleep(0.1) 
        
    # 3. Guardar el catálogo resultante
    df_distancias = pd.DataFrame(distancias)
    #df_distancias.to_csv('catalogo_distancias.csv', index=False)
    print("\nCatálogo guardado exitosamente como 'catalogo_distancias.csv'")
    
    return df_distancias

if __name__ == '__main__':
    
    DS_FILE_ADRESS = Path()
    DATA_ADRESS = DS_FILE_ADRESS/'data'/'plata'/'viajes_foraneos_plata.csv'
        
    # Al ejecutar esto en tu terminal, tomará unos 10-15 minutos debido a las pausas de Rate Limiting
    df_rutas = generar_matriz_distancias(DATA_ADRESS)
    print(df_rutas.head(10))