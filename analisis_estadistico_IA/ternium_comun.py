"""Definiciones compartidas por los componentes del reto Ternium (universo, estilo de figuras, bootstrap).

Replica las decisiones del Componente 1 (secciones 1, 2 y 4.2 de componente_1.ipynb) para que el
Componente 2 trabaje exactamente sobre el mismo universo. Si se cambia algo aquí, cambiarlo también allá.
"""
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

# ---------------------------------------------------------------- datos y universo
ORO = Path('data/oro_v2/viajes_foraneos_oro.csv')
VENTANA = ('2026-01-01', '2026-09-01')          # [inicio, fin): ene–ago 2026
FAM = 'FAMILIA_CAMION_DESC'
GRUPO, PLANTA = 'GRUPO_PLANTA_ORIGEN', 'PLANTA_ORIGEN'
UNIDADES = ['Torton', '2 Ejes', 'Caja Seca 2 Ejes', '3 Ejes', 'Big Coil', 'Full']
MAPA_UNIDAD = {
    'TORTON': 'Torton',
    'CAJA SECA 2 EJES NEUMATICA': 'Caja Seca 2 Ejes',
    'PLATAFORMA 2 EJES NEUMATICA': '2 Ejes',
    'PLATAFORMA 2 EJES MUELLES': '2 Ejes',
    'PLATAFORMA 2 EJES NEUMATICA DESACOPLADA': '2 Ejes',
    'PLATAFORMA 3 EJES NEUMATICA': '3 Ejes',
    'PLATAFORMA 3 EJES MUELLES': '3 Ejes',
    'PLATAFORMA 3 EJES NEUMATICA CORTA': '3 Ejes',
    'PLATAFORMA 3 EJES NEUMATICA CORTA LIGERA': '3 Ejes',
    'PLATAFORMA 3 EJES NEUMATICA ULTRA LIGERA': '3 Ejes',
    'PLATAFORMA 3 EJES NEUMATICA BIG COIL': 'Big Coil',
    'FULL NEUMATICA': 'Full',
}


def cargar_universo(ruta=ORO):
    """Viajes de la ventana con unidad dentro del universo del Componente 1 (58,275 viajes)."""
    d = pd.read_csv(ruta, low_memory=False, parse_dates=['FECHA_EGRESO', 'FECHA_VIAJE_FINALIZADO'])
    d = d[(d['FECHA_EGRESO'] >= VENTANA[0]) & (d['FECHA_EGRESO'] < VENTANA[1])].copy()
    d['Unidad'] = d[FAM].map(MAPA_UNIDAD)
    d = d[d['Unidad'].notna()].copy()
    d['Unidad'] = pd.Categorical(d['Unidad'], UNIDADES, ordered=True)
    d['Costo'] = d['Monto total']
    return d


# ---------------------------------------------------------------- estilo de figuras
SUPERFICIE, TINTA, TINTA_2, TINTA_3, REJILLA = '#fcfcfb', '#0b0b0b', '#52514e', '#8a8984', '#e4e3df'
COLOR_UNIDAD = {'Torton': '#2a78d6', '2 Ejes': '#eb6834', 'Caja Seca 2 Ejes': '#1baf7a',
                '3 Ejes': '#eda100', 'Big Coil': '#e87ba4', 'Full': '#008300'}
SECUENCIAL = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b']


def aplicar_estilo():
    plt.rcParams.update({
        'figure.facecolor': SUPERFICIE, 'axes.facecolor': SUPERFICIE, 'savefig.facecolor': SUPERFICIE,
        'axes.edgecolor': REJILLA, 'axes.labelcolor': TINTA_2, 'axes.titlecolor': TINTA,
        'axes.spines.top': False, 'axes.spines.right': False,
        'axes.grid': True, 'grid.color': REJILLA, 'grid.linewidth': 0.8,
        'xtick.color': TINTA_2, 'ytick.color': TINTA_2, 'text.color': TINTA,
        'font.size': 10.5, 'axes.titlesize': 12, 'axes.titleweight': 'bold', 'axes.titlelocation': 'center',
        'legend.frameon': False, 'figure.dpi': 110,
    })


def titulo(fig, texto, subtitulo=None):
    """Título centrado y subtítulo corto; acomoda la figura debajo (llamar al final)."""
    h = fig.get_figheight()
    fig.suptitle(texto, x=0.5, y=1 - 0.12 / h, va='top', ha='center', fontweight='bold', fontsize=13.5)
    if subtitulo:
        fig.text(0.5, 1 - 0.45 / h, subtitulo, ha='center', va='top', color=TINTA_2, fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 1 - (0.8 if subtitulo else 0.5) / h))


def leyenda_unidades(ax, unidades, **kw):
    ax.legend(handles=[Patch(color=COLOR_UNIDAD[u], label=u) for u in unidades], **kw)


# ---------------------------------------------------------------- bootstrap de dos vías
CONGLOMERADOS = ['Transportista', 'Ruta_ID']   # pigeonhole bootstrap (Owen, 2007)


def bootstrap_conglomerados(data, celda, sumas, razones, conglomerados=None, B=2000, semilla=2026, bloque=250):
    """IC 95 % (percentil) de razones Σnum/Σden por celda, remuestreando conglomerados completos.

    sumas: {nombre: columna a sumar}; razones: {nombre: (num, den)}; 'n' = número de viajes.
    Con varios conglomerados, cada factor se remuestrea por separado y el peso del viaje es el producto.
    """
    conglomerados = CONGLOMERADOS if conglomerados is None else conglomerados
    agg = (data.assign(_n=1)
               .groupby(conglomerados + celda, observed=True)
               .agg(**{k: (v, 'sum') for k, v in sumas.items()}, n=('_n', 'sum')).reset_index())
    cel_codes, cel_uniq = pd.factorize(agg[celda].apply(tuple, axis=1))
    G, K = len(agg), len(cel_uniq)
    A = {}
    for v in list(sumas) + ['n']:
        A[v] = np.zeros((G, K)); A[v][np.arange(G), cel_codes] = agg[v].values
    codigos = [pd.factorize(agg[k])[0] for k in conglomerados]
    rng = np.random.default_rng(semilla)
    S = {v: np.empty((B, K)) for v in A}
    for i in range(0, B, bloque):
        b = min(bloque, B - i)
        w = np.ones((b, G))
        for cod in codigos:
            m = cod.max() + 1
            w *= rng.multinomial(m, np.full(m, 1 / m), size=b)[:, cod]
        for v in A:
            S[v][i:i + b] = w @ A[v]
    idx = (pd.MultiIndex.from_tuples(cel_uniq, names=celda) if len(celda) > 1
           else pd.Index([c[0] for c in cel_uniq], name=celda[0]))
    res = pd.DataFrame(index=idx)
    res['Viajes'] = A['n'].sum(0).astype(int)
    for k in sumas:
        res[k] = A[k].sum(0)
    with np.errstate(invalid='ignore', divide='ignore'):
        for r, (num, den) in razones.items():
            res[r] = A[num].sum(0) / A[den].sum(0)
            res[f'{r}_inf'], res[f'{r}_sup'] = np.nanpercentile(S[num] / S[den], [2.5, 97.5], axis=0)
    return res


# ---------------------------------------------------------------- capacidades (Componente 1, sección 4.1)
# Carga útil legal = PBV NOM-012-SCT-2 (camino ET y A) − tara por unidad (supuesto provisional dentro de 14–17 t).
# Torton: sin tara confirmada → capacidad = techo operativo (P99 observado).
PBV_T = {'Torton': 27.5, '2 Ejes': 46.5, 'Caja Seca 2 Ejes': 46.5, '3 Ejes': 54.0, 'Big Coil': 54.0, 'Full': 66.5}
TARA_T = {'2 Ejes': 14.5, 'Caja Seca 2 Ejes': 16.0, '3 Ejes': 15.5, 'Big Coil': 16.5, 'Full': 15.5, 'Torton': np.nan}


def capacidades(d):
    """Tabla por unidad: carga útil legal, techo operativo (P99 del peso real) y capacidad para decidir = mínimo de ambas."""
    cap = pd.DataFrame({'PBV_t': pd.Series(PBV_T), 'Tara_t': pd.Series(TARA_T)}).reindex(UNIDADES)
    cap['Techo_P99_t'] = d.groupby(d['Unidad'].astype(str))['Toneladas_Reales'].quantile(.99).reindex(UNIDADES)
    cap['Cap_legal_t'] = (cap['PBV_t'] - cap['Tara_t']).fillna(cap['Techo_P99_t'])
    cap['Cap_decision_t'] = cap[['Cap_legal_t', 'Techo_P99_t']].min(axis=1)
    return cap
