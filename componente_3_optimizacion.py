"""Optimizador de la sección 6 del Componente 2, conservado para reproducibilidad."""
import numpy as np
import pandas as pd
from ternium_comun import UNIDADES, PLANTA
from scipy.optimize import milp, LinearConstraint, Bounds
from scipy import sparse
from ternium_comun import capacidades

def preparar_optimizador(df):
    global cap, CAP_DEC, CAP_LEG, K, DELTA, PERMITIDO, o, rutas_o, cel, cid, con_cel, orden, pos_cel, costo_ord, cid_ord, ini, fin, cel_r, cel_k, semanal, F_max
    cap = capacidades(df)
    CAP_DEC = cap['Cap_decision_t'].reindex(UNIDADES).values
    CAP_LEG = cap['Cap_legal_t'].reindex(UNIDADES).values
    K = len(UNIDADES)
    DELTA = 0.03
    PERMITIDO = np.array([[not (a == 'Caja Seca 2 Ejes' and b != a) for b in UNIDADES] for a in UNIDADES])
    
    o = df.copy()
    o['k0'] = o['Unidad'].cat.codes.values
    o['Semana'] = o['FECHA_EGRESO'].dt.to_period('W').astype(str)
    rutas_o = pd.Index(o['Ruta_ID'].unique()); o['r'] = rutas_o.get_indexer(o['Ruta_ID'])
    o['q'] = o['Programado_t']
    
    # Tarifa de referencia: mediana ponderada por (ruta, unidad); se reusa con pesos de bootstrap
    cel = o.groupby(['r', 'k0']).size(); cel = cel[cel >= 5].index
    cid = pd.Series(np.arange(len(cel)), index=cel)
    o['cid'] = pd.MultiIndex.from_arrays([o['r'], o['k0']]).map(cid)
    con_cel = o['cid'].notna().values
    orden = np.lexsort((o['Costo'].values[con_cel], o['cid'].values[con_cel]))
    pos_cel = np.flatnonzero(con_cel)[orden]
    costo_ord, cid_ord = o['Costo'].values[pos_cel], o['cid'].values[pos_cel].astype(int)
    ini = np.searchsorted(cid_ord, np.arange(len(cel)), 'left'); fin = np.searchsorted(cid_ord, np.arange(len(cel)), 'right')
    cel_r, cel_k = cel.get_level_values(0).values, cel.get_level_values(1).values
    semanal = o.groupby([PLANTA, 'Semana', 'k0']).size()
    F_max = semanal.groupby(level=[0, 2]).max()
    

def tarifas(w=None):
    w = np.ones(len(o)) if w is None else w
    cum = np.concatenate([[0.0], np.cumsum(w[pos_cel])])
    tot = cum[fin] - cum[ini]
    j = np.clip(np.searchsorted(cum, cum[ini] + tot / 2, 'left') - 1, ini, np.maximum(fin - 1, ini))
    T = np.full((len(rutas_o), K), np.nan)
    T[cel_r, cel_k] = np.where(tot > 0, costo_ord[j], np.nan)
    return T

def factibles(T, delta=0.03, cap_dec=None):
    """Matriz viajes × unidades: costo si la asignación es factible, NaN si no."""
    if cap_dec is None: cap_dec = CAP_DEC
    Tr = T[o['r'].values]
    k0 = o['k0'].values
    t0 = Tr[np.arange(len(o)), k0]
    ok = ~np.isnan(Tr) & (o['q'].values[:, None] <= cap_dec[None, :]) & PERMITIDO[k0] & (Tr <= (1 - delta) * t0[:, None])
    ok[np.arange(len(o)), k0] = True                             # la unidad actual siempre es factible
    C = np.where(ok, Tr, np.nan)
    C[np.arange(len(o)), k0] = np.where(np.isnan(t0), 0.0, t0)   # sin tarifa propia: el viaje se queda donde está
    sin_tarifa = np.isnan(t0)
    C[sin_tarifa] = np.nan; C[sin_tarifa, k0[sin_tarifa]] = 0.0
    return C, t0

def resolver(T, con_flota=True, F=None, delta=0.03, cap_dec=None):
    """Devuelve la unidad asignada a cada viaje. Sin flota: el mínimo por viaje (desempate: menor capacidad).
    Con flota: un programa entero por semana."""
    if cap_dec is None: cap_dec = CAP_DEC
    C, t0 = factibles(T, delta, cap_dec)
    clave = np.where(np.isnan(C), np.inf, C + 1e-6 * CAP_LEG[None, :])
    k_sol = clave.argmin(1)
    if not con_flota:
        return k_sol, C
    F = F_max if F is None else F
    k0 = o['k0'].values
    for sem, ix in o.groupby('Semana').indices.items():
        sub = C[ix]
        movibles = (~np.isnan(sub)).sum(1) > 1
        if not movibles.any():
            continue
        # ¿la solución sin flota ya respeta la disponibilidad? entonces es óptima
        pl_sem = o[PLANTA].values[ix]
        uso = pd.Series(1, index=pd.MultiIndex.from_arrays([pl_sem, k_sol[ix]])).groupby(level=[0, 1]).sum()
        lim = F.reindex(uso.index)
        usado_sem = pd.Series(1, index=pd.MultiIndex.from_arrays([pl_sem, k0[ix]])).groupby(level=[0, 1]).sum()
        lim = np.maximum(lim.fillna(0), usado_sem.reindex(uso.index).fillna(0))
        if (uso <= lim).all():
            continue
        ii, kk = np.nonzero(~np.isnan(sub))
        c = sub[ii, kk]
        n_v = len(ii)
        A_eq = sparse.csr_matrix((np.ones(n_v), (ii, np.arange(n_v))), shape=(len(ix), n_v))
        slot = pd.factorize(pd.Series(pl_sem[ii]).astype(str) + '|' + pd.Series(kk).astype(str))
        s_codes, s_uniq = slot
        cap_s = []
        for sname in s_uniq:
            p_, k_ = sname.rsplit('|', 1); k_ = int(k_)
            f = F.get((p_, k_), 0)
            ya = ((pl_sem == p_) & (k0[ix] == k_)).sum()
            cap_s.append(max(f, ya))
        A_in = sparse.csr_matrix((np.ones(n_v), (s_codes, np.arange(n_v))), shape=(len(s_uniq), n_v))
        r = milp(c, constraints=[LinearConstraint(A_eq, 1, 1), LinearConstraint(A_in, 0, np.array(cap_s))],
                 integrality=np.ones(n_v), bounds=Bounds(0, 1))
        if not r.success or r.x is None:
            raise RuntimeError(f"MILP no resuelto: {r.message}")
        x = np.round(r.x).astype(bool)
        k_sol[ix[ii[x]]] = kk[x]
    return k_sol, C

