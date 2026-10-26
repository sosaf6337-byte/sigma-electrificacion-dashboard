# Demostración pública

La aplicación pública ejecuta `sigma_dashboard.public_app:app`. El servidor local sigue usando `sigma_dashboard.app:app`. Son puntos de entrada diferentes: el público no importa el módulo de importación ni abre la base operativa local.

## Datos y aislamiento

- El despliegue se construye exclusivamente desde el repositorio público. Una comprobación de compilación rechaza Excel, bases SQLite, carpetas de datos/trabajo y configuración local.
- Cada visitante recibe una cookie aleatoria de 256 bits, HttpOnly, Secure bajo el dominio HTTPS de Render y SameSite Strict. El identificador solo sirve para su sesión y no se registra en logs de acceso.
- Cada sesión tiene su propio archivo SQLite en una carpeta temporal ajena al proyecto. El contexto de solicitud se propaga a las operaciones de almacenamiento. Ninguna consulta puede abrir la base de otro visitante mediante un identificador de escenario o ejecución.
- Las sesiones caducan a las 2 horas desde su creación. Se eliminan al revisar la caducidad en la siguiente solicitud o al apagarse la instancia; todo el almacenamiento es efímero y también se pierde en suspensión/reinicio/redeploy. No se promete retención duradera.
- Los endpoints de catálogo, diccionario, importación Excel/CSV y pilotos reales están bloqueados; no basta con ocultar los botones. Los escenarios públicos deben ser sintéticos y su procedencia se registra como supuesta.
- La interfaz solicita no introducir información confidencial. Las coordenadas del mapa se transmiten a OSRM al calcular por calles y las teselas a OSM. Las entradas de prueba y resultados se procesan en el alojamiento Render, aislados entre sesiones, y se pueden exportar.

## Límites de la demostración

24 sesiones simultáneas; como máximo 12 sesiones nuevas por minuto por instancia. Cada sesión admite 6 escenarios, 3 resultados y 90 solicitudes/minuto. Tamaño de petición 600 KB, perfiles de hasta 3,000 puntos, 8 horas de jornada y 20,000 pasos internos. Un cálculo a la vez, intervalo mínimo de 10 segundos entre cálculos de una sesión y un límite aproximado de 20 segundos por simulación. La ruta de demostración de 3 horas cabe en estos límites con sus parámetros predeterminados.

Son límites para una prueba pública pequeña, no un servicio operativo con disponibilidad garantizada ni una protección completa contra abuso distribuido. No utiliza cuentas, correos ni acceso a sistemas SIGMA. Un despliegue institucional requiere autenticación, controles de acceso, cola de trabajo, retención y proveedor de mapas propios.

## Configuración de alojamiento

- Servicio web de Render, plan `free`, un proceso y sin base o disco persistente.
- Construcción: `pip install -r requirements.lock && python scripts/check_public_bundle.py && python -m pytest -q`.
- Inicio: `uvicorn sigma_dashboard.public_app:app --host 0.0.0.0 --port $PORT --workers 1 --no-access-log`.
- Python `3.12.14`. El hostname autorizado se toma de `RENDER_EXTERNAL_HOSTNAME` (variable proporcionada por Render); no se admite un comodín.
- Salud: `/api/health`, sin crear sesiones ni consultar servicios externos.
- Despliegues automáticos deshabilitados para publicar deliberadamente revisiones verificadas. No se crea un colector de telemetría ni se imprimen cookies, entradas de los usuarios o secretos.
- Robots y encabezados indican no indexar. Esto no es control de acceso: el enlace es público por solicitud del usuario.

## Verificación y reversión

Las pruebas comprueban que dos visitantes no pueden leer, modificar, duplicar ni exportar datos del otro; rechazo de cookies falsas y solicitudes de otro origen; bloqueo de importaciones y archivos locales; cookie HTTPS; caducidad; límites de tamaño, sesiones y cómputo; ejecución integrada y exportación. Las pruebas generales de física y API local siguen aplicándose.

Antes de anunciar el enlace: esperar estado `live`, comprobar salud por HTTPS, ejecutar una ruta sintética desde el navegador y repetir una consulta cruzada de sesión sobre el servicio publicado. Ante una exposición de datos o fallo del límite de sesión, suspender el servicio inmediatamente. Para errores de otra naturaleza, desplegar la última revisión verificada del punto de entrada público; nunca sustituirlo por el servidor local.

Render puede suspender servicios gratuitos por inactividad y el siguiente acceso puede tardar alrededor de un minuto. El plan tiene cuotas de uso; no está diseñado para producción. Fuentes: https://render.com/docs/free, https://render.com/docs/health-checks, https://render.com/docs/deploys.
