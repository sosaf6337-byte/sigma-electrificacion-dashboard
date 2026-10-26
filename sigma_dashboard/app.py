from __future__ import annotations

import csv
import io
import json
import hashlib
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import ValidationError

from . import MODEL_VERSION
from . import storage
from .schemas import ScenarioInput, SimulationConfig, form_schema, RoutePoint
from .scenarios import demo_scenario, operational_draft
from .simulation import run_simulation, LIMITATIONS
from .importer import ingest, ROOT, SOURCE
from .reports import render_report
from .routing import RoutePlan, build_route, profile_hash
import httpx


@asynccontextmanager
async def lifespan(app):
    storage.init()
    if not storage.list_scenarios():
        storage.save_scenario(demo_scenario().model_dump())
    yield


app = FastAPI(title="SIGMA · Electrificación refrigerada", version=MODEL_VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost","127.0.0.1","testserver"])


def validation_detail(error):
    kind, ctx = error["type"], error.get("ctx", {})
    messages = {
        "missing": "Falta proporcionar este dato.",
        "float_type": "Introduce un número; el dato está vacío o no es válido.",
        "float_parsing": "Introduce un número válido.",
        "finite_number": "El número debe ser finito.",
        "greater_than": f"Debe ser mayor que {ctx.get('gt')}.",
        "greater_than_equal": f"Debe ser al menos {ctx.get('ge')}.",
        "less_than": f"Debe ser menor que {ctx.get('lt')}.",
        "less_than_equal": f"No debe superar {ctx.get('le')}.",
        "too_short": f"Se necesitan al menos {ctx.get('min_length')} elementos.",
        "too_long": f"Se permiten como máximo {ctx.get('max_length')} elementos.",
    }
    message = str(ctx['error']) if kind == 'value_error' and 'error' in ctx else messages.get(kind,"Revisa el valor y el formato de este dato.")
    return {"field":".".join(map(str,error["loc"])),"message":message}


@app.middleware("http")
async def local_only(request: Request, call_next):
    if request.method not in ("GET","HEAD","OPTIONS"):
        origin = request.headers.get("origin")
        if request.headers.get("x-sigma-request") != "local" or (origin and urlparse(origin).netloc != request.headers.get("host")):
            return Response("Solicitud local no reconocida",status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; frame-ancestors 'none'; object-src 'none'"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    return response


def catalogue():
    path = ROOT/"data"/"processed"/"catalogue.json"
    if not path.exists():
        raise HTTPException(404,"Importe el Excel para explorar los datos.")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/api/health")
def health():
    return {"status":"ok","model_version":MODEL_VERSION,"mode":"local","operational_validation":False}


@app.get("/api/schema")
def schema():
    return {"groups":form_schema(),"limitations":LIMITATIONS,"model_version":MODEL_VERSION}


@app.get("/api/catalogue")
def get_catalogue():
    return catalogue()


@app.get("/api/dictionary")
def get_dictionary():
    path = ROOT/"data"/"processed"/"dictionary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


@app.post("/api/import-source")
def import_source():
    if not SOURCE.exists():
        raise HTTPException(404,"Archivo de origen no disponible en la ruta configurada.")
    data = ingest()
    return {"source":data["source"],"summary":data["summary"]}


@app.post("/api/import-workbook")
async def import_workbook(request: Request):
    content = await request.body()
    if not content or len(content)>20_000_000:
        raise HTTPException(400,"Se requiere un XLSX de hasta 20 MB.")
    path = ROOT/"work"/"uploads"/f"{uuid4()}.xlsx"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(content)
    try:
        data = ingest(path)
    except Exception as exc:
        raise HTTPException(422, f"No se pudo importar el libro: {exc}") from exc
    return {"source":data["source"],"summary":data["summary"]}


@app.get("/api/scenarios")
def scenarios():
    return storage.list_scenarios()


@app.get("/api/scenarios/{sid}")
def scenario(sid: str):
    s = storage.get_scenario(sid)
    if s is None:
        raise HTTPException(404,"Escenario no encontrado")
    return s


@app.post("/api/scenarios")
def create_scenario(data: ScenarioInput):
    return storage.save_scenario(data.model_dump())


@app.put("/api/scenarios/{sid}")
def edit_scenario(sid: str, data: ScenarioInput):
    old = scenario(sid)
    payload = data.model_dump()
    if payload.get("route_plan") and payload["route_plan"].get("profile_sha256") != profile_hash(payload["config"]):
        payload["route_plan"] = None
    def changed_evidence(field):
        supplied = payload["evidence"].get(field)
        former = old.get("evidence",{}).get(field)
        source = supplied.get("source") if supplied and supplied != former else None
        return {"status":"assumed", "source":source or "Editado en interfaz; pendiente de verificar.", "period":None}
    # Changing an input invalidates its former provenance instead of retaining 'measured'.
    for group, values in payload["config"].items():
        prior = old["config"].get(group)
        if values != prior:
            if isinstance(values,dict):
                for k,v in values.items():
                    if not isinstance(prior,dict) or prior.get(k) != v:
                        field = f"{group}.{k}"
                        payload["evidence"][field] = changed_evidence(field)
            else:
                payload["evidence"][group] = changed_evidence(group)
    # A synthetic scenario cannot become operational through relabelling.
    if old["kind"] == "synthetic":
        payload["kind"] = "synthetic"
    return storage.save_scenario(payload,sid)


@app.post("/api/scenarios/{sid}/duplicate")
def duplicate_scenario(sid: str):
    old = scenario(sid)
    payload = {k:old[k] for k in ScenarioInput.model_fields if k in old}
    payload["name"] = (old["name"]+" · copia")[:120]
    return storage.save_scenario(payload)


@app.post("/api/pilots/{record_id}")
def create_pilot(record_id: str):
    cat = catalogue()
    record = next((r for r in cat["vehicles"] if r["record_id"]==record_id),None)
    if record is None:
        raise HTTPException(404,"Registro no encontrado")
    return storage.save_scenario(operational_draft(record,cat["source"]).model_dump())


@app.post("/api/route-csv")
async def parse_route(request: Request):
    content = await request.body()
    if len(content)>5_000_000:
        raise HTTPException(400,"CSV demasiado grande")
    try:
        reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        if not {"time_s","speed_m_s","grade_pct"}.issubset(reader.fieldnames or []):
            raise ValueError("Encabezados requeridos: time_s,speed_m_s,grade_pct")
        rows = [RoutePoint.model_validate({k:r[k] for k in ["time_s","speed_m_s","grade_pct"]}).model_dump() for r in reader]
        if len(rows)<2 or len(rows)>100000:
            raise ValueError("Se requieren de 2 a 100 000 registros.")
    except Exception as exc:
        raise HTTPException(422,str(exc)) from exc
    return {"route":rows,"sha256":hashlib.sha256(content).hexdigest(),"source":"CSV ingresado por usuario; no acredita medición."}


@app.post("/api/map-route")
async def map_route(plan: RoutePlan):
    try:
        return await build_route(plan)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    except (httpx.HTTPError, KeyError, TypeError) as exc:
        raise HTTPException(502,"El servicio de calles no respondió correctamente. Conserva tus puntos y reintenta, o elige segmentos directos explícitamente.") from exc


@app.post("/api/demo-scenario")
def new_demo():
    return storage.save_scenario(demo_scenario().model_dump())


def compact_run(payload):
    r = payload["result"]
    series = r["series"]
    stride = max(1,len(series)//900)
    sampled = series[::stride]
    if sampled and sampled[-1] is not series[-1]:
        sampled.append(series[-1])
    current = storage.get_scenario(payload["scenario"]["id"])
    return {**payload,"stale":current is not None and current["revision"] != payload["scenario"]["revision"], "result":{**r,"series":sampled,"series_count_full":len(series),"sampling_note":"Vista reducida; CSV contiene todos los pasos. Picos y métricas se calculan sobre la serie completa."}}


@app.post("/api/scenarios/{sid}/run")
def simulate(sid: str):
    s = scenario(sid)
    try:
        config = SimulationConfig.model_validate(s["config"])
    except ValidationError as exc:
        return Response(json.dumps({"detail":[validation_detail(e) for e in exc.errors()]},ensure_ascii=False),status_code=422,media_type="application/json")
    try:
        result = run_simulation(config)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    if s.get("route_plan"):
        result["limitations"].extend(s["route_plan"].get("limitations",[]))
    if s["kind"] == "synthetic":
        result["validation_status"] = "Demostración sintética · no representa operación SIGMA"
    payload = storage.save_run(s,result)
    return compact_run(payload)


@app.get("/api/runs")
def runs():
    return storage.list_runs()


@app.get("/api/runs/{rid}")
def run(rid: str):
    payload = storage.get_run(rid)
    if payload is None:
        raise HTTPException(404,"Ejecución no encontrada")
    return compact_run(payload)


@app.get("/api/runs/{rid}/export/{format}")
def export_run(rid: str, format: str):
    p = storage.get_run(rid)
    if p is None:
        raise HTTPException(404,"Ejecución no encontrada")
    name = f"sigma-{rid[:8]}"
    if format=="json":
        return Response(json.dumps(p,ensure_ascii=False,indent=2,allow_nan=False),media_type="application/json",headers={"Content-Disposition":f'attachment; filename="{name}.json"'})
    if format=="csv":
        stream = io.StringIO()
        columns = list(p["result"]["series"][0])
        writer = csv.DictWriter(stream,fieldnames=columns)
        writer.writeheader()
        writer.writerows(p["result"]["series"])
        return Response("\ufeff"+stream.getvalue(),media_type="text/csv; charset=utf-8",headers={"Content-Disposition":f'attachment; filename="{name}.csv"'})
    if format=="html":
        content = render_report(p)
        return Response(content,media_type="text/html",headers={"Content-Disposition":f'attachment; filename="{name}.html"'})
    raise HTTPException(404,"Formato no disponible")


app.mount("/static",StaticFiles(directory=ROOT/"static"),name="static")


@app.get("/")
def home():
    return FileResponse(ROOT/"static"/"index.html")
