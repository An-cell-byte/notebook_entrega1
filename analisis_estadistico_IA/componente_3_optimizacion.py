"""Optimizador de right-sizing compartido por los Componentes 3 y 4, alineado con los Componentes 1 y 2.

Contiene:
  * El optimizador de la sección 6 de componente_2.ipynb (tarifas de referencia, factibilidad y MILP por semana con
    disponibilidad de flota). Es una copia: si cambian las reglas allá, hay que cambiarlas aquí.
  * La regla de decisión del Componente 1 (sección 6.1): con el peso real y sin límite de flota.
  * El ahorro por viaje y la clasificación por respaldo causal del Componente 2 (secciones 3–4).
  * Los pesos de bootstrap de dos vías y las tarifas recalculadas con el método del Componente 1 (sección 6.2).

Uso: llamar `preparar_optimizador(df)` una vez con el universo de `ternium_comun.cargar_universo()` (con la columna
'Programado_t') y después usar las demás funciones. El estado se guarda en variables globales del módulo.
"""
import numpy as np
import pandas as pd
from ternium_comun import UNIDADES, PLANTA, CONGLOMERADOS
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy import sparse
from ternium_comun import capacidades

# Movimientos (unidad actual, unidad nueva) cuyo efecto sobre el costo sostiene el Componente 2 (secciones 3–4):
# robustos a confusores omitidos, a la replicación temporal y al placebo. Los demás no se distinguen del ruido
# o de un efecto del transportista (Torton → 2 ejes, 2 ejes → 3 ejes, Big Coil → 3 ejes, 3 ejes → Full).
RESPALDO_CAUSAL = {('3 Ejes', '2 Ejes'), ('Big Coil', '2 Ejes')}


def preparar_optimizador(df):
    """Prepara el estado del optimizador para el universo `df` (capacidades, tarifas por ruta × unidad y flota).

    Guarda todo en variables globales del módulo para que `tarifas`, `factibles` y `resolver` las usen
    igual que en la sección 6 de componente_2.ipynb. Hay que llamarla una vez antes de las demás funciones.
    """
    global cap, CAP_DEC, CAP_LEG, K, DELTA, PERMITIDO, o, rutas_o, cel, cid, con_cel, orden, pos_cel, costo_ord, cid_ord, ini, fin, cel_r, cel_k, semanal, F_max
    global T_OBS, COD_CONGLOMERADOS, PARES_RESPALDO
    cap = capacidades(df)
    CAP_DEC = cap['Cap_decision_t'].reindex(UNIDADES).values     # para decidir: mín(carga útil legal, techo P99)
    CAP_LEG = cap['Cap_legal_t'].reindex(UNIDADES).values        # para medir utilización: carga útil legal
    K = len(UNIDADES)
    DELTA = 0.03                                 # solo se cambia de unidad si ahorra ≥ 3 % (ruido de la tarifa)
    # PERMITIDO[a, b]: la carga de la unidad a puede pasar a b (la caja seca, cerrada, no pasa a plataforma abierta)
    PERMITIDO = np.array([[not (a == 'Caja Seca 2 Ejes' and b != a) for b in UNIDADES] for a in UNIDADES])

    # Índices por viaje: unidad actual (k0), semana, ruta (r) y peso programado (q)
    o = df.copy()
    o['k0'] = o['Unidad'].cat.codes.values
    o['Semana'] = o['FECHA_EGRESO'].dt.to_period('W').astype(str)
    rutas_o = pd.Index(o['Ruta_ID'].unique()); o['r'] = rutas_o.get_indexer(o['Ruta_ID'])
    o['q'] = o['Programado_t']

    # Tarifa de referencia: mediana ponderada por (ruta, unidad) con ≥ 5 viajes. Los costos se ordenan una sola vez
    # dentro de cada celda (cid) para poder recalcular la mediana con cualquier vector de pesos (bootstrap).
    cel = o.groupby(['r', 'k0']).size(); cel = cel[cel >= 5].index
    cid = pd.Series(np.arange(len(cel)), index=cel)
    o['cid'] = pd.MultiIndex.from_arrays([o['r'], o['k0']]).map(cid)
    con_cel = o['cid'].notna().values
    orden = np.lexsort((o['Costo'].values[con_cel], o['cid'].values[con_cel]))
    pos_cel = np.flatnonzero(con_cel)[orden]                      # posición de cada viaje ordenado dentro de `o`
    costo_ord, cid_ord = o['Costo'].values[pos_cel], o['cid'].values[pos_cel].astype(int)
    ini = np.searchsorted(cid_ord, np.arange(len(cel)), 'left'); fin = np.searchsorted(cid_ord, np.arange(len(cel)), 'right')
    cel_r, cel_k = cel.get_level_values(0).values, cel.get_level_values(1).values
    # Disponibilidad de flota: máximo de viajes semanales de cada unidad observado en cada planta
    semanal = o.groupby([PLANTA, 'Semana', 'k0']).size()
    F_max = semanal.groupby(level=[0, 2]).max()

    # Tarifas observadas, códigos de conglomerados para el bootstrap y pares con respaldo causal (en índices)
    T_OBS = tarifas()
    COD_CONGLOMERADOS = [pd.factorize(o[c])[0] for c in CONGLOMERADOS]
    PARES_RESPALDO = {(UNIDADES.index(a), UNIDADES.index(b)) for a, b in RESPALDO_CAUSAL}


def tarifas(w=None):
    """Matriz rutas × unidades con la mediana (ponderada por `w`) del costo por viaje; NaN si no hay tarifa."""
    w = np.ones(len(o)) if w is None else w
    cum = np.concatenate([[0.0], np.cumsum(w[pos_cel])])          # peso acumulado de los costos ordenados
    tot = cum[fin] - cum[ini]                                     # peso total de cada celda
    # Primer costo de cada celda cuyo peso acumulado alcanza la mitad del total (mediana ponderada)
    j = np.clip(np.searchsorted(cum, cum[ini] + tot / 2, 'left') - 1, ini, np.maximum(fin - 1, ini))
    T = np.full((len(rutas_o), K), np.nan)
    T[cel_r, cel_k] = np.where(tot > 0, costo_ord[j], np.nan)     # celda sin peso en la réplica: sin tarifa
    return T


def factibles(T, delta=0.03, cap_dec=None):
    """Matriz viajes × unidades: costo si la asignación es factible, NaN si no.

    Factible = la unidad tiene tarifa en la ruta, el peso programado cabe, la carga puede pasar a esa unidad
    (caja seca) y la tarifa es al menos `delta` más barata que la de la unidad actual.
    """
    if cap_dec is None: cap_dec = CAP_DEC
    Tr = T[o['r'].values]                                         # tarifa de cada unidad en la ruta de cada viaje
    k0 = o['k0'].values
    t0 = Tr[np.arange(len(o)), k0]                                # tarifa de la unidad actual
    ok = ~np.isnan(Tr) & (o['q'].values[:, None] <= cap_dec[None, :]) & PERMITIDO[k0] & (Tr <= (1 - delta) * t0[:, None])
    ok[np.arange(len(o)), k0] = True                             # la unidad actual siempre es factible
    C = np.where(ok, Tr, np.nan)
    C[np.arange(len(o)), k0] = np.where(np.isnan(t0), 0.0, t0)   # sin tarifa propia: el viaje se queda donde está
    sin_tarifa = np.isnan(t0)
    C[sin_tarifa] = np.nan; C[sin_tarifa, k0[sin_tarifa]] = 0.0
    return C, t0


def resolver(T, con_flota=True, F=None, delta=0.03, cap_dec=None):
    """Devuelve la unidad asignada a cada viaje (MILP del Componente 2, sección 6).

    Sin flota: el mínimo por viaje (desempate: menor capacidad). Con flota: un programa entero por semana que
    respeta, por planta × unidad, la disponibilidad `F` (por omisión, el máximo semanal observado).
    """
    if cap_dec is None: cap_dec = CAP_DEC
    C, t0 = factibles(T, delta, cap_dec)
    clave = np.where(np.isnan(C), np.inf, C + 1e-6 * CAP_LEG[None, :])
    k_sol = clave.argmin(1)                                       # solución sin restricción de flota
    if not con_flota:
        return k_sol, C
    F = F_max if F is None else F
    k0 = o['k0'].values
    for sem, ix in o.groupby('Semana').indices.items():
        sub = C[ix]
        movibles = (~np.isnan(sub)).sum(1) > 1                    # viajes con más de una opción esta semana
        if not movibles.any():
            continue
        # ¿la solución sin flota ya respeta la disponibilidad? entonces es óptima
        pl_sem = o[PLANTA].values[ix]
        uso = pd.Series(1, index=pd.MultiIndex.from_arrays([pl_sem, k_sol[ix]])).groupby(level=[0, 1]).sum()
        lim = F.reindex(uso.index)
        usado_sem = pd.Series(1, index=pd.MultiIndex.from_arrays([pl_sem, k0[ix]])).groupby(level=[0, 1]).sum()
        lim = np.maximum(lim.fillna(0), usado_sem.reindex(uso.index).fillna(0))   # nunca menos de lo ya usado
        if (uso <= lim).all():
            continue
        # Programa entero de la semana: una variable por cada par (viaje, unidad) factible
        ii, kk = np.nonzero(~np.isnan(sub))
        c = sub[ii, kk]
        n_v = len(ii)
        A_eq = sparse.csr_matrix((np.ones(n_v), (ii, np.arange(n_v))), shape=(len(ix), n_v))
        # Un "cupo" por planta × unidad; su límite es la flota disponible (o lo ya usado esa semana, si es mayor)
        slot = pd.factorize(pd.Series(pl_sem[ii]).astype(str) + '|' + pd.Series(kk).astype(str))
        s_codes, s_uniq = slot
        cap_s = []
        for sname in s_uniq:
            p_, k_ = sname.rsplit('|', 1); k_ = int(k_)
            f = F.get((p_, k_), 0)
            ya = ((pl_sem == p_) & (k0[ix] == k_)).sum()
            cap_s.append(max(f, ya))
        A_in = sparse.csr_matrix((np.ones(n_v), (s_codes, np.arange(n_v))), shape=(len(s_uniq), n_v))
        # Cada viaje en exactamente una unidad; por planta × unidad, no más que la flota disponible
        r = milp(c, constraints=[LinearConstraint(A_eq, 1, 1), LinearConstraint(A_in, 0, np.array(cap_s))],
                 integrality=np.ones(n_v), bounds=Bounds(0, 1))
        if not r.success or r.x is None:
            raise RuntimeError(f"MILP no resuelto: {r.message}")
        x = np.round(r.x).astype(bool)
        k_sol[ix[ii[x]]] = kk[x]
    return k_sol, C


# ---------------------------------------------------------------- alineación con los Componentes 1 y 2

def decidir_c1(T, q_real, cap_dec=None, delta=None):
    """Regla de right-sizing del Componente 1 (sección 6.1): unidad asignada a cada viaje.

    Con el peso real `q_real` (t) y sin límite de flota: la unidad factible más barata de la ruta (desempate: menor
    capacidad); solo se mueve si ahorra al menos `delta` frente a la unidad actual. Reproduce los 5,784 viajes y
    38.5 M MXN de C1. A diferencia de `resolver`, usa el peso real, que solo se conoce después de cargar.
    """
    cap_dec = CAP_DEC if cap_dec is None else cap_dec
    delta = DELTA if delta is None else delta
    k0, n = o['k0'].values, len(o)
    Tr = T[o['r'].values]                                         # viajes × unidades
    fact = ~np.isnan(Tr) & (q_real[:, None] <= cap_dec[None, :]) & PERMITIDO[k0]
    t_act = Tr[np.arange(n), k0]
    k_best = np.where(fact, Tr + 1e-6 * cap_dec[None, :], np.inf).argmin(1)
    t_best = Tr[np.arange(n), k_best]
    mueve = ~np.isnan(t_act) & fact.any(1) & (k_best != k0) & (t_best <= (1 - delta) * t_act)
    return np.where(mueve, k_best, k0)


def ahorro(k, T=None):
    """Ahorro por viaje (MXN) de asignar la unidad `k`: tarifa de la unidad actual − tarifa de la nueva, misma ruta.

    Por omisión usa las tarifas observadas; con `T` de una réplica evalúa los mismos movimientos con otras tarifas.
    """
    T = T_OBS if T is None else T
    k0, r = o['k0'].values, o['r'].values
    m = k != k0
    a = np.zeros(len(o))
    a[m] = T[r[m], k0[m]] - T[r[m], k[m]]
    return a


def con_respaldo(k):
    """True en los viajes cuyo cambio de unidad tiene respaldo causal en el Componente 2 (ver RESPALDO_CAUSAL)."""
    k0 = o['k0'].values
    return np.array([(a, b) in PARES_RESPALDO for a, b in zip(k0, k)]) & (k != k0)


def pesos_dos_vias(rng, n):
    """`n` réplicas de pesos por viaje del bootstrap de dos vías transportista × ruta (matriz n × viajes).

    Se remuestrean transportistas y rutas por separado, con reemplazo; el peso de un viaje es (veces que salió su
    transportista) × (veces que salió su ruta). Mismo generador que el Componente 1 (sección 6.2): con la misma
    semilla y bloques de 100 réplicas se obtienen exactamente sus intervalos.
    """
    w = np.ones((n, len(o)))
    for cod in COD_CONGLOMERADOS:
        m = cod.max() + 1
        w *= rng.multinomial(m, np.full(m, 1 / m), size=n)[:, cod]
    return w


def tarifas_bootstrap(w):
    """Tarifas de referencia recalculadas con los pesos `w` de una réplica (método del Componente 1, sección 6.2).

    Si una celda ruta × unidad queda sin viajes en la réplica, conserva su tarifa observada.
    """
    T = tarifas(w)
    return np.where(np.isnan(T), T_OBS, T)
