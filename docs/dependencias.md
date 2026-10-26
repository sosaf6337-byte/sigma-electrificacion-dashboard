# Dependencias revisadas

Consulta a documentación oficial y metadatos PyPI: 2026-10-26. Instalación aislada en `.venv`, sin cambios en el Python compartido. Versiones directas en requirements.in, resolución exacta en requirements.lock.

| Dependencia | Versión | Licencia declarada | Uso |
|---|---|---|---|
| FastAPI | 0.162.0 | MIT | API y validación |
| Uvicorn | 0.54.0 | BSD-3-Clause | Servidor local |
| Pydantic | 2.14.1 | MIT | Contratos numéricos |
| openpyxl | 3.1.5 | MIT | Lectura de Excel |
| pytest | 9.1.1 | MIT | Pruebas |
| httpx | 0.28.1 | BSD-3-Clause | Pruebas de API y cliente OSRM |

Las publicaciones reportadas por PyPI van de 2024 a octubre de 2026; que una versión esté publicada no constituye auditoría de seguridad. No se instaló SciPy, paquetes gráficos de terceros ni herramientas de telemetría. No se configura exportación de telemetría. FastAPI incorpora opentelemetry-api como dependencia transitiva; no se habilitan colectores.

Fuentes: https://fastapi.tiangolo.com/deployment/manually/ ; https://uvicorn.dev/installation/ ; https://openpyxl.readthedocs.io/en/stable/tutorial.html ; https://docs.python.org/3/library/venv.html ; https://pypi.org/.

Leaflet 1.9.4 (BSD-2-Clause) se distribuye localmente con su licencia. No requiere npm ni CDN en ejecución. Véase THIRD_PARTY_NOTICES.md.
