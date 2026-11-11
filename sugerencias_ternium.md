# Sugerencias y preguntas para Ternium (bitácora acumulativa)

Cada entrada: qué vimos, evidencia, qué sugerimos o preguntamos. Estado: 🟡 por confirmar · 🟢 confirmada · ⚪ descartada.
Ventana de datos: viajes con egreso del 2026-01-01 al 2026-08-31.

## Preguntas abiertas

1. 🟡 **Techo de ~26 t en unidades de 2 ejes.** La plataforma de 2 ejes y la caja seca de 2 ejes no pasan de ~26 t (P95) en
   ningún grupo de producto. La NOM-012 permite ~31 t de carga útil (46.5 t de PBV − 15.5 t de tara). ¿Es una política interna,
   una restricción del equipo, de los transportistas o del tipo de camino? Si no hay restricción, hay ~5 t por viaje de holgura legal. **Vale ~28 M MXN en 8 meses**: el right-sizing
   ahorra 27.8 M con el 2 ejes topado en ~26 t, 38.5 M con 29 t y 66.7 M con las 32 t legales.
2. 🟡 **Tara del Full (T3-S2-R4).** Si la tara de 14–17 t aplica también al Full, con 17 t el 19.8% de los Full exceden la carga
   útil legal (49.5 t). Un doble remolque suele pesar más que un sencillo. ¿Cuál es su tara real?
3. 🟡 **Tara del Torton (C3).** Por ahora su capacidad es el techo operativo (P99 = 16.9 t).
4. 🟡 **Hueco de julio.** Julio tiene 6,887 viajes contra ~9,000 en los otros meses. ¿Es un problema de extracción o una baja real?
5. 🟡 **Full solo en Largos Puebla.** Largos Apodaca no usa Full (y sí 44% de 2 ejes). ¿Hay una razón operativa (clientes,
   rutas, permisos)?

## Sugerencias candidatas (a validar con el análisis)

1. 🟡 **Torton contra 2 ejes en CEDIS.** En 13 rutas donde operan ambos (≥5 viajes cada uno), la tarifa del Torton es mayor que
   la del 2 ejes en el 69% de ellas (razón mediana 1.17), y el Torton carga ~15 t contra ~26 t. Donde el producto y el destino
   lo permitan, el 2 ejes sería mejor en costo y en utilización. Muestra chica: hay que revisarlo ruta por ruta.
   **Actualización (C2):** con efectos fijos de ruta, mes y peso, la diferencia Torton vs. 2 ejes no es significativa
   (−1% [−19, +21], 17 rutas). Por ahora no se puede sostener como ahorro.
2. 🟡 **3 ejes casi vacíos en Juventud.** En Juventud, el 25.3% de los viajes en plataforma de 3 ejes va a menos de la mitad de
   su capacidad: 958 viajes llevan ≤10 t en una unidad con 38.5 t legales. La distribución es bimodal (un grupo en 30–35 t y otro
   en 5–10 t); un solo transportista (TRANSPORTISTA_018) tiene una mediana de 7 t. Es la mayor capacidad ociosa del universo
   (59.3 mil t en ocho meses). Candidato directo a Torton o 2 ejes, según la tarifa en esas rutas.
3. 🟡 **Big Coil con 12 t ociosas por viaje.** Utilización agregada de 0.69 [0.68–0.69] y 12.0 t ociosas por viaje: es la
   unidad menos utilizada. Pesquería concentra el 91% de sus viajes (42.5 mil t ociosas). Ternium confirma que esa carga puede
   ir en 3 ejes o 2 ejes. La carga mediana (~26.4 t) cabe en un 2 ejes en lo legal (31 t), pero está justo en el techo
   operativo de ~26 t (ver pregunta 1).
4. 🟡 **CEDI Norte, 3 ejes y Torton con baja carga.** 3 ejes con u = 0.62 [0.55–0.67] y 20% de viajes a u < 0.5; Torton con
   40% de viajes a u < 0.5 (solo 52 viajes, 3 transportistas).
5. 🟡 **Torton caro por tonelada-km.** En distancias < 600 km, el Torton cuesta 3.9–4.5 MXN/t-km [IC 3.0–5.8] contra 1.5–2.3 de
   las plataformas de 2 y 3 ejes en la misma banda. Refuerza la sugerencia 1 (sustituir Torton por 2 ejes donde el destino lo permita).
6. 🟡 **Dimensión económica de la capacidad ociosa.** 21% del gasto en fletes (343 M MXN [310–372] en ene–ago 2026) paga capacidad
   que viaja vacía; Juventud 3 ejes sola son 60 M. Es el tamaño del problema, no el ahorro alcanzable (ver right-sizing).
7. 🟡 **Right-sizing: 3 ejes y Big Coil a 2 ejes.** Con tarifas observadas en la misma ruta, 5,784 viajes (9.9%) podrían ir en una
   unidad más barata: ahorro 38.5 M MXN [20–65] en ene–ago 2026 (2.4% del gasto). Lo principal es 3 ejes → 2 ejes (3,216 viajes
   de ~24 t, 24 M) y Big Coil → 2 ejes (1,651 viajes de ~26 t, 11 M), concentrado en Pesquería, Juventud y Churubusco.
8. 🟡 **Juventud: consolidar, no cambiar de unidad.** De 1,114 viajes en 3 ejes a menos de media capacidad, 423 pueden pasar a 2 ejes
   (3.7 M), pero 630 no tienen otra unidad que ya opere su ruta (no hay Torton en Juventud). El cambio de unidad recupera poco de
   sus 60 M de costo ocioso. La palanca es consolidar pedidos o abrir Torton en esas rutas.
9. 🟡 **Retornos con carga entre plantas.** Solo ~1% de los viajes regresa con carga de Ternium, aunque el 32% de los viajes
   termina a ≤100 km de otra planta de Ternium. Los retornos que sí ocurren se concentran en Largos Puebla ↔ Largos Apodaca y
   Pesquería ↔ CSI San Luis Potosí. Pregunta: ¿se coordina el retorno entre plantas? ¿Las tarifas consideran el viaje redondo?
   (Hoy no se detecta descuento por retorno en la tarifa.)
10. 🟡 **Revisión tarifaria abr–may.** Dentro de la misma ruta, unidad y transportista, la tarifa sube ~3% entre ene–abr y
   jun–ago, con el salto entre finales de abril y mayo. ¿Hubo un ajuste de tarifas? ¿A qué transportistas o rutas aplicó?
11. 🟡 **Fecha de finalización.** `FECHA_VIAJE_FINALIZADO` no parece la llegada física (la placa sale a otro viaje antes de
   esa fecha en 37% de los casos). ¿Qué evento registra? ¿Las placas son del tractor o del remolque?
