# Planificador geográfico y acoplamiento

## Arquitectura

`static/route.js` presenta Leaflet local, selección de escenario/camión, puntos arrastrables, orden, descarga y apertura. `POST /api/map-route` valida de 2 a 25 puntos y construye un plan. `routing.py` obtiene distancias por calles de OSRM o calcula distancias geodésicas directas únicamente cuando se selecciona ese modo.

La ruta de calles utiliza el perfil driving para automóvil y comprueba que cada punto pueda aproximarse a una calle a menos de 500 m. No valida accesibilidad ni restricciones de camión. La red de calles aporta distancia y geometría; no aporta un ciclo medido ni pendiente. El tiempo del proveedor se conserva como referencia separada.

## Construcción del perfil

Para cada tramo de longitud d, velocidad de crucero vc y aceleración/frenado a:

- v = min(vc, sqrt(d·a)).
- Tiempo de cada rampa: v/a.
- Tiempo de crucero: max(0, (d − v²/a)/v).
- La integral trapezoidal de velocidad devuelve exactamente d, incluyendo perfiles triangulares cortos.

El camión se detiene en cada punto. Se agrega la permanencia configurada con velocidad cero. La apertura ocupa el comienzo de la parada y la masa descargada se retira al llegar, coherente con el modelo actual de entrega instantánea y estiba homogénea. El resto de la permanencia tiene puertas cerradas. El modelo frigorífico permanece en control térmico durante movimiento y parada. Las potencias se integran en la arquitectura de batería seleccionada.

La pendiente es un supuesto constante editable. No se simulan tráfico, pendientes variables, curvas ni semáforos intermedios. Una ruta de ida y vuelta con pendiente constante distinta de cero no representa su topografía real. Para eso se requiere el perfil temporal medido mediante CSV.

## Reproducibilidad y errores

`route_plan` se guarda con el escenario y la ejecución: puntos, geometría, distancias, horario, proveedor, fecha, supuestos y hash del perfil. Modificar puntos invalida la previsualización y exige calcular otra vez. Cambiar el perfil o las entregas manualmente desvincula el plan guardado cuando el hash deja de coincidir. Las ejecuciones anteriores permanecen inmutables.

Un fallo de conexión muestra un error conservando los puntos; no genera una ruta alternativa oculta. Puntos consecutivos idénticos, tramos menores de 10 m, jornadas mayores de 24 h, coordenadas inválidas, apertura superior a parada o descarga sin apertura se rechazan. La simulación verifica carga total y restricciones físicas.

## Servicios externos

Solo las coordenadas viajan a OSRM cuando se pulsa calcular por calles. Las teselas de OSM revelan el área consultada al proveedor. No hay claves, geolocalización del dispositivo, geocodificación, tráfico ni importación automática de rutas reales. El servicio público es para demostración e investigación no comercial y no ofrece garantía operativa. Consultar THIRD_PARTY_NOTICES.md antes de ampliar el uso.

## Verificación

Pruebas sin red: integración exacta de distancias largas/cortas, orden temporal, paradas, apertura, descarga de masa, consumo frigorífico detenido, guardado/relectura, ejecución y desvinculación tras editar el perfil. Los fallos del proveedor se prueban mediante sustitución controlada. Las pruebas generales revisan los balances físicos, límites y exportación.

Prueba manual local: recorrido ilustrativo de Monterrey de aproximadamente 9 km, una parada de 15 min, puerta abierta 5 min y entrega de 250 kg. Se comprobó cálculo por calles, simulación completa y separación de consumos. Esto valida el flujo de software, no una ruta SIGMA ni el desempeño real del camión.
