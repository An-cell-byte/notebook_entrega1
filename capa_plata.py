"""Capa de plata: une las 3 tablas por ID de viaje y conserva solo las columnas de interés.

Se usa un inner join, así que solo quedan los viajes que aparecen en las 3 tablas
(Detalles viajes foráneos, Tiempos Viajes Foráneos y Viajes con Costos V2).
"""
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
SALIDA = DATA / "plata" / "viajes_foraneos_plata.csv"


def leer(nombre):
    return pd.read_csv(DATA / nombre, sep=";", encoding="utf-8-sig", dtype=str)


def numero_es(s):
    """Convierte '30.470,000' -> 30470.0 (punto = miles, coma = decimal)."""
    return pd.to_numeric(s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))


def una_fila_por_viaje(df, nombre):
    antes = len(df)
    df = df.drop_duplicates().drop_duplicates(subset="ID_VIAJE", keep="first")
    print(f"{nombre:<10} {antes:>8,} filas -> {len(df):>8,} viajes únicos")
    return df


# Detalles viajes foraneos ultimo año (ya limpia con limpieza_viajes_foraneos.py)
det = leer("Detalles viajes foraneos ultimo año.csv")
det = det[["Planta", "ID_VIAJE", "Ciudad Destino", "ID Camión", "Tipo Camión", "Programado (Peso)"]]
det = una_fila_por_viaje(det, "Detalles")

# Tiempos Viajes Foraneos (una fila por parada; se deja una por viaje)
tie = leer("Tiempos Viajes Foraneos.csv")
tie = tie[["GRUPO_PLANTA_ORIGEN", "COD_PLANTA_ORIGEN", "PLANTA_ORIGEN", "ID_VIAJE", "FECHA_EGRESO", "FAMILIA_CAMION_DESC", "FECHA_VIAJE_FINALIZADO"]]
tie = una_fila_por_viaje(tie, "Tiempos")

# Viajes con Costos V2
cos = leer("Viajes con Costos V2.csv")
cos = cos[["ID_VIAJE", "Planta Origen", "Nombre", "Desc TpoTrn", "Peso Total", "Monto total"]]
cos = cos.rename(columns={"Nombre": "Transportista"})
cos = una_fila_por_viaje(cos, "Costos")

plata = (det.merge(tie, on="ID_VIAJE", how="inner")
            .merge(cos, on="ID_VIAJE", how="inner"))

# Tipos de dato
plata["ID_VIAJE"] = plata["ID_VIAJE"].astype("int64")
plata["ID Camión"] = plata["ID Camión"].astype("int64")
plata["Programado (Peso)"] = pd.to_numeric(plata["Programado (Peso)"])   # toneladas
plata["Peso Total"] = numero_es(plata["Peso Total"])                      # kilogramos
plata["Monto total"] = numero_es(plata["Monto total"])                    # MXN
for c in ["FECHA_EGRESO", "FECHA_VIAJE_FINALIZADO"]:
    plata[c] = pd.to_datetime(plata[c], format="%d/%m/%Y %H:%M:%S")

plata = plata.sort_values("ID_VIAJE").reset_index(drop=True)
SALIDA.parent.mkdir(exist_ok=True)
plata.to_csv(SALIDA, sep=";", index=False, encoding="utf-8-sig")

print(f"\nCapa de plata: {len(plata):,} viajes x {plata.shape[1]} columnas")
print(f"ID_VIAJE único: {plata['ID_VIAJE'].is_unique}")
print("Nulos por columna:", plata.isna().sum()[lambda s: s > 0].to_dict() or "ninguno")
print(f"Guardado en: {SALIDA}")
