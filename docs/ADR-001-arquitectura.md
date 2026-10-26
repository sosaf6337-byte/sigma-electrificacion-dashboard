# ADR-001 — Aplicación local y motor físico independiente

Estado: aceptada para el inicio local. Fecha: 2026-10-26.

## Contexto

La carpeta estaba vacía. El libro aporta catálogos e indicadores agregados, pero no un ciclo de conducción ni parámetros frigoríficos suficientes para validar una ruta. Se necesita importar sin modificar, explorar calidad, configurar escenarios reproducibles y desarrollar el motor por niveles de fidelidad verificables.

## Decisión

- Python 3.12, FastAPI y Pydantic: API local, contratos explícitos y validación dimensional por campos con unidades. Uvicorn escucha únicamente en 127.0.0.1.
- openpyxl: lectura del libro, sin recalcular ni escribir el original. Copia con SHA-256; errores y cachés de fórmulas visibles.
- SQLite: escenarios y ejecuciones inmutables con sus entradas. Base local, uso de un solo equipo; no abrir la misma base simultáneamente desde dos equipos vía OneDrive.
- HTML, CSS y módulos JavaScript nativos: interfaz sin CDN ni proceso de compilación; gráficos SVG y tablas accesibles.
- Motor de simulación independiente: módulos de tracción, térmico y batería, sin dependencias de la API. Integración conservativa de flujos y verificación de convergencia.
- Los valores de ejemplo viven exclusivamente en una plantilla sintética. Un equipo real seleccionado genera un borrador incompleto; no hereda esos valores.

## Alternativas

Streamlit simplifica un prototipo, pero dificulta controlar interacción, formularios y persistencia reproducible. React con un servicio Python ofrece más herramientas para una aplicación grande, a cambio de dependencias y compilación adicionales. La interfaz nativa reduce instalación para este piloto; puede sustituirse sin cambiar el motor ni los contratos.

## Estructura

`sigma_dashboard/importer.py` → `data/processed/` → API de catálogo.

`schemas.py` → `physics.py` / `thermal.py` / `simulation.py` → ejecución reproducible.

`storage.py` → SQLite de escenarios y resultados.

`app.py` → API local → `static/` → operador.

## Límites de la primera implementación

El primer motor es un modelo reducido: tracción longitudinal, batería equivalente, pared RC, tres zonas de aire, dos nodos de producto por zona, humedad, apertura, termostato y deshielo. No se presenta como CFD, gemelo digital, mapa de fabricante o modelo calibrado. Eficiencias y correlaciones simplificadas son entradas explícitas. No extrapolar a inversión o cumplimiento sanitario sin datos y validación.

El desarrollo se divide en importación y arquitectura; simulación preliminar e interfaz; pruebas físicas e integración; calibración y validación operacional pendientes de medición. El objetivo completo del prompt permanece documentado en el alcance y matriz de brechas.

## Consecuencias y próximos puntos de decisión

La simulación puede usarse sin cuentas; el mapa y el cálculo por calles utilizan servicios externos descritos en mapa-y-ruta.md. El catálogo es sensible: archivos y base excluidos del control de versiones. Escalar a múltiples usuarios requiere otra arquitectura de ejecución, autenticación y almacenamiento. Introducir mapas del fabricante exige validar cobertura y unidades, no reemplazar silenciosamente constantes.
