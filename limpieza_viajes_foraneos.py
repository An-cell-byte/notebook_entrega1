"""Limpia 'Detalles viajes foraneos ultimo año.xlsx' y guarda un CSV limpio en data/."""
from pathlib import Path
import pandas as pd

DATA = Path(__file__).resolve().parent / "data"
ENTRADA = DATA / "Detalles viajes foraneos ultimo año.xlsx"
SALIDA = DATA / "Detalles viajes foraneos ultimo año.csv"

df = pd.read_excel(ENTRADA)
n0 = len(df)

# 1. Filas basura del final: "Total", fila vacía y texto de filtros (no tienen ID Viaje).
df = df[df["ID Viaje"].notna()].copy()
n1 = len(df)

# 2. Categoría Extranjero/Texas (antes de borrar Ciudad/Zona, que es de donde se detecta).
df["Estado Destino"] = df["Estado Destino"].astype("string").str.strip().replace({"": pd.NA})
es_texas = (df["Descripción Zona"].astype("string").str.upper().eq("TEXAS")
            | df["Ciudad Destino"].astype("string").str.contains(r"Texas|, TX\b", case=False, regex=True))
df.loc[es_texas.fillna(False), "Estado Destino"] = "Extranjero/Texas"

# 3. Pesos imposibles: cero, negativos o mayores a 80 toneladas.
peso = df["Programado (Peso)"]
df = df[(peso > 0) & (peso <= 80)]
n3 = len(df)

# 4. Viajes repetidos: una fila por ID Viaje (se conserva la primera aparición).
df = df.drop_duplicates(subset="ID Viaje", keep="first")
n4 = len(df)

# 5. Columnas que sobran.
df = df.drop(columns=["Ciudad Destino", "Descripción Zona", "Cant. Ciclos", "Sociedad", "Motivo"])
for c in ["ID Viaje", "ID Camión", "Año", "Día"]:
    df[c] = df[c].astype("int64")

df.to_csv(SALIDA, sep=";", index=False, encoding="utf-8-sig")

print(f"Filas originales:            {n0:,}")
print(f"Filas basura quitadas:       {n0 - n1:,}")
print(f"Pesos imposibles quitados:   {n1 - n3:,}")
print(f"Viajes repetidos quitados:   {n3 - n4:,}")
print(f"Filas finales (viajes):      {n4:,}")
print(f"Extranjero/Texas:            {(df['Estado Destino'] == 'Extranjero/Texas').sum():,}")
print(f"Estado Destino aún vacío:    {df['Estado Destino'].isna().sum():,}")
print(f"Columnas: {list(df.columns)}")
print(f"Guardado en: {SALIDA}")
