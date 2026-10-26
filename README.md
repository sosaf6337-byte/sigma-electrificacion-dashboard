# SIGMA × Tecnológico de Monterrey · Electrificación del transporte

Dashboard local en español para planear una ruta y explorar el consumo conjunto de tracción, refrigeración y batería. **Modelo preliminar sin calibración operacional.** Incluye una demostración sintética y los logotipos oficiales solicitados para el proyecto; no implica aprobación institucional.

## Ejecutar la demostración

Requiere Python 3.12. No se necesita el Excel para probar el mapa o el simulador.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m uvicorn sigma_dashboard.app:app --host 127.0.0.1 --port 8765
```

Abra http://127.0.0.1:8765/#route. En Linux/macOS use `.venv/bin/python` en lugar de `.venv\Scripts\python.exe`. En Windows también puede usar `Iniciar_dashboard.ps1` después de instalar las dependencias.

## Probar el flujo

1. Abra **Mapa y ruta**. Seleccione un escenario/camión o cree uno de ejemplo. La selección incluye caja, refrigeración, batería y carga; se editan en **Configurar escenario**.
2. Haga clic en el mapa para añadir origen, entregas y destino, o escriba coordenadas. Arrastre los marcadores, cambie el orden y añada regreso al origen si corresponde.
3. Defina minutos de parada, minutos de puerta abierta y kg descargados en cada punto. La apertura no puede superar la parada ni la descarga exceder la carga inicial.
4. Elija trazado por calles o segmentos directos, velocidad de crucero, aceleración y pendiente supuestas. **Calcular y guardar ruta** conserva el horario, geometría y procedencia con el escenario.
5. **Simular tracción y refrigeración** abre consumos separados, regeneración, batería y temperaturas. Compare ejecuciones y exporte CSV, JSON o informe HTML.

**Cargar ejemplo** utiliza puntos ilustrativos en Monterrey; no son ubicaciones operativas de SIGMA. Los valores de vehículo, equipo, clima y precios del ejemplo son supuestos de demostración. Los escenarios existentes de cada usuario se conservan localmente.

## Datos privados y servicios de mapas

Esta distribución no contiene el Excel, catálogos, identificadores reales, auditorías privadas ni bases de resultados. Los datos se guardan en `data/`, excluido de Git. Los parámetros privados de instalación se pueden guardar en `config.local.json`, también excluido.

El mapa usa teselas de OpenStreetMap con atribución. **Calcular por calles** envía las coordenadas al servicio público OSRM; no envía nombres, cantidades, Excel ni parámetros del vehículo. No introducir coordenadas confidenciales si no está autorizado su procesamiento por ese servicio. Los segmentos directos evitan el servicio de rutas, aunque la vista del mapa sigue solicitando teselas externas. No hay descarga masiva ni modo sin conexión de mapas.

El perfil OSRM es de automóvil: no garantiza restricciones de peso, altura, acceso o circulación para camiones. No incorpora tráfico en tiempo real. El perfil de velocidad de simulación es sintético y la pendiente es un supuesto constante, no elevación obtenida del mapa. El tiempo OSRM se muestra como referencia; la jornada simulada usa el perfil generado y las paradas. Si el servicio falla se conserva el trazado editable y se muestra el error; no se sustituye silenciosamente por una recta.

## Importación opcional

En **Datos de operación** puede importar un libro compatible. También puede usar:

```powershell
.\.venv\Scripts\python.exe -m sigma_dashboard.importer --source 'ruta-del-libro.xlsx'
```

El importador espera la estructura específica del cuestionario SIGMA y conserva celdas, valores originales, errores y huellas. No recalcula fórmulas ni modifica el original. `SIGMA_SOURCE_XLSX` o `config.local.json` con la clave `source_xlsx` configura la relectura. Un caso real queda incompleto hasta proporcionar sus parámetros, precios y criterios térmicos; nunca se completa con el camión sintético.

## Revisión técnica

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas son independientes del Excel privado y no llaman servicios externos. Revisan balances físicos, batería, refrigeración, restricciones, persistencia, exportaciones, conservación de distancia y acoplamiento de paradas/descargas.

- [Arquitectura](docs/ADR-001-arquitectura.md)
- [Modelo físico y límites](docs/modelo-v0.1.md)
- [Mapa, cronología y validación](docs/mapa-y-ruta.md)
- [Dependencias](docs/dependencias.md) y [avisos de terceros](THIRD_PARTY_NOTICES.md)

## Alcance de uso

La versión para visitantes se ejecuta con `sigma_dashboard.public_app:app`, en un servidor dedicado a datos sintéticos y sesiones temporales aisladas. No carga el catálogo ni admite importaciones. Consulta [demostración pública y protección de datos](docs/demo-publica.md) para límites, alojamiento, verificación y retención.

Aplicación para un equipo, escuchando en `127.0.0.1`. Compartir el código en GitHub permite revisarlo y ejecutarlo localmente; no crea una aplicación web alojada. No exponga este servidor a Internet: no tiene autenticación multiusuario, colas ni aislamiento de datos. Para un despliegue compartido se requieren esos componentes y un proveedor de mapas con capacidad y condiciones adecuadas.

Los balances numéricos prueban consistencia de las ecuaciones implementadas; no certifican viabilidad técnica, sanitaria o financiera de una operación real. La máxima fidelidad requiere perfiles medidos y mapas de fabricante, calibración y validación con jornadas independientes.
