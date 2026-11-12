"""Componente 4: ¿Cuánto ganaría Ternium realmente? (Reto B: right-sizing)

Parte del número ingenuo del Componente 3 (MILP con disponibilidad de flota, 31.6 M MXN, mismo universo de
58,275 viajes de `tc.cargar_universo()`) y lo encoge paso a paso: factibilidad, respaldo causal del
Componente 2, maldición del optimizador (partición de datos), disponibilidad de unidades y respuesta del
mercado. Reporta escenarios por supuestos con su intervalo muestral (bootstrap de dos vías transportista ×
ruta, como C1–C3), el punto de quiebre, la anualización, la holgura estructural y el tamaño de un piloto.

Ejecutar desde la raíz del proyecto:  python componente_4.py
"""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

import ternium_comun as tc
import componente_3_optimizacion as opt

OUT = Path('resultados_ternium')
OUT.mkdir(exist_ok=True)
B, SEMILLA = 2000, 2026
CAP_FFD = 36.575                                  # límite de consolidación de C3 (95 % de 38.5 t)

# ----------------------------------------------------------------------------
# 1. Datos y número ingenuo (réplica exacta de C3)
# ----------------------------------------------------------------------------
df = tc.cargar_universo().reset_index(drop=True)
df['Programado_t'] = df['Programado_kg'] / 1000
assert len(df) == 58275
opt.preparar_optimizador(df)
o = opt.o
N, K = len(o), opt.K
U = np.array(tc.UNIDADES)
IDX = {u: i for i, u in enumerate(tc.UNIDADES)}
k0, rr = o['k0'].to_numpy(), o['r'].to_numpy()
qr = df['Toneladas_Reales'].to_numpy()
PERM0, CAPDEC0, Q0 = opt.PERMITIDO.copy(), opt.CAP_DEC.copy(), o['q'].copy()
semana = df['FECHA_EGRESO'].dt.to_period('W')
par = (semana.apply(lambda p: p.ordinal) % 2 == 0).to_numpy()
mes = df['FECHA_EGRESO'].dt.to_period('M')
n_meses = mes.nunique()
gasto = df['Costo'].sum()
print(f"Universo: {N:,} viajes, {n_meses} meses, gasto {gasto/1e6:,.1f} M MXN")


def pares(lista):
    """Matriz de movimientos permitidos: la unidad actual y los pares indicados."""
    M = np.eye(K, dtype=bool)
    for a, b in lista:
        M[IDX[a], IDX[b]] = True
    return M & (PERM0 | np.eye(K, dtype=bool))


# Respaldo causal (C2, sección 3): 2E vs 3E −20.8 % [−24.2, −17.2]; 2E vs Big Coil −28.8 %; 3E vs Big Coil −9.5 %.
# Sin respaldo: Torton→2E (−1.3 % [−19, +21], n.s.), 3E→Full (Full +21.5 %), 2E→3E (2E más barato en 91 % de rutas;
# estable solo en 16 % de réplicas), movimientos a Torton o caja seca (sin efecto estimado).
CAUSAL = [('3 Ejes', '2 Ejes'), ('Big Coil', '2 Ejes'), ('Big Coil', '3 Ejes')]
ESTRICTO = [('3 Ejes', '2 Ejes'), ('Big Coil', '2 Ejes')]
FLAG = df['Flag_Discrepancia_Peso'].astype(bool).to_numpy()
CAP2E_P95 = float(df.loc[df['Unidad'] == '2 Ejes', 'Toneladas_Reales'].quantile(.95))


def configurar(perm=None, excluir_flag=False, cap_2e=None):
    """Fija los supuestos del optimizador de C3 (variables de módulo que leen factibles/resolver)."""
    opt.PERMITIDO = PERM0 if perm is None else perm
    opt.CAP_DEC = CAPDEC0.copy()
    if cap_2e is not None:
        opt.CAP_DEC[IDX['2 Ejes']] = cap_2e
    # peso programado no confiable: el viaje no se mueve (ninguna unidad alternativa es factible)
    o['q'] = np.where(excluir_flag & FLAG, np.inf, Q0)


def flota(q):
    """Disponibilidad semanal por planta × unidad: máximo observado (C3) o un cuantil de las semanas."""
    return opt.F_max if q >= 1 else opt.semanal.groupby(level=[0, 2]).quantile(q)


def decidir(T, F):
    k, _ = opt.resolver(T, con_flota=True, F=F)
    k = k.copy()
    k[qr > opt.CAP_LEG[k]] = k0[qr > opt.CAP_LEG[k]]    # peso real no cabe en la unidad nueva: no se cambia
    return k


def en_muestra(F):
    """Ahorro como en C3: misma muestra para elegir y para medir."""
    T = opt.tarifas()
    k = decidir(T, F)
    m = k != k0
    a, tn = np.zeros(N), np.zeros(N)
    a[m] = T[rr[m], k0[m]] - T[rr[m], k[m]]
    tn[m] = T[rr[m], k[m]]
    return a, tn, k


def crossfit(F):
    """Maldición del optimizador: decidir con las tarifas de semanas pares y medir en las impares (y al revés)."""
    a, tn, kf = np.zeros(N), np.zeros(N), k0.copy()
    for A in (par, ~par):
        TA, TB = opt.tarifas(A.astype(float)), opt.tarifas((~A).astype(float))
        k = decidir(TA, F)
        m = (~A) & (k != k0)
        d, t = TB[rr[m], k0[m]] - TB[rr[m], k[m]], TB[rr[m], k[m]]
        sin = np.isnan(d)                 # la celda no aparece en la mitad de evaluación (pocos viajes)
        d[sin] = (TA[rr[m], k0[m]] - TA[rr[m], k[m]])[sin]
        t[sin] = TA[rr[m], k[m]][sin]
        a[m], tn[m], kf[m] = d, t, k[m]
    return a, tn, kf


# ----------------------------------------------------------------------------
# 2. Bootstrap de dos vías transportista × ruta (pigeonhole, igual que tc.bootstrap_conglomerados)
# ----------------------------------------------------------------------------
celda = pd.MultiIndex.from_arrays([df['Transportista'], df['Ruta_ID']])
cod_cel, uniq_cel = pd.factorize(celda)
ct = pd.factorize(uniq_cel.get_level_values(0))[0]
cr = pd.factorize(uniq_cel.get_level_values(1))[0]
rng = np.random.default_rng(SEMILLA)
W = (rng.multinomial(ct.max() + 1, np.full(ct.max() + 1, 1 / (ct.max() + 1)), size=B)[:, ct]
     * rng.multinomial(cr.max() + 1, np.full(cr.max() + 1, 1 / (cr.max() + 1)), size=B)[:, cr]).astype(float)
n_cel = np.bincount(cod_cel, minlength=len(uniq_cel)).astype(float)
DEN = W @ n_cel


def sorteos(x):
    """Totales bootstrap normalizados a N viajes (como C3): B réplicas."""
    return (W @ np.bincount(cod_cel, weights=x, minlength=len(uniq_cel))) / DEN * N


def ic(x):
    return np.percentile(sorteos(x), [2.5, 97.5])


# ----------------------------------------------------------------------------
# 3. Evidencia: tarifario implícito y prima de mercado
# ----------------------------------------------------------------------------
modal = df.groupby(['Ruta_ID', 'Unidad', 'Transportista'], observed=True)['Costo'].transform(lambda s: s.mode().iloc[0])
pct_tarifa = float((df['Costo'] == modal).mean())
fuera = (df['Unidad'] == '2 Ejes') & (df['Costo'] != modal)
prima_obs = (df.loc[fuera, 'Costo'] / modal[fuera] - 1)
prima_obs = prima_obs[prima_obs > 0]
PRIMA_C, PRIMA_P = float(prima_obs.median()), float(prima_obs.quantile(.75))
print(f"Viajes cobrados a la tarifa modal (ruta × unidad × transportista): {pct_tarifa:.1%}")
print(f"2 Ejes cobrados arriba de su tarifa: {len(prima_obs):,}; prima mediana {PRIMA_C:.1%}, P75 {PRIMA_P:.1%}")

# ----------------------------------------------------------------------------
# 4. Cascada (escenario central)
# ----------------------------------------------------------------------------
cascada = []


def paso(nombre, corto, a, tn=None):
    lo, hi = ic(a)
    cascada.append(dict(Ajuste=nombre, Corto=corto, Ahorro_M=a.sum() / 1e6, IC_inf_M=lo / 1e6, IC_sup_M=hi / 1e6,
                        Viajes=int((a != 0).sum())))
    print(f"{a.sum()/1e6:7.2f} M [{lo/1e6:6.2f}, {hi/1e6:6.2f}] | {int((a != 0).sum()):6,} viajes | {nombre}")


print('\n=== CASCADA (ene–ago 2026, M MXN, IC 95 % transportista × ruta) ===')
configurar()
a0, _, k_c3 = en_muestra(opt.F_max)
paso('0. Número ingenuo: MILP con flota de C3', 'Ingenuo\n(MILP C3)', a0)
assert abs(a0.sum() / 1e6 - 31.60) < 0.01

configurar(excluir_flag=True)
a1, _, _ = en_muestra(opt.F_max)
paso('1. Factibilidad: peso programado confiable y peso real dentro de la capacidad legal', 'Factibilidad', a1)

configurar(perm=pares(CAUSAL), excluir_flag=True)
a2, _, _ = en_muestra(opt.F_max)
paso('2. Solo movimientos con efecto causal estimado en C2 (3E→2E, Big Coil→2E, Big Coil→3E)', 'Respaldo\ncausal (C2)', a2)

a3, _, _ = crossfit(opt.F_max)
paso('3. Maldición del optimizador: elegir con semanas pares, medir con impares (y al revés)', 'Maldición del\noptimizador', a3)

Q_C = 0.90
a4, tn4, k4 = crossfit(flota(Q_C))
paso('4. Disponibilidad: unidades por planta y semana = P90 semanal observado (no el máximo)', 'Disponibilidad\n(P90 semanal)', a4)

a5 = a4 - PRIMA_C * tn4
paso(f'5. Respuesta del mercado: la unidad adicional se paga con prima de {PRIMA_C:.1%}', f'Prima de\nmercado {PRIMA_C:.1%}', a5)
cascada = pd.DataFrame(cascada)
cascada.drop(columns='Corto').to_csv(OUT / 'componente_4_cascada.csv', index=False, encoding='utf-8-sig')
a_cen, tn_cen, k_cen = a5, tn4, k4

mov = pd.DataFrame({'De': U[k0], 'A': U[k_cen], 'ah': a_cen})[k_cen != k0]
print(mov.groupby(['De', 'A']).ah.agg(['size', 'sum']).assign(sum=lambda x: x['sum'] / 1e6))

# ----------------------------------------------------------------------------
# 5. Escenarios por supuestos, cada uno con su IC muestral
# ----------------------------------------------------------------------------
ESC = {
    'Optimista': dict(perm=None, q=1.0, prima=0.0, cap_2e=None,
                      txt='todos los movimientos de C3; flota = máximo semanal; sin prima; 2E hasta 29 t (P99)'),
    'Central': dict(perm=CAUSAL, q=Q_C, prima=PRIMA_C, cap_2e=None,
                    txt=f'movimientos con respaldo causal; flota = P90 semanal; prima {PRIMA_C:.1%}; 2E hasta 29 t'),
    'Pesimista': dict(perm=ESTRICTO, q=0.75, prima=PRIMA_P, cap_2e=CAP2E_P95,
                      txt=f'solo 3E→2E y Big Coil→2E; flota = P75 semanal; prima {PRIMA_P:.1%}; 2E hasta {CAP2E_P95:.1f} t (P95)'),
}
k_anual = 12 / n_meses
filas, ahorros = [], {}
for nombre, p in ESC.items():
    configurar(perm=None if p['perm'] is None else pares(p['perm']), excluir_flag=True, cap_2e=p['cap_2e'])
    a, tn, k = crossfit(flota(p['q']))
    a = a - p['prima'] * tn
    ahorros[nombre] = a
    lo, hi = ic(a)
    filas.append(dict(Escenario=nombre, Supuestos=p['txt'], Viajes=int((k != k0).sum()),
                      Rutas=int(df.loc[k != k0, 'Ruta_ID'].nunique()),
                      Ahorro_M=a.sum() / 1e6, IC_inf_M=lo / 1e6, IC_sup_M=hi / 1e6,
                      Anual_M=a.sum() / 1e6 * k_anual, Anual_inf_M=lo / 1e6 * k_anual, Anual_sup_M=hi / 1e6 * k_anual,
                      Pct_gasto=a.sum() / gasto * 100))
esc = pd.DataFrame(filas)
esc.to_csv(OUT / 'componente_4_escenarios.csv', index=False, encoding='utf-8-sig')
print('\n=== ESCENARIOS ===')
print(esc.drop(columns='Supuestos').round(2).to_string(index=False))
assert np.allclose(ahorros['Central'], a_cen)

# Sensibilidad a la disponibilidad (resto del central fijo)
configurar(perm=pares(CAUSAL), excluir_flag=True)
sens_flota = []
for q in [1.0, 0.95, 0.90, 0.75, 0.50]:
    a, tn, k = crossfit(flota(q))
    sens_flota.append(dict(Cuantil=q, Viajes=int((k != k0).sum()), Ahorro_M=(a - PRIMA_C * tn).sum() / 1e6))
sens_flota = pd.DataFrame(sens_flota)
print(sens_flota.round(2).to_string(index=False))

# ----------------------------------------------------------------------------
# 6. Punto de quiebre: prima sobre la tarifa de la unidad nueva que borra el ahorro central
# ----------------------------------------------------------------------------
S_a, S_t = sorteos(a4), sorteos(tn4)
p_quiebre = a4.sum() / tn4.sum()
p_q_ic = np.percentile(S_a / S_t, [2.5, 97.5])
pct_sobre_q = float((prima_obs > p_quiebre).mean())
tarifa_media = tn4[k4 != k0].mean()
print(f"\nQuiebre de prima: {p_quiebre:.1%} [{p_q_ic[0]:.1%}, {p_q_ic[1]:.1%}]; tarifa media de la unidad nueva "
      f"${tarifa_media:,.0f}; de los 2E cobrados arriba de tarifa, {pct_sobre_q:.1%} superan el quiebre")
primas = np.linspace(0, 0.40, 81)
curva = np.array([(a4.sum() - p * tn4.sum()) for p in primas]) / 1e6 * k_anual
curva_ic = np.array([np.percentile(S_a - p * S_t, [2.5, 97.5]) for p in primas]) / 1e6 * k_anual

# ----------------------------------------------------------------------------
# 7. Validación temporal: decidir con ene–jun, medir en jul–ago (como el simulador de C2)
# ----------------------------------------------------------------------------
H1 = (df['FECHA_EGRESO'] < '2026-07-01').to_numpy()
configurar(perm=pares(CAUSAL), excluir_flag=True)
T1, T2 = opt.tarifas(H1.astype(float)), opt.tarifas((~H1).astype(float))
F1 = o[H1].groupby([tc.PLANTA, 'Semana', 'k0']).size().groupby(level=[0, 2]).quantile(Q_C)
kv = decidir(T1, F1)
mv = (~H1) & (kv != k0)
dv = T2[rr[mv], k0[mv]] - (1 + PRIMA_C) * T2[rr[mv], kv[mv]]
sin = np.isnan(dv)
dv[sin] = (T1[rr[mv], k0[mv]] - (1 + PRIMA_C) * T1[rr[mv], kv[mv]])[sin]
a_val = np.zeros(N); a_val[mv] = dv
val_lo, val_hi = ic(a_val)
cen_julago = a_cen[~H1].sum()
print(f"Validación jul–ago (decidido con ene–jun): {a_val.sum()/1e6:.2f} M [{val_lo/1e6:.2f}, {val_hi/1e6:.2f}], "
      f"{mv.sum():,} viajes; el central atribuye a jul–ago {cen_julago/1e6:.2f} M")

# ----------------------------------------------------------------------------
# 8. Anualización
# ----------------------------------------------------------------------------
mensual = pd.DataFrame({'Ahorro_M': pd.Series(a_cen).groupby(mes.to_numpy()).sum() / 1e6,
                        'Viajes_cambiados': pd.Series(k_cen != k0).groupby(mes.to_numpy()).sum(),
                        'Viajes': df.groupby(mes).size().values,
                        'Gasto_M': df.groupby(mes)['Costo'].sum().values / 1e6})
mensual['Pct_gasto'] = mensual['Ahorro_M'] / mensual['Gasto_M'] * 100
mensual.index = mensual.index.astype(str)
mensual.to_csv(OUT / 'componente_4_ahorro_mensual.csv', encoding='utf-8-sig')
print(mensual.round(2).to_string())
tot = a_cen.sum()
anual = tot * k_anual
anual_bajo = tot + 4 * mensual['Ahorro_M'].min() * 1e6
anual_alto = tot + 4 * mensual['Ahorro_M'].max() * 1e6
# julio tiene 5,630 viajes contra ~7,500 de los demás meses (posible hueco de extracción, C1)
jul = mensual.loc['2026-07']
viajes_tipicos = mensual.drop('2026-07')['Viajes'].mean()
anual_jul = (tot + jul['Ahorro_M'] * 1e6 * (viajes_tipicos / jul['Viajes'] - 1)) * k_anual
print(f"Anual ×12/8: {anual/1e6:.1f} M; sep–dic como el peor/mejor mes: {anual_bajo/1e6:.1f}–{anual_alto/1e6:.1f} M; "
      f"con julio completado a volumen típico: {anual_jul/1e6:.1f} M; % del gasto {tot/gasto:.2%}")

# ----------------------------------------------------------------------------
# 9. Holgura estructural e indivisibilidad
# ----------------------------------------------------------------------------
ociosa_act = np.maximum(opt.CAP_LEG[k0] - qr, 0).sum() / 1e3
ociosa_cen = np.maximum(opt.CAP_LEG[k_cen] - qr, 0).sum() / 1e3
co_ton = df['Costo'] / np.maximum(qr, 1e-9)
print(f"\nCapacidad ociosa legal: actual {ociosa_act:,.1f} kt; central {ociosa_cen:,.1f} kt "
      f"(recupera {ociosa_act-ociosa_cen:,.1f} kt = {(ociosa_act-ociosa_cen)/ociosa_act:.1%})")


def ffd(clave):
    """FFD de C3 (3 ejes de la misma ruta, peso programado, cargas indivisibles) con otra ventana de tiempo."""
    q = df['Programado_t'].to_numpy()
    elim = np.zeros(N, bool); inv = np.zeros(N, bool)
    eleg = ((df['Unidad'].astype(str) == '3 Ejes') & df['Ruta_ID'].notna() & df['Ciudad Destino'].notna()
            & (df['Programado_t'] > 0) & (df['Programado_t'] <= CAP_FFD) & (df['Toneladas_Reales'] > 0))
    for _, g in df.loc[eleg].groupby([clave[eleg], tc.PLANTA, 'Ciudad Destino', 'Ruta_ID'], observed=True, dropna=True):
        bins = []
        for i in g.index[np.argsort(-q[g.index], kind='stable')]:
            for b in bins:
                if b[0] + q[i] <= CAP_FFD + 1e-9:
                    b[0] += q[i]; b[1].append(i); break
            else:
                bins.append([q[i], [i]])
        for _, ids in bins:
            if len(ids) > 1:
                elim[ids[1:]] = True; inv[ids] = True
    return int(inv.sum()), int(elim.sum()), float(df.loc[elim, 'Costo'].sum())


fecha = df['FECHA_EGRESO']
consol = pd.DataFrame([dict(Ventana=n, Involucrados=r[0], Eliminados=r[1], Ahorro_M=r[2] / 1e6)
                       for n, c in [('Mismo día (C3)', fecha.dt.normalize()),
                                    ('Misma semana', fecha.dt.to_period('W').astype(str)),
                                    ('Mismo mes', fecha.dt.to_period('M').astype(str))]
                       for r in [ffd(c)]])
consol.to_csv(OUT / 'componente_4_consolidacion.csv', index=False, encoding='utf-8-sig')
print(consol.round(2).to_string(index=False))
peso_med = float(np.median(qr))
pct_dos_caben = float((qr <= CAP_FFD / 2).mean())
print(f"Peso real mediano {peso_med:.1f} t; viajes con ≤ {CAP_FFD/2:.1f} t (dos cabrían juntos): {pct_dos_caben:.1%}")

# ----------------------------------------------------------------------------
# 10. Piloto: switchback por ruta × semana
# ----------------------------------------------------------------------------
cambia = k_cen != k0
rutas = (pd.DataFrame({'Ruta': df['Ruta_ID'], 'a': a_cen, 'c': cambia})[cambia]
         .groupby('Ruta').agg(Viajes=('c', 'size'), Ahorro_M=('a', 'sum')).sort_values('Ahorro_M', ascending=False))
rutas['Ahorro_M'] /= 1e6
top = list(rutas.head(10).index)
pct_top = rutas.head(10)['Ahorro_M'].sum() / rutas['Ahorro_M'].sum()
# Métrica: costo por tonelada de TODAS las cargas elegibles de las rutas piloto (unidad de origen o destino de los
# movimientos con respaldo y peso programado que cabe en 2 ejes); entran también los viajes que no se cambian.
eleg = (df['Unidad'].astype(str).isin(['2 Ejes', '3 Ejes', 'Big Coil']) & (df['Programado_t'] <= CAPDEC0[IDX['2 Ejes']])
        & df['Ruta_ID'].isin(top) & ~FLAG & (qr > 0)).to_numpy()
# y = log(costo/t) del viaje: el costo/t en pesos tiene colas enormes (P99 = 4.4× la mediana) por cargas ligeras.
# δ = reducción esperada en log del costo del viaje si se aplica la regla (los viajes que no cambian aportan 0).
pil = pd.DataFrame({'Ruta': df['Ruta_ID'][eleg], 'Sem': semana[eleg].astype(str), 'y': np.log(co_ton[eleg]),
                    'd': -np.log1p(-np.clip(a_cen[eleg] / df['Costo'].to_numpy()[eleg], -0.9, 0.9))})
delta = float(pil['d'].mean())
pil['res'] = pil['y'] - pil.groupby('Ruta')['y'].transform('mean')
sigma = float(pil['res'].std())
z = 1.959964 + 0.841621                       # α = 5 % dos colas, potencia 80 %
n_iid = int(np.ceil(2 * z**2 * sigma**2 / delta**2))
g = pil.groupby(['Ruta', 'Sem'])['res']
mbar = float(g.size().mean())
icc = max(0.0, (g.mean().var() - sigma**2 / mbar) / sigma**2)
deff = 1 + (mbar - 1) * icc
n_clu = int(np.ceil(n_iid * deff))
bloques = int(np.ceil(n_clu / mbar))          # bloques ruta × semana por brazo
por_semana = len(pil) / semana.nunique()
semanas = int(np.ceil(2 * bloques / len(top)))
print(f"\nPiloto: δ={delta:.3f} log ({np.expm1(delta):.1%}), σ={sigma:.3f} → n iid={n_iid:,}/grupo; ICC={icc:.3f}, "
      f"m={mbar:.1f}, DEFF={deff:.2f} → n={n_clu:,} viajes/grupo = {bloques} bloques ruta×semana; "
      f"{por_semana:.0f} cargas elegibles/semana → {semanas} semanas")
print(rutas.head(10).round(2).to_string())
print(f"Top 10 rutas = {pct_top:.0%} del ahorro central")

resumen = dict(N=N, n_meses=n_meses, gasto=gasto, pct_tarifa=pct_tarifa, prima_c=PRIMA_C, prima_p=PRIMA_P,
               n_prima=len(prima_obs), cap2e_p95=CAP2E_P95, flag=int(FLAG.sum()),
               cascada=cascada.drop(columns='Corto').to_dict('records'), escenarios=esc.to_dict('records'),
               sens_flota=sens_flota.to_dict('records'),
               p_quiebre=p_quiebre, p_quiebre_ic=list(p_q_ic), pct_sobre_quiebre=pct_sobre_q, tarifa_media=tarifa_media,
               validacion=dict(ahorro=a_val.sum(), ic=[val_lo, val_hi], viajes=int(mv.sum()), central_julago=cen_julago),
               anual=anual, anual_bajo=anual_bajo, anual_alto=anual_alto, anual_jul=anual_jul, pct_gasto=tot / gasto,
               ociosa_act=ociosa_act, ociosa_cen=ociosa_cen, consolidacion=consol.to_dict('records'),
               peso_med=peso_med, pct_dos_caben=pct_dos_caben,
               piloto=dict(delta=delta, sigma=sigma, n_iid=n_iid, icc=icc, mbar=mbar, deff=deff, n_clu=n_clu, bloques=bloques,
                           por_semana=por_semana, semanas=semanas, rutas=top, pct_top=pct_top),
               movimientos=mov.groupby(['De', 'A']).ah.agg(['size', 'sum']).reset_index().to_dict('records'))
json.dump(resumen, open(OUT / 'componente_4_resumen.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=1,
          default=lambda x: x.item() if hasattr(x, 'item') else str(x))

# ----------------------------------------------------------------------------
# 11. Figuras (estilo común de ternium_comun; solo se grafica lo que lleva IC)
# ----------------------------------------------------------------------------
tc.aplicar_estilo()
AZUL, NARANJA = tc.SECUENCIAL[4], tc.COLOR_UNIDAD['2 Ejes']

# Figura 4.1: cascada con IC de cada nivel
fig, ax = plt.subplots(figsize=(11, 5.2))
v, lo, hi = cascada['Ahorro_M'].values, cascada['IC_inf_M'].values, cascada['IC_sup_M'].values
x = np.arange(len(v))
for i in x:
    if i == 0:
        ax.bar(i, v[i], width=0.6, color=tc.TINTA_3)
    else:
        d = v[i] - v[i - 1]
        ax.bar(i, v[i], width=0.6, color=AZUL if i == len(v) - 1 else tc.SECUENCIAL[1])
        ax.text(i, hi[i] + 1.2, f'{d:+.2f}' if abs(d) < 0.1 else f'{d:+.1f}', ha='center', va='bottom',
                color=NARANJA, fontsize=10, fontweight='bold')
    ax.errorbar(i, v[i], yerr=[[v[i] - lo[i]], [hi[i] - v[i]]], fmt='none', ecolor=tc.TINTA, capsize=4, lw=1.1)
    claro = 0 < i < len(v) - 1
    ax.text(i, lo[i] / 2, f'{v[i]:.1f}', ha='center', va='center', color=tc.TINTA if claro else 'white',
            fontweight='bold')
ax.set_axisbelow(True)
ax.set_xticks(x, cascada['Corto'])
ax.set_ylabel('Ahorro ene–ago 2026 (M MXN)')
ax.set_ylim(0, hi.max() * 1.12)
ax.grid(axis='x', visible=False)
tc.titulo(fig, 'Del número ingenuo al número creíble',
          'Escenario central · IC 95 %: bootstrap transportista × ruta · cambio de cada paso en naranja')
fig.savefig(OUT / 'componente_4_cascada.png', dpi=200); plt.close(fig)

# Figura 4.2: escenarios anualizados y curva de la prima
fig, (f1, f2) = plt.subplots(1, 2, figsize=(12, 4.8), gridspec_kw={'width_ratios': [1, 1.2]})
orden = ['Pesimista', 'Central', 'Optimista']
r = esc.set_index('Escenario').loc[orden]
yy = np.arange(3)
f1.errorbar(r['Anual_M'], yy, xerr=[r['Anual_M'] - r['Anual_inf_M'], r['Anual_sup_M'] - r['Anual_M']],
            fmt='o', color=AZUL, ecolor=AZUL, capsize=5, ms=8, lw=1.6)
for i, (_, row) in enumerate(r.iterrows()):
    f1.annotate(f"{row['Anual_M']:.1f}", (row['Anual_M'], i), xytext=(0, 9), textcoords='offset points', ha='center')
f1.set_yticks(yy, orden); f1.set_ylim(-0.6, 2.6)
f1.set_xlim(0, r['Anual_sup_M'].max() * 1.1)
f1.set_xlabel('Ahorro anualizado (M MXN/año)')
f1.set_title('Escenarios por supuestos')
f2.fill_between(primas * 100, curva_ic[:, 0], curva_ic[:, 1], color=tc.SECUENCIAL[0])
f2.plot(primas * 100, curva, color=AZUL, lw=2)
f2.axhline(0, color=tc.TINTA_3, lw=0.9)
f2.axvline(p_quiebre * 100, color=tc.TINTA, lw=1.1, ls='--')
f2.annotate(f'Quiebre {p_quiebre:.0%}', (p_quiebre * 100, curva.max() * 0.9), xytext=(5, 0), textcoords='offset points')
for pr in (PRIMA_C, PRIMA_P):
    yv = np.interp(pr, primas, curva)
    f2.plot(pr * 100, yv, 'o', color=NARANJA, ms=7)
    f2.annotate(f'{pr:.1%}', (pr * 100, yv), xytext=(6, 6), textcoords='offset points', color=tc.TINTA_2)
f2.set_xlabel('Prima sobre la tarifa de la unidad nueva (%)')
f2.set_ylabel('Ahorro anualizado (M MXN/año)')
f2.set_title('¿Cuánto puede subir la tarifa?')
tc.titulo(fig, '¿Cuánto ganaría Ternium realmente?',
          'IC 95 %: bootstrap transportista × ruta · base ene–ago 2026 × 12/8 · puntos naranjas: prima observada (mediana y P75)')
fig.savefig(OUT / 'componente_4_escenarios_quiebre.png', dpi=200); plt.close(fig)
print('Figuras guardadas.')
