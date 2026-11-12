# Proyecto Ternium – Bitácora (actualizada 2026-11-10)

> Este archivo es la memoria del proyecto. Se actualiza en cada hito. En una conversación nueva con Claude, adjúntalo
> (o ponlo como `CLAUDE.md` en la raíz del repo) antes de pedir nada.

## 1. Qué estamos haciendo
- Análisis de datos para Ternium sobre viajes foráneos de camiones (base: `viajes_foraneos_plata.csv` → oro).
- Entrega actual: **Componente 1 = línea base**. Lineamientos clave: cada número con incertidumbre; bootstrap por
  conglomerados (proveedor/ruta/semana, justificando la elección); ventana y segmentación declaradas.
- **Reto B**: utilización u = max sobre dimensiones (carga/capacidad) por tipo de camión; costo por viaje, por tonelada y por
  tonelada-km (¿cambia el orden de los tipos según la métrica?); descomposición de capacidad ociosa (camión más barato
  compatible que puede llevar la carga completa; la diferencia es una cota superior del ahorro evitable).
- **Métrica de la Entrega 1 (explicada 2026-11-10)**: enfoque de *right-sizing*. "Mejor" = menor costo por tonelada (y por
  ton-km) al mover la carga de un viaje a una unidad más chica/barata que la pueda llevar dentro de la NOM-012-SCT-2. El usuario
  quería un modelo estadístico de costo por camión según distancia, peso y material para estimar el ahorro de la operación sugerida.
- **Hallazgo clave (2026-11-10)**: el costo por viaje es en la práctica una tarifa fija por ruta × tipo × transportista. En
  2,574 celdas con ≥5 viajes (62,204 viajes), el CV mediano del costo por viaje es 3.1% (22% de las celdas tienen costo idéntico)
  y la elasticidad costo-peso dentro de la celda es 0.02. Entonces costo/ton ≈ tarifa / peso: el ahorro de right-sizing es la
  diferencia de tarifas entre tipos en la misma ruta. Un modelo de costo hace falta solo para rutas sin tarifa observada del tipo alternativo.
- Con solo el peso medido, u_i = q/c_peso ≤ u real (la verdadera es el máximo sobre dimensiones) → la capacidad ociosa y el
  ahorro calculados son cotas superiores. La compatibilidad física se aproxima con el grupo de producto (`GRUPO_PLANTA_ORIGEN`).

## 2. Datos
- Plata: 71,967 viajes. Egresos 2026-01-01 → 2026-09-01 (ocho meses; septiembre solo 23 viajes; julio 6,887 vs ~9,000 en
  otros meses: posible hueco de extracción, por confirmar). NO es un año: no decir "anual".
- El oro viejo (`data_engineer.py`) tenía 55,388 viajes: su filtro IQR eliminó ~16,579 (23%), incluidos viajes largos y los más
  ineficientes. Los resultados anteriores calculados sobre ese oro están sesgados.
- Sin datos de volumen/largo ni de producto: solo existe el peso. `GRUPO_PLANTA_ORIGEN` es lo más cercano a producto.

## 3. Decisiones tomadas
- Km: **nunca se imputan con medianas**. Origen de la fuente en `Km_Fuente` (osrm, estimado_haversine, faltante, multidestino, region…).
- Multidestino (destino con coma, 46 viajes) y `CDMX+EDOMEX` (región, 801 viajes): se excluyen de ton-km.
- Plantas sin coordenadas: se geocodifican por **ciudad** (`config/plantas.csv`, a mano). Destinos en `config/destinos_canonicos.csv`.
- Km sospechoso (velocidad implícita >90 o <3 km/h, o km<5): se conserva el viaje; `Costo_Ton_Km` queda en NaN y existe
  `Costo_Ton_Km_Bruto` para sensibilidad. Los km estimados no cuentan como `Km_Confiable`.
- Outliers: se marcan (`Flag_*`), no se eliminan. Solo se rechazan registros imposibles (`viajes_rechazados.csv`).
- Tipo de camión: solo por texto declarado (`FAMILIA_CAMION_DESC`, con respaldo en `Tipo Camión`). No se reclasifica por peso
  (la regla vieja `Programado_kg>38500 → Full` era circular). Exceso de capacidad: `Excede_Capacidad`.
- Capacidades en `capacidades_config.csv`, **sin verificar** contra NOM-012-SCT-2 (que fija peso bruto; falta restar tara).
  "Plataforma larga 40 pies" aún sin capacidad.
- `Costo_Ton_Optimo` / `Sobrecosto_Ton` suponen consolidación total: cota superior laxa (≈238 M MXN, 17.9% del gasto), NO ahorro ejecutable.

## 4. Hallazgos de la auditoría del notebook Componente 1 (sobre el oro viejo)
1. Los "Full" de las gráficas de costo son 288 camiones de 3 ejes con 38.5–39.9 t reetiquetados; los 527 Full reales (todos Largos)
   no tienen km y no aparecen. Full real: mediana $46,492/viaje y $967/ton.
2. "Ahorro ejecutable" 41.6 M: no reproducible exacto (yo obtuve 4,090 viajes cambiados y 44.2 M puntual; el notebook 3,828).
   964 viajes de 3 ejes→Full aportan 10.4 M (24%) con benchmark contaminado; con benchmark de la misma ruta, ese tramo cae a 0.46 M.
   Tramo 3 ejes→2 ejes: en 154 rutas con ambos tipos (≥5 viajes c/u) el 2 ejes es más barato en 92% (razón mediana 0.76) → sólido.
   Estimación defendible provisional: ~19–22 M (no 41.6 M). Benchmark por ruta, no por segmento de distancia.
3. "Dimensión que amarra" estaba inventada (`u_volumen`=1.0 para Largos, 0.85·u_peso resto). Datos: u_peso Largos media 0.868 vs
   Masivos 0.784 → contradice la hipótesis de cube-out.
4. IC del ahorro (mi reproducción, punto 44.2 M): por ruta 34.6–54.7; por transportista 25.3–64.8; por semana 39.3–48.8.
   Hay que justificar el conglomerado; transportista es el más defendible (tarifas). Top 5 transportistas = 46% del ahorro.
5. El orden de tipos SÍ cambia por métrica (ej. Torton: #1 por viaje, #5 por ton-km) → historia de "la métrica que engaña",
   a rehacer con Full reales y km validados.
6. La tabla "intervalo P25-P75" es dispersión, no IC de la mediana. Faltan IC en todas las medianas/utilizaciones.

## 1b. Enfoque reformulado por el usuario (2026-11-10)
- El costo del viaje lo explican transportista, ruta y camión (contratos por camión × ruta); el peso no lo mueve.
- Objetivo final: un modelo que reciba el **peso programado** y el destino (y la planta de origen) y devuelva la unidad más eficiente
  (costo y utilización) y, como dato informativo, transportistas con tarifa observada. La asignación de transportista queda
  fuera de alcance (dinámicas internas).
- Métrica principal declarada por el usuario: **costo por tonelada-km**. Matiz acordado/por discutir: dentro de una ruta los km
  son fijos, así que para decidir la unidad, costo/ton-km ≡ costo/ton ≡ tarifa/q. El costo/ton-km sirve para comparar entre
  rutas y plantas, pero la tarifa tiene un componente fijo (elasticidad tarifa-km: 2E 0.90, 3E 0.76, Torton 0.42) → baja con la
  distancia; las comparaciones entre rutas deben segmentarse por distancia o hacerse contra un valor esperado.
- Tarea actual: revisar utilizaciones y decidir en qué casos mover cargas a unidades que mejoren la utilización y, si se puede,
  ahorren. Las sugerencias para Ternium se acumulan en `sugerencias_ternium.md`.

## 4b. Hallazgos sobre el oro v2 (2026-11-10, ventana ene–ago)
- Largos viajan en plataformas estándar: 2 ejes (3,383), 3 ejes (12,174), Full (729, todos Largos). Nunca en Torton/Tortoneta.
- Techo de peso observado (P95) casi igual entre grupos de producto: 2 ejes ≈26 t (Largos 25.9, Masivos 25.9), 3 ejes ≈36–37 t,
  Full ≈50.6 t. → Para Largos amarra el peso, no el largo: se pueden incluir en right-sizing (restringido a tipos que ya los cargan).
- La capacidad de 2 ejes en config (32 t) está muy por encima del techo operativo (~26 t) → u de 2 ejes subestimada, ociosidad inflada.
- Largos en 3 ejes con ≤25.5 t (cabrían en 2 ejes): solo 369 de 12,174.
- Varianza de log(costo/viaje) explicada (R²): ruta 0.942; transportista 0.601; tipo 0.131; ruta×tipo 0.966; ruta×tipo×transportista 0.992.
  Mediana 2 transportistas por ruta×tipo (55.8% de celdas con >1). 136 transportistas, 1,600 rutas.

- Regla de Largos ACEPTADA por el usuario: entran al right-sizing solo hacia tipos que ya los cargan (2 ejes, 3 ejes, Full).
- NOM-012 (tabla PBV, camino ET y A) proporcionada por el usuario. Mapeo (los "ejes" de los datos son los del semirremolque):
  2 ejes = T3-S2 46.5 t; 3 ejes y Portacintas = T3-S3 54.0 t; Full = T3-S2-R4 66.5 t (NA en camino B); Torton = C3 10 llantas 27.5 t;
  Tortoneta = C2 19.0 t. Camioneta 3.5, Heavy, Cama baja, plataformas largas: sin mapeo aún. Falta TARA por tipo para carga útil.
- Tara implícita (PBV − P99 observado): 2E 17.6, 3E 15.9, Portacintas 17.1, Full 15.5, Torton 10.6, Tortoneta 8.4 → el 2 ejes
  carga muy por debajo de su máximo legal (techo ~26 t) y el Full podría rebasarlo si su tara real es ~18–20 t. Por aclarar.

## 4c. Indicaciones de Ternium (2026-11-10) y universo v2
1. Excluir 3 ejes Cortina. 2. Análisis por planta/bodega. 3. El "ahorro" se mide en TONELAJE (utilización de flota); el dinero
   se calcula como traducción. 4. Big Coil (FAMILIA "... BIG COIL") SÍ entra y su carga puede moverse a 3 ejes o incluso 2 ejes;
   Portacintas común ("BASES PORTACINTAS") NO.
- Tara 14–17 t (Ternium) → central 15.5: carga útil legal 2E 31.0, 3E/Big Coil 38.5, Full 51.0 (pendiente: ¿aplica al Full?).
- Universo (por `FAMILIA_CAMION_DESC`): Torton, 2 Ejes (plataforma neumática/muelles/desacoplada), Caja Seca 2 Ejes, 3 Ejes
  (neumática, muelles, corta, corta ligera, ultra ligera), Big Coil, Full = 58,275 viajes (81.0%), 1.671 Mt (81.3%).
  Caja seca y Torton REINCLUIDOS por decisión del usuario (unidades cerradas que pueden mover otras cargas si son rentables).
  Excluidos con motivo trazado: Cortina (2E y 3E), Portacintas, Tortoneta, Camioneta, Heavy, Cama baja, plataformas largas 40/48/53.
- Caja seca: 285 viajes, todos de Juventud; techo 26.7 t (mismo ~26 t que la plataforma 2E). Torton: solo CEDIS; P99 16.9 t;
  NOM C3 (10 llantas) 27.5 t; tara de Torton PENDIENTE (la de 14–17 t no le aplica).
  DECISIÓN usuario: por ahora capacidad del Torton = techo operativo (P99 observado).
- Big Coil: 91% sale de Pesquería (3,541 de 3,872). Full: 100% de Largos Puebla. CEDI Mexico: 96% en 2 ejes.
- Notebook: secciones 1–3 nuevas al inicio de `componente_1.ipynb`; las celdas viejas quedan abajo bajo un separador "Versión anterior".

## 4d. Utilización (sección 4 del notebook, IC bootstrap por transportista B=2000)
- **Taras por unidad (supuesto provisional del usuario, 2026-11-10)**: Ternium casi nunca excede el límite legal (si lo hace, con
  permiso). Taras dentro de 14–17 t, con orden físico y ≤1% de viajes excedidos: 2E 14.5 (cap 32.0), Caja seca 16.0 (30.5),
  3E 15.5 (38.5), Big Coil 16.5 (37.5), Full 15.5 (51.0; físicamente baja, pendiente), Torton = P99 (16.9). Banda [14,17] = sensibilidad.
  Con esto: 2E u 0.75 [0.74–0.76], 109.5 kt ociosas; Big Coil u 0.71 [0.70–0.71], 42.8 kt; resto igual que abajo.
  (Las cifras siguientes son de la versión anterior con tara única de 15.5 t.)
- Decisión: regla de unidad = menor tarifa entre unidades factibles; desempate por mayor utilización (aceptada por el usuario).
- u agregada por unidad: Torton 0.85 [0.80–0.88], 2E 0.77 [0.76–0.78], Caja seca 0.74 (1 transportista), 3E 0.81 [0.79–0.83],
  Big Coil 0.69 [0.68–0.69], Full 0.95 [0.95–0.96]. Contra el techo operativo P99: 2E 0.83, Big Coil 0.86 → parte de la
  ociosidad legal no es accionable sin confirmar el tope de ~26 t.
- Ociosa total (kt, 8 meses): 3E 280.8, 2E 95.8, Big Coil 46.7, Torton 5.3, Caja seca 2.3, Full 1.8.
- Mayores focos: Juventud 3E (u 0.65, 25% viajes u<0.5, 59.3 kt), Pesquería 3E 55.6 kt, Churubusco 3E 46.5 kt,
  Pesquería Big Coil 42.5 kt, CEDI Norte 3E (u 0.62).
- Excede la carga útil legal (tara 17 t): 3E 1,285; Full 144; 2E 75. Torton: 21 sobre su P99 (por construcción).

## 4e. Costo de la capacidad ociosa (sección 5 del notebook, 2026-11-11)
- Definición: CO_i = tarifa_i × (1 − min(u_i,1)). Identidad: CO_i = (costo/t-km real − costo/t-km a capacidad llena) × t-km movidas.
  Es TAMAÑO DEL PROBLEMA (cota superior, exige consolidación perfecta), no ahorro alcanzable; el ahorro sale del right-sizing.
- IC: bootstrap por transportista (`bootstrap_razones`, generaliza el de la sección 4); totales = proporción (IC) × gasto observado.
- Universo: gasto 1,636 M MXN (ene–ago); CO legal 343 M [310–372] = 20.9% [18.9–22.8]; contra techo operativo P99 292 M (17.9%).
- Por unidad (% del gasto legal): 3E 202 M (19%), 2E 112 M (25%; operativo 77 M → el tope de ~26 t pesa), Big Coil 20 M (30%),
  Torton 4.5 M (15%), Full 1.9 M (5%), Caja seca 1.9 M (31%). MXN por t no cargada: universo 775 [659–900].
- Top: Juventud 3E 60.4 M (36% de su gasto, $1,019/t no cargada), Pesquería 3E 30.7, Largos Apodaca 2E 28.9, Largos Apodaca 3E 28.2,
  Churubusco 3E 25.4, Juventud 2E 21.6. 15 celdas = 93%.
- Costo/t-km por banda de distancia (km confiable, 94.7%): Torton 3.9–4.5 MXN/t-km en < 600 km contra 1.5–2.3 de 2E/3E.
  Sobrecosto por capacidad ociosa (1/u − 1): 2E +31–36%, Big Coil +40–44%, 3E +22–28%, Full +5%.

## 4f. Bootstrap de dos vías y right-sizing (2026-11-11)
- DECISIÓN: IC por bootstrap de dos vías transportista × ruta (pigeonhole, Owen 2007), función `bootstrap_conglomerados`
  (sección 4.2). Sensibilidad en la celda siguiente: viaje/semana subestiman; con solo transportista, Big Coil (12 transp.) y caja
  seca (1) salen con IC casi nulo. Resultados robustos: CO total 343 M [302–378]; Juventud 3E 60.4 [48.3–74.4] sigue primero.
- Right-sizing (sección 6). Reglas: tarifa de referencia = mediana ruta × unidad (≥5 viajes); factible si q ≤ min(legal, P99) y la
  unidad ya opera la ruta; caja seca no pasa a abierta; se mueve si ≥3% más barata; desempate por u. Bootstrap de dos vías
  recalculando tarifas (B=1000).
- Resultado base: 5,784 viajes (9.9%), ahorro 38.5 M [20.2–65] = 2.35% del gasto (≈11% del costo ocioso); bajar 35.2 M, subir 3.3 M.
  3E→2E 3,216 viajes 24.1 M [17.4–28.5]; Big Coil→2E 1,651 viajes 10.8 M [7.4–13.4]; Torton→2E 1.4 M (sube, CEDIS).
  u flota 0.791→0.799; capacidad liberada 23.3 kt. Por planta: Pesquería 15.3 M, Juventud 9.5 M, Churubusco 5.2 M.
- Sensibilidad: umbral 0–10% → 36.9–38.7 M (estable). Capacidad 2E: P95 (~26 t) 27.8 M; P99 (29 t) 38.5 M; legal (32 t) 66.7 M →
  el tope de 2 ejes vale ~28 M. Benchmark del mismo transportista (1,381 viajes): 10.4 vs 12.7 M, sugerida más barata en 84%.
- IC sesgado hacia arriba (elegir el mínimo de tarifas ruidosas = "maldición del ganador"); el punto es razonable.
- CAMBIO (2026-11-11, pedido del usuario): el bootstrap de la sección 6 ahora evalúa los MISMOS movimientos (decisión base fija)
  con tarifas remuestreadas (antes re-decidía en cada réplica → IC acotado en 0 por construcción). Nuevo total 38.5 M [17.4–62.6]
  (incluye incertidumbre de composición, dos vías). Por movimiento: 3E→2E 24.1 [17.2–29.4]; BC→2E 10.8 [7.4–12.9];
  Torton→2E 1.4 [−0.4–1.8]; 2E→3E 1.2 [−2.6–3.3]; 3E→Full 0.5 [−0.9–1.1]. Por planta: Pesquería 15.3 [5.5–28.7],
  Juventud 9.5 [4.8–15.1], Churubusco 5.2 [1.3–10.0]; Largos Apodaca 2.3 [−2.4–4.3] y Largos Puebla 0.5 [−1.9–2.8] cruzan 0.
- Juventud 3E ligeros (u<0.5, 1,114 viajes): 423 pasan a 2E (3.7 M); 630 no tienen tarifa de 2E en su ruta y no hay Torton en
  Juventud → para ellos es problema de consolidación (o de abrir unidad chica), no de cambio de unidad. Recupera poco de 60 M.

## 4g. Convenciones de presentación (usuario, 2026-11-11)
- Solo se grafica lo que lleva IC; lo descriptivo (universo, mezcla por planta, capacidades, histogramas) va en tabla.
  Títulos centrados, subtítulos cortos (IC y ventana), etiquetas con el valor solamente. Tablas compactas (pocas columnas).
- `titulo(fig, texto, sub)` se llama al final de cada figura y hace el `tight_layout`.
- Histogramas de carga vs capacidad por unidad RESTAURADOS (2026-11-11, pedido del usuario), tras la tabla de la 4.2, con u agregada
  e IC 95 % en cada panel.
- Notebook: 6 figuras (utilización planta×unidad; % del gasto ocioso por unidad; top-10 costo ocioso; costo/t-km real vs lleno;
  movimientos de right-sizing; utilización antes/después y ahorro por planta). Respaldos previos en el scratchpad.
- DECISIÓN: los movimientos que suben de unidad (2E→3E, Torton→2E, 3E→Full) SÍ cuentan en el ahorro reportado (38.5 M),
  identificados aparte como "subir de unidad".

## 4h. Componente 2 — DAG (2026-11-11)
- Pendiente de Ternium: ¿cuántos 2 ejes adicionales por semana pueden surtir los transportistas por planta?; ¿revisión tarifaria abr–may?, nodos faltantes (cliente que exige unidad, ventanas), retorno.
- Lineamientos C2: validación temporal, solo info al momento de decidir, supuestos diagnosticados, robustez (3–4 decisiones),
  falsificación; Reto B: DAG + positividad + sensibilidad (Cinelli-Hazlett/valor E), econometría con EF de ruta y retorno,
  optimización con restricciones de la entrevista y sensibilidad a IC, simulador que reproduzca la línea base de C1.
- `componente_2.ipynb`: sección 1 (DAG) nueva arriba; lo viejo bajo separador (problemas: oro viejo, Nomenclatura_Inferida,
  ahorro = real − predicho con clip(0), fuga en clusters de destino, "Q4/anual" falsos). Código común en `ternium_comun.py`.
- DAG: T = tipo de camión, C = costo del viaje. Ajuste = EF de ruta (absorbe planta/producto, destino, distancia, retorno
  esperado) + peso programado + mes (transportista solo en sensibilidad). No ajustar: peso real, utilización, retorno realizado, costo/ton.
  ENTREVISTA (usuario, 2026-11-11): Ternium pide la unidad según lo que va a cargar y luego los transportistas ofertan →
  flecha tipo → transportista; el transportista es MEDIADOR. Estimando principal = efecto total (ajuste: EF ruta + peso
  programado + mes, SIN transportista); sensibilidad = mismo transportista. Coincide con el right-sizing de C1 (medianas
  de ruta entre transportistas). No observado (urgencia, requisitos del cliente) → Cinelli-Hazlett.
  Positividad (celdas ≥5 viajes): 175 de 600 rutas con >1 tipo = 69% de los viajes; con transportista fijo solo ~10%.
- Evidencia: peso prog. → tipo +7.5 t (3E vs 2E, misma ruta); peso prog. → costo elasticidad 0.026 [0.009–0.043];
  peso real | prog. 0.18 [−0.09–0.45] (poca potencia); periodo → costo +3.2% [1.8–4.6] (salto fines abr–may: posible
  revisión tarifaria → preguntar a Ternium); periodo → tipo n.s.; transportistas especializados (84% en su tipo principal;
  solo ~10% de ruta×transportista con >1 tipo → alerta de positividad).
- Peso programado ≈ real en la mayoría (mediana de diferencia 0); 1,328 con Flag_Discrepancia (p. ej. 72 t) se excluyen.

## 4i. Componente 2 — retorno y efecto del tipo de camión (secciones 2–3, 2026-11-11)
- FECHA_VIAJE_FINALIZADO NO es llegada física (37% de las veces la placa sale antes; P95 duración 14 días) → ciclos solo
  con egresos + geografía. 14.4% de pares consecutivos de una placa son físicamente imposibles (>80 km/h): placa ≠ camión único.
- Retorno con carga Ternium (≤100 km del destino, planta >100 km del origen, ≤48 h de holgura): ~1% de viajes (1–2.6% al
  variar umbrales). Destino cerca de otra planta: 32% de viajes, pero solo 3% regresa con carga Ternium. Corredores:
  Largos Puebla↔Largos Apodaca, Pesquería↔CSI SLP. "Es retorno" (pre-decisión) = confusor ajustado; "Consigue retorno" = control negativo.
- Efecto por pares (soporte común: rutas con ≥5 viajes de cada unidad; EF ruta + mes + log peso prog. + es retorno; IC 2 vías):
  2E vs 3E −20.8% [−24.2, −17.2] (~−5,200 MXN/viaje; 207 rutas; mismo transp. −26%; RV 44%; con confusor = peso prog. −18%);
  2E vs Big Coil −28.8% (9 rutas); 3E vs Big Coil −9.5% pero −0.8% mismo transportista (efecto de proveedor, no de unidad);
  2E vs Torton −1.3% [−19, +21] NO significativo (17 rutas) → sugerencia Torton→2E sin respaldo; Full vs 3E +21.5%.
  Cobertura: 2E vs 3E cubre 48% de viajes 3E; Full vs 3E 7%.
- Retorno no abarata (−2.1% n.s.; +0.3% mismo transportista). Control negativo FALLA parcialmente: consigue retorno −3.2%
  [−5.8, −0.5]; con mismo transportista −0.8% → factores no ajustados de ~1–3%; no afecta 2E vs 3E (−21%) pero sí efectos pequeños.

## 4j. Componente 2 — robustez y falsificación (sección 4, 2026-11-11)
- Robustez (7 variantes: soporte ≥2/≥20, peso real, incluir pesos imposibles, solo km confiable, sin mayo): 2E vs 3E entre
  −20.6% y −21.1%; 2E vs Big Coil −28.7% a −29.3%. En pesos: 2E vs 3E −31% (pesan más rutas largas).
- Replicación: 2E vs 3E ene–jun −19.7% [−23.4, −15.8], jul–ago −25.2% [−28.1, −22.3]; 2E vs BC jul–ago −32% (IC no estimable).
  Mes a mes: 8/8 meses negativos sin incluir 0.
- Placebo (permutar D dentro de ruta, 500): centrado en 0 (±0.5%), p<0.002. Nota: permutar dentro de ruta×mes NO sirve
  (la proporción mensual conserva señal → media −2.2%).
- Homogeneidad: 2E más barato en 91% [87–95] de rutas con 3E; pero esas 9% rutas tienen 21% de los viajes → decidir por ruta.

## 4k. Componente 2 — modelo de elección de unidad (sección 5, 2026-11-11)
- HistGradientBoosting; entradas solo pre-decisión: peso programado, planta, grupo, coord. destino, km, mes, es retorno,
  historial de la ruta (% por unidad con viajes ANTERIORES, suavizado hacia la planta). Sin transportista/peso real/costo.
  Entrena ene–may, valida jun (lr 0.05, 31 hojas), reentrena ene–jun, prueba jul–ago.
- Exactitud jul–ago: modelo 94.9% [92.4–96.8], regla "más usada en la ruta" 81.9% [74.8–87.7]; balanceada 0.94 vs 0.50.
  Importancia: peso programado 30 pp, historial ruta 14 pp, distancia 2, planta 1.5; mes y retorno ~0.
- Comparación con Random Forest (sección 5.1b; one-hot de planta/grupo, min_samples_leaf=5 por log-loss en jun): exactitud
  94.5% [91.4–97.0] vs boosting 94.9%; diferencia pareada +0.4% [−0.7, +2.1] (empate); log-loss RF 0.180 vs 0.156 → se queda
  el boosting porque el simulador usa las probabilidades.
- Atípicos (P(unidad más chica) ≥ 0.5): 3.3% de 3E en jul–ago (301), peso mediano 24 t; vs right-sizing C1 ~9% de 3E →
  el ahorro es sobre todo CAMBIO DE POLÍTICA (pedir 2E para ~24 t en rutas que hoy usan 3E sistemáticamente), no corrección de errores.

## 4l. Componente 2 — optimización (sección 6, 2026-11-11)
- `capacidades()` en ternium_comun.py (legal, P99, decisión = mín). Optimización: min Σ T̂_rk x_ik; 1 unidad por viaje;
  q_prog ≤ c_k; unidad con tarifa en la ruta (≥5 viajes); caja seca no a abierta; materialidad 3%; disponibilidad de flota
  Σ_{p,w} x_ik ≤ F_pk (máx semanal observado, nunca < lo usado esa semana). MILP por semana (HiGHS); estructura de transporte.
- Con peso real y sin flota reproduce C1 exacto (5,784 viajes, 38.5 M). Con peso programado 34.9 M; con flota 31.6 M
  (4,721 viajes; u 0.791→0.796). Por movimiento: 3E→2E 19.5 M, BC→2E 7.9, Torton→2E 1.3, BC→3E 1.2, 2E→3E 1.15, 3E→Full 0.4.
- Sensibilidad: tarifas ±5% → 30.7–34.2 M, 81% de movimientos estables (≥90% réplicas); bootstrap de tarifas (Poisson por
  transportista dentro de ruta×unidad; NO remuestrear rutas: desaparecen) → 30.4–38.1 M, 63%. Estabilidad por tipo:
  3E→2E 78%, BC→2E 75%, Torton→2E 7%, 2E→3E 16%, Full 0%. Flota P75 → 18.8 M (parámetro más sensible). Umbral 0–5% ≈ igual.

## 4m. Componente 2 — simulador (sección 7, 2026-11-11)
- Demanda: viajes reales remuestreados por ruta × semana (pigeonhole), pesos normalizados; totales = promedio por viaje ×
  viajes reales del periodo. Política actual: unidad sorteada del modelo de la sección 5. Right-sizing: optimizador con flota,
  decidido con tarifas y flota de ene–jun, aplicado a jul–ago. Costo: observado si la unidad es la real; si no, sorteo de la
  celda ruta×unidad (jun–ago si ≥5, si no todo el periodo). 500 réplicas; números aleatorios comunes (pareado).
- Validación ene–ago (actual simulado vs C1): costo/viaje 28,182 [25,330–31,311] vs 28,082 [23,285–33,483]; u 0.790 vs 0.791
  [0.770–0.815]; % ocioso 21.0 vs 20.9 [18.5–23.0] → 3/3 dentro. Placebo modelo de costos: +0.8% (conservador para el RS).
- Jul–ago fuera de muestra: 1,474 de 13,800 viajes cambian; ahorro 6.2 M [3.3–10.0] (1.5%), positivo en 100% de réplicas;
  u +0.48 pp [0.06–0.97]; ociosa −3.0 kt [0.4–6.2]. ~25 M en ritmo de 8 meses (vs 31.6 M in-sample de la sección 6).
- Componente 2 completa (secciones 1–7). Falta: hilo conductor del reporte; respuestas de Ternium.

## 5. Estado del código (carpeta `etl/`)
- `etl_oro.py` (ETL v2) + `test_etl.py`. `distancias_v2.py` + `test_distancias.py` (17 pruebas totales, pasan).
- Orden: ETL → `distancias_v2.py --solo-tablas` (llenar plantas/destinos) → `distancias_v2.py` → ETL con `--catalogo catalogo_distancias_v2.csv`.
- Reporte de calidad inicial (ETL v2 sobre plata): 45,266 viajes con km confiable, 22,491 sin km, 4,210 sospechosos; 421 exceden capacidad.
- **Estado al 2026-11-10 (tarde)**: `distancias_v2.py` terminado. Se corrigieron typos en config (`plantas.csv`: Apocada→Apodaca;
  destinos: Tlaltelulco, Totimehuacán) y se reejecutó. ETL rerun con `data/distancias_v2/catalogo_distancias_v2.csv` →
  `data/oro_v2/`: 68,414 km confiables, 2,427 sospechosos, 0 faltantes, 88 multidestino, 1,037 región, 1 sin geocodificar
  ("Zonas Postales*NU"). Los 729 FULL NEUMATICA ya tienen km (729/729).
- Factor carretera calibrado: 1.252 (1,534 rutas OSRM).
- Rutas a Baja California Sur (Los Cabos, Cd. Constitución; 29 viajes): OSRM da ~3,300–4,200 km por tierra vía Mexicali
  (ratio 2.8–3.7). Si en la práctica cruzan en ferry (Topolobampo/Mazatlán→La Paz), los km reales son mucho menores. POR DECIDIR.
- Los archivos `test_etl.py` / `test_distancias.py` NO están en el repo (no se encontraron).
- (2026-11-12) `etl_oro.py` había perdido lógica (editado 18:07 del 10-nov, después de generar oro_v2). Reconstruido y
  VERIFICADO: reproduce data/oro_v2 exacto (todas las columnas y archivos auxiliares). Reglas: Flag_Discrepancia_Peso =
  |programado − real| > 1,000 kg; Es_Multidestino = ',' en destino; Es_Region = '+'; Km_Estimado = fuente estimado_haversine
  (no confiable); Costo_Ton_Km_Bruto sin filtro; Km_Fuente conserva motivo del catálogo; respaldo `Tipo Camión` si la familia
  es nula (plataforma 40 pies); rutas_pendientes con columna Fuente.

## 6. Pendientes
1. ~~Revisar salidas de distancias; rerun del ETL con catálogo v2~~ (hecho 2026-11-10). Queda: decidir ruta ferry vs. tierra a BCS.
2. Capacidad de Plataforma larga 40 pies; verificar capacidades contra NOM-012; revisar 421 viajes con `Excede_Capacidad`.
3. Revisar `Flag_Discrepancia_Peso` (pesos programados de 72 t, etc.).
4. Confirmar hueco de julio con quien entregó los datos.
5. Rehacer Componente 1 sobre el oro nuevo: Full reales, benchmark por ruta, IC por conglomerado justificado, ventana declarada, sin volumen inventado.
6. Entender la definición de "mejor" de la Entrega 1 y alinear la línea base.
