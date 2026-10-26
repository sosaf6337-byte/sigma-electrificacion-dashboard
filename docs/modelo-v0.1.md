# Modelo físico implementado · v0.1.0

Fecha: 26 de octubre de 2026. Primera implementación ejecutable; pendiente de calibración y validación con jornadas reales de SIGMA. Estas ecuaciones describen el código actual y sus simplificaciones, no una promesa de precisión medida.

## Unidades y acoplamiento

El motor usa segundos, metros, kilogramos, newtons, watts y joules; convierte a kW/kWh solo para presentar resultados. El ciclo se ingresa como tiempo, velocidad y pendiente porcentual. La velocidad y la pendiente se interpolan linealmente. Las entregas ocurren en reposo, reducen la masa y extraen la energía sensible de la mercancía entregada. La caja continúa consumiendo energía durante las paradas.

Todos los subsistemas avanzan sobre el mismo paso de tiempo. El paso se corta en cambios de tramo, entregas y aperturas. La integración explícita reduce el paso según las capacidades y conductancias térmicas. El límite de pasos detiene casos excesivos; no entrega un resultado parcial como completo.

## Tracción

Para cada intervalo, v = (v₀ + v₁)/2, a = (v₁ − v₀)/Δt y θ = atan(pendiente/100).

```text
m = masa lista para operar + mercancía restante
F = (m + m_rot) a + m g Crr cosθ + ½ ρ CdA u |u| + m g sinθ
u = v − viento longitudinal
P_rueda = F v
P_tracción,DC = max(P_rueda, 0) / η_propulsión
F_límite = min(F_máxima, μ m g cosθ · fracción de peso en eje motriz)
```

La masa lista para operar incluye batería, caja y equipo frigorífico, y excluye mercancía. No existe todavía un cálculo automático del aumento de masa al redimensionar baterías: debe ajustarse esa entrada. El usuario declara fuerza máxima y potencia máxima; exceder alguna detiene el recorrido. No hay todavía mapa de torque/velocidad, dinámica de transmisión, temperatura de motor ni transferencia dinámica de peso.

```text
f_baja_velocidad = min(1, v / 2 m/s)
P_regen = min(max(−P_rueda,0) · η_regen · f_baja_velocidad,
              límite regenerativo DC, cargas del bus + aceptación batería)
P_freno_fricción = max(−P_rueda,0) − P_regen / η_regen
```

La regeneración alimenta primero las cargas coincidentes del bus compartido y el excedente carga la batería. El límite de adherencia de frenado, ABS y temperatura de frenos aún no están modelados; las capacidades de frenado del vehículo deben verificarse antes de conclusiones operativas. Las eficiencias constantes y el desvanecimiento regenerativo son aproximaciones explícitas.

## Integración eléctrica y batería

```text
Arquitectura compartida:
P_batería = P_tracción,DC − P_regen + P_refrigeración,DC + P_auxiliares

Arquitectura independiente:
P_principal = P_tracción,DC − P_regen + P_auxiliares
P_batería_frío = P_refrigeración,DC

V_terminal = V_oc − I R
P_terminal = V_oc I − R I²
I = 2 P_terminal / (V_oc + sqrt(V_oc² − 4 R P_terminal))
Q_efectiva = capacidad_nominal_kWh · 3 600 000 · SOH / V_oc
SOC_nuevo = SOC − I Δt / Q_efectiva
P_pérdidas = I² R
```

Corriente positiva significa descarga. Se verifican aceptación de carga, potencia de descarga, SOC superior y reserva. El algoritmo conserva E_química = E_terminal + E_pérdidas. La batería usa tensión de circuito abierto y resistencia constantes; no modela temperatura, mapas SOC/temperatura, envejecimiento temporal ni restricciones de celdas individuales. Las dos baterías no comparten regeneración ni energía sin una conexión explícita, que esta versión no implementa.

## Caja, aire y mercancía

Tres zonas longitudinales, cada una con pared, aire y dos nodos de producto: superficie y centro. La masa se reparte en tercios y se descarga proporcionalmente. Se fijó una fracción térmica superficial de 20 % y central de 80 % como reducción del modelo, pendiente de identificación por producto/empaque.

```text
G_exterior = G_interior = 2 UA / 3
C_pared,z = C_pared,total / 3
C_aire,z = ρ_aire · volumen / 3 · cp_aire
C_producto,z = masa_producto / 3 · cp_producto

C_pared,z dT_pared,z/dt = G_exterior(T_sol−aire − T_pared,z)
                       − G_interior(T_pared,z − T_aire,z)

C_aire,z dT_aire,z/dt = Q_pared + Q_producto + Q_infiltración
                    + Q_interno + Q_mezcla − Q_evaporador,sensible,z

0.2 C_producto,z dT_superficie,z/dt = −Q_producto + Q_centro→superficie
0.8 C_producto,z dT_centro,z/dt = −Q_centro→superficie
```

La suma de intercambios internos se cancela en el balance. La conductancia total UA ya incluye el efecto del área y puentes térmicos; el campo de superficie se conserva como descriptor, no multiplica UA otra vez. El volumen interior se trata como volumen efectivo de aire, sin descontar explícitamente estiba: debe calibrarse y esta simplificación debe eliminarse al introducir geometría real.

La temperatura solar equivalente usa absorptividad, fracción expuesta, irradiancia y convección exterior simplificada dependiente de velocidad/viento. El clima es constante en esta versión. No se resuelven orientación de cada cara, radiación infrarroja, contacto con piso ni paneles separados por material.

## Infiltración, humedad y refrigeración

```text
caudal_infiltración = ρ_aire · volumen · (ACH_fugas + ACH_puerta) / 3600
Q_infiltración,sensible,z = caudal_z cp_aire (T_exterior − T_aire,z)
m_aire_seco,z dw_z/dt = caudal_z(w_exterior − w_z)
                     + mezcla_humedad − condensado_evaporador,z

T_evap = T_retorno − aproximación_evaporador
T_cond = T_exterior + aproximación_condensador
COP = fracción_Carnot · (T_evap + 273.15) / max(3, T_cond − T_evap)
P_compresor = Q_evaporador,total / COP
P_refrigeración,DC = (P_compresor + P_ventiladores + P_control + P_deshielo)
                   / η_conversión
```

Infiltración por ACH es un parámetro de calibración; no representa por sí sola geometría de puerta, viento y flotación. Con puerta abierta, el flujo se reparte 10/20/70 %; la extracción sensible 45/33/22 %. La mezcla entre zonas es simétrica. La psicrometría utiliza presión de referencia de 101325 Pa; debe sustituirse por presión local para altitudes relevantes.

El equipo tiene capacidad limitada, reducción simplificada por temperatura exterior y escarcha, termostato con histéresis y deshielo programado. El evaporador extrae humedad con límite por flujo de aire, agua disponible y 65 % de capacidad frigorífica. El límite de 65 %, COP mínimo 0.2 y pisos de capacidad 25 % son supuestos de esta implementación; no provienen de mapas de SIGMA ni de un fabricante. La energía latente incluye congelación cuando la temperatura evaporadora es negativa.

La escarcha y el deshielo son estados simplificados. No se cierra todavía un balance total de entalpía de aire húmedo, agua y hielo con drenaje. Se comprueban por separado energía sensible y masa de vapor. Si el aire queda sobresaturado, la pantalla identifica la limitación de condensación superficial y declara la evaluación térmica insuficiente. No debe interpretarse ese caso como una predicción fiable de consumo frigorífico o conservación.

## Recarga, costos y decisión

La recarga posterior es una estimación separada del recorrido, con límites de cargador, batería, carga estacionaria y potencia del sitio si se ingresa. Usa una reducción ilustrativa de potencia por encima de 80 % de SOC; no es una curva de fabricante. El objetivo es recuperar el SOC inicial. La recarga de arquitectura independiente permanece pendiente de estrategia y cargadores por rama.

Costo energético = kWh de red estimados × precio proporcionado. Ahorro requiere litros de una línea base confirmada con el mismo alcance. Recuperación simple sobre energía requiere rutas/año e inversión incremental. No incluye demanda, mantenimiento, sustitución de batería, financiamiento ni TCO/VAN; no sustenta una recomendación financiera.

La interfaz separa factibilidad del perfil bajo supuestos, evaluación térmica, operación, infraestructura y economía. No emite una conclusión global afirmativa cuando faltan datos.

## Ruta hacia mayor fidelidad

1. Registrar GPS, elevación, corriente/tensión/SOC, temperaturas de aire y centro/superficie de producto, humedad, puertas y descarga con reloj común.
2. Incorporar mapas de motor/inversor, transmisión, batería y equipo frigorífico con dominio válido explícito; impedir extrapolación silenciosa.
3. Ampliar paredes por cara/capas, volumen de aire libre, presión local, condensación superficial, drenaje, hielo y control real de deshielo; cerrar el balance total de entalpía.
4. Incorporar precooling desde red, clima temporal, carga parcial, recogidas, recarga por rama y límites térmicos de componentes.
5. Identificar parámetros con jornadas de calibración y evaluar error de energía, potencia, SOC y temperatura sobre jornadas independientes. Publicar residuos, intervalos y condiciones de validez; no inventar una precisión objetivo cumplida.

## Referencias de fundamento

- [FHWA: modelación del movimiento vehicular](https://www.fhwa.dot.gov/publications/research/operations/18037/004.cfm).
- [FASTSim: ciclos de conducción](https://natlabrockies.github.io/fastsim/drive-cycle/). Referencia metodológica; esta aplicación no usa el motor FASTSim.
- [EnergyPlus: Engineering Reference](https://energyplus.net/documentation). Referencia para evolución del balance frigorífico; la implementación actual no equivale a EnergyPlus.

Las correlaciones y constantes simplificadas expuestas arriba se deben reemplazar por evidencia específica del sistema. Las referencias no validan automáticamente este código ni sus parámetros.
