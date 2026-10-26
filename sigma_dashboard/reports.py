"""Printable Spanish report with a separate technical audit appendix."""
import html
import json
import base64
from pathlib import Path


def brand_image(filename, mime):
    path = Path(__file__).resolve().parents[1] / "static" / "assets" / "brand" / filename
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


def render_report(payload):
    e = html.escape
    result, scenario = payload["result"], payload["scenario"]
    sigma_logo = brand_image("sigma-alimentos.png", "image/png")
    tec_logo = brand_image("tecnologico-de-monterrey.svg", "image/svg+xml")
    summary, energy = result["summary"], result["summary"]["energy_kwh"]

    def value(v, unit=""):
        if v is None:
            return "Sin dato / no evaluable"
        return f"{v:,.2f} {unit}".strip() if isinstance(v, (int, float)) else str(v)

    def table(rows):
        return '<table><tbody>'+''.join(f'<tr><th scope="row">{e(label)}</th><td>{e(value(v,unit))}</td></tr>' for label,v,unit in rows)+'</tbody></table>'

    metrics = [
        ("Recorrido simulado",summary["distance_km"],"km"),
        ("Duración simulada",summary["duration_h"],"h"),
        ("Energía neta en terminales de baterías",summary["battery_net_kwh"],"kWh"),
        ("Tracción, antes de regeneración",energy["traction"],"kWh eléctricos"),
        ("Refrigeración",energy["refrigeration"],"kWh eléctricos"),
        ("Otros auxiliares",energy["auxiliary"],"kWh eléctricos"),
        ("Regeneración recuperada",energy["regeneration"],"kWh eléctricos"),
        ("Pérdidas internas de baterías",summary["battery_internal_loss_kwh"],"kWh"),
        ("SOC final de batería principal",summary["soc_final_pct"],"%"),
        ("Reserva configurada",summary["soc_reserve_pct"],"%"),
        ("Temperatura máxima del producto",summary["product_max_c"],"°C"),
        ("Temperatura mínima del producto",summary["product_min_c"],"°C"),
        ("Tiempo fuera de límites ingresados",summary["excursion_min"],"min"),
        ("Mercancía restante",summary["payload_final_kg"],"kg"),
    ]
    names = {"technical":"Perfil técnico", "thermal":"Conservación térmica", "operational":"Operación", "infrastructure":"Infraestructura", "economic":"Economía"}
    charging, eco = result["charging"], result["economics"]
    recharge = [("Estado de recarga",charging["status"],""),("Duración estimada de recarga",charging.get("hours"),"h"),("Energía de red estimada",charging.get("grid_kwh"),"kWh"),("Costo de electricidad",eco["grid_energy_cost_mxn"],"MXN"),("Costo diésel comparable",eco["diesel_cost_mxn"],"MXN"),("Ahorro energético por ruta",eco["energy_saving_mxn"],"MXN")]
    failure = f'<p class="warning">Ruta incompleta: {e(result["failure"]["reason"])}. Los indicadores representan solo el tramo simulado.</p>' if result["failure"] else ''
    limitations = '<ul>'+''.join(f'<li>{e(item)}</li>' for item in result["limitations"])+ '</ul>'
    appendix = e(json.dumps({"inputs_and_provenance":scenario,"numerical_checks":result["checks"],"input_sha256":result["input_sha256"]},ensure_ascii=False,indent=2))
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Informe SIGMA · {e(scenario["name"])}</title>
<style>body{{font:15px/1.6 system-ui;max-width:980px;margin:40px auto;color:#172b3a;padding:24px}}h1{{font-size:30px;line-height:1.2}}h2{{margin-top:32px;font-size:21px}}p{{color:#526473}}table{{width:100%;border-collapse:collapse}}th,td{{padding:10px 12px;border-bottom:1px solid #dce3e9;text-align:left;vertical-align:top}}th{{width:60%;font-weight:500}}td{{font-variant-numeric:tabular-nums}}.warning{{background:#fff5df;border:1px solid #ebd7ae;padding:15px;color:#74500c}}pre{{font:11px/1.5 monospace;white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px}}li{{margin:8px 0}}.report-brand{{display:flex;align-items:center;gap:28px;padding-bottom:24px;border-bottom:4px solid #0039a6}}.report-brand img{{object-fit:contain;height:auto}}.sigma-logo{{width:120px}}.tec-logo{{width:230px}}.report-brand span{{color:#526473;font-size:24px}}.report-project{{color:#0039a6}}h1{{color:#041e42}}h2{{color:#003087}}@media(max-width:500px){{.report-brand{{gap:14px}}.sigma-logo{{width:84px}}.tec-logo{{width:148px}}body{{padding:16px}}}}@media print{{body{{margin:0;padding:0}}tr{{break-inside:avoid}}h2{{break-after:avoid}}}}</style></head><body>
<header class="report-brand"><img class="sigma-logo" src="{sigma_logo}" alt="Sigma Alimentos"><span aria-hidden="true">×</span><img class="tec-logo" src="{tec_logo}" alt="Tecnológico de Monterrey"></header><p class="report-project">SIGMA × Tecnológico de Monterrey · Electrificación de transporte refrigerado</p><h1>{e(scenario["name"])}</h1><p>Modelo {e(result["model_version"])} · Revisión {scenario["revision"]} · Ejecución {e(payload["id"])}</p><p>Fecha de cálculo UTC: {e(result["created_at"])}</p>
<p class="warning">{e(result["validation_status"])}. Modelo preliminar: no constituye un dictamen operativo, sanitario o de inversión.</p>{failure}
<h2>Evaluación por dimensión</h2>{table([(names[k],v,"") for k,v in result["viability"].items()])}
<h2>Energía y conservación de la carga</h2>{table(metrics)}<p>La temperatura de producto considera superficie y centro de las zonas. La ausencia de excursiones solo aplica a los límites ingresados y no sustituye la validación térmica.</p>
<h2>Recarga y comparación energética</h2>{table(recharge)}<p>{e(charging.get("assumption") or charging.get("reason") or "Recarga estimada bajo los parámetros ingresados.")}</p><p>{e(eco["scope"])}</p>
<h2>Supuestos y límites de interpretación</h2>{limitations}
<h2>Anexo técnico: entradas y trazabilidad</h2><p>Se conserva la configuración de esta ejecución. Los cambios posteriores del escenario no modifican este informe.</p><pre>{appendix}</pre></body></html>'''
