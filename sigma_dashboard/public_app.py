"""Public synthetic demo. Never imports the local app or workbook importer.

One process, ephemeral per-visitor SQLite files. Not an operational multiuser system.
"""
from __future__ import annotations

import csv
import io
import json
import os
import secrets
import tempfile
import threading
import time
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import MODEL_VERSION, storage
from .schemas import ScenarioInput, SimulationConfig, form_schema
from .scenarios import demo_scenario
from .simulation import run_simulation, LIMITATIONS
from .routing import RoutePlan, build_route, profile_hash
from .reports import render_report

ROOT = Path(__file__).resolve().parents[1]
COOKIE = "sigma_demo"
TTL_S = 7200
MAX_SESSIONS = 24
MAX_SCENARIOS = 6
MAX_RUNS = 3
MAX_BODY = 600_000
CSP = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"


@dataclass
class Visitor:
    db: Path
    created: float
    requests: deque = field(default_factory=deque)
    active: int = 0
    last_run: float = -100.


class DemoSessions:
    def __init__(self, root=None):
        self.root = Path(root or tempfile.mkdtemp(prefix="sigma-public-demo-"))
        self.root.mkdir(parents=True, exist_ok=True)
        self.visitors = {}
        self.lock = threading.RLock()
        self.compute = threading.Lock()
        self.new_times = deque()

    def prune(self):
        now = time.monotonic()
        for key, visitor in list(self.visitors.items()):
            if now-visitor.created >= TTL_S and not visitor.active:
                self.remove(key)

    def remove(self, key):
        visitor = self.visitors.pop(key, None)
        if visitor:
            # Only known files directly inside this instance's dedicated temp folder.
            for suffix in ("", "-journal", "-wal", "-shm"):
                path = Path(str(visitor.db)+suffix)
                if path.resolve().parent != self.root.resolve():
                    raise RuntimeError("Invalid session path")
                path.unlink(missing_ok=True)

    def create(self):
        now = time.monotonic()
        while self.new_times and now-self.new_times[0] > 60:
            self.new_times.popleft()
        if len(self.visitors) >= MAX_SESSIONS or len(self.new_times) >= 12:
            raise HTTPException(429,"La demostración está ocupada. Intenta de nuevo más tarde.")
        key = secrets.token_urlsafe(32)
        visitor = Visitor(self.root/(secrets.token_hex(16)+".sqlite3"), now)
        context = storage.request_db.set(visitor.db)
        try:
            storage.init()
            storage.save_scenario(demo_scenario().model_dump())
        finally:
            storage.request_db.reset(context)
        self.visitors[key] = visitor
        self.new_times.append(now)
        return key, visitor


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST","PUT","PATCH"):
            return await self.app(scope, receive, send)
        chunks, total = [], 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            data = message.get("body",b"")
            total += len(data)
            if total > MAX_BODY:
                return await JSONResponse({"detail":"La solicitud supera el tamaño permitido para la demo."},status_code=413)(scope,receive,send)
            chunks.append(data)
            if not message.get("more_body"):
                break
        buffered = b"".join(chunks)
        sent = False

        async def replay():
            nonlocal sent
            if not sent:
                sent = True
                return {"type":"http.request","body":buffered,"more_body":False}
            return await receive()
        await self.app(scope,replay,send)


def create_app(session_root=None):
    sessions = DemoSessions(session_root)

    @asynccontextmanager
    async def lifespan(app):
        yield
        with sessions.lock:
            for key in list(sessions.visitors):
                sessions.remove(key)

    app = FastAPI(title="SIGMA · Demo pública",docs_url=None,redoc_url=None,openapi_url=None,lifespan=lifespan)
    app.state.sessions = sessions
    hostname = os.environ.get("RENDER_EXTERNAL_HOSTNAME","")
    hosts = ["127.0.0.1","localhost","testserver"] + ([hostname] if hostname else [])
    app.add_middleware(BodyLimit)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=hosts)

    @app.middleware("http")
    async def visitor_boundary(request, call_next):
        if request.url.hostname not in hosts:
            return JSONResponse({"detail":"Host no autorizado."},status_code=400)
        path = request.url.path
        is_api = path.startswith("/api/")
        visitor = None
        context = None
        key = request.cookies.get(COOKIE)
        fresh = False
        try:
            if request.method not in ("GET","HEAD"):
                origin = urlparse(request.headers.get("origin",""))
                if request.headers.get("x-sigma-request") != "local" or origin.netloc != request.headers.get("host") or origin.scheme not in ("http","https"):
                    return JSONResponse({"detail":"Solicitud de otro origen rechazada."},status_code=403)
            if is_api and path != "/api/health":
                if path.startswith(("/api/import","/api/pilots")) or path in ("/api/catalogue","/api/dictionary","/api/route-csv"):
                    return JSONResponse({"detail":"Esta demostración no permite consultar ni importar datos operativos."},status_code=403)
                with sessions.lock:
                    sessions.prune()
                    visitor = sessions.visitors.get(key)
                    if path == "/api/session" and request.method == "GET" and not visitor:
                        key, visitor = sessions.create()
                        fresh = True
                    if not visitor or time.monotonic()-visitor.created >= TTL_S:
                        return JSONResponse({"detail":"La sesión de prueba terminó. Recarga la página para iniciar una nueva."},status_code=401)
                    now = time.monotonic()
                    while visitor.requests and now-visitor.requests[0] > 60:
                        visitor.requests.popleft()
                    if len(visitor.requests) >= 90:
                        return JSONResponse({"detail":"Demasiadas solicitudes. Espera un minuto."},status_code=429)
                    visitor.requests.append(now)
                    visitor.active += 1
                request.state.visitor = visitor
                context = storage.request_db.set(visitor.db)
            response = await call_next(request)
            response.headers.update({"X-Content-Type-Options":"nosniff","Referrer-Policy":"strict-origin-when-cross-origin","Content-Security-Policy":CSP,"X-Frame-Options":"DENY","X-Robots-Tag":"noindex, nofollow","Cache-Control":"no-store" if is_api else "public, max-age=300"})
            if fresh:
                response.set_cookie(COOKIE,key,max_age=TTL_S,httponly=True,secure=request.url.hostname not in ("localhost","127.0.0.1","testserver"),samesite="strict",path="/")
            return response
        except HTTPException as exc:
            return JSONResponse({"detail":exc.detail},status_code=exc.status_code)
        finally:
            if context is not None:
                storage.request_db.reset(context)
                with sessions.lock:
                    visitor.active -= 1

    def scenario(sid):
        value = storage.get_scenario(sid)
        if value is None:
            raise HTTPException(404,"Escenario no encontrado en esta sesión.")
        return value

    def clean_scenario(data):
        if data.kind != "synthetic" or data.source_record:
            raise HTTPException(422,"La versión pública solo admite escenarios sintéticos, sin registros operativos.")
        payload = data.model_dump()
        payload["evidence"] = {k:{"status":"assumed","source":"Entrada de demostración; no verificada contra operación real."} for k in data.config}
        try:
            if payload.get("route_plan") and payload["route_plan"].get("profile_sha256") != profile_hash(payload["config"]):
                payload["route_plan"] = None
        except (KeyError,ValueError,TypeError,AttributeError) as exc:
            raise HTTPException(422,"El perfil de ruta no tiene un formato válido.") from exc
        return payload

    def check_capacity():
        if len(storage.list_scenarios()) >= MAX_SCENARIOS:
            raise HTTPException(429,"La demo admite hasta 6 escenarios por sesión.")

    def compact(payload):
        result = payload["result"]
        series = result["series"]
        sampled = series[::max(1,len(series)//900)]
        if sampled and sampled[-1] is not series[-1]:
            sampled.append(series[-1])
        current = storage.get_scenario(payload["scenario"]["id"])
        return {**payload,"stale":current is not None and current["revision"]!=payload["scenario"]["revision"],"result":{**result,"series":sampled,"series_count_full":len(series),"sampling_note":"Vista reducida; CSV conserva todos los pasos. Parámetros sintéticos sin validación operacional."}}

    @app.get("/api/health")
    def health():
        return {"status":"ok","mode":"public_demo","model_version":MODEL_VERSION,"release":os.environ.get("RENDER_GIT_COMMIT"),"private_data_enabled":False,"session_storage":"ephemeral","operational_validation":False}

    @app.get("/api/session")
    def session():
        return {"mode":"public_demo","expires_in_s":TTL_S,"max_scenarios":MAX_SCENARIOS,"max_runs":MAX_RUNS}

    @app.get("/api/schema")
    def schema():
        return {"groups":form_schema(),"limitations":LIMITATIONS,"model_version":MODEL_VERSION}

    @app.get("/api/scenarios")
    def scenarios():
        return storage.list_scenarios()

    @app.get("/api/scenarios/{sid}")
    def get_scenario(sid:str):
        return scenario(sid)

    @app.post("/api/scenarios")
    def create_scenario(data:ScenarioInput):
        check_capacity()
        return storage.save_scenario(clean_scenario(data))

    @app.put("/api/scenarios/{sid}")
    def edit_scenario(sid:str,data:ScenarioInput):
        scenario(sid)
        return storage.save_scenario(clean_scenario(data),sid)

    @app.post("/api/scenarios/{sid}/duplicate")
    def duplicate(sid:str):
        check_capacity()
        old = scenario(sid)
        payload = {k:old[k] for k in ScenarioInput.model_fields if k in old}
        payload["name"] = (old["name"]+" · copia")[:120]
        return storage.save_scenario(payload)

    @app.post("/api/demo-scenario")
    def new_demo():
        check_capacity()
        new = demo_scenario().model_dump()
        new["name"] = "Camión de ejemplo · ruta por definir"
        return storage.save_scenario(new)

    @app.post("/api/map-route")
    async def map_route(plan:RoutePlan):
        try:
            result = await build_route(plan)
            if result["route_plan"]["duration_s"] > 8*3600:
                raise ValueError("La demostración pública admite jornadas de hasta 8 horas.")
            return result
        except ValueError as exc:
            raise HTTPException(422,str(exc)) from exc
        except (httpx.HTTPError,KeyError,TypeError) as exc:
            raise HTTPException(502,"El servicio de calles no respondió. Reintenta o selecciona segmentos directos.") from exc

    @app.post("/api/scenarios/{sid}/run")
    def simulate(sid:str,request:Request):
        s = scenario(sid)
        if len(storage.list_runs()) >= MAX_RUNS:
            raise HTTPException(429,"La sesión permite 3 ejecuciones. Puedes compararlas y descargarlas; inicia otra sesión de prueba en una ventana privada para seguir explorando.")
        visitor = request.state.visitor
        if time.monotonic()-visitor.last_run < 10 or not sessions.compute.acquire(blocking=False):
            raise HTTPException(429,"Hay un cálculo en curso o recién terminado. Espera unos segundos y vuelve a intentar.")
        visitor.last_run = time.monotonic()
        try:
            config = SimulationConfig.model_validate(s["config"])
            if config.route[-1].time_s > 8*3600 or len(config.route)>3000:
                raise ValueError("La demo admite hasta 8 horas y 3,000 puntos del perfil.")
            result = run_simulation(config,max_steps=20000,max_runtime_s=20)
            result["validation_status"] = "Demostración pública sintética · no representa operación SIGMA"
            if s.get("route_plan"):
                result["limitations"].extend(str(x)[:500] for x in s["route_plan"].get("limitations",[])[:10])
            return compact(storage.save_run(s,result))
        except ValidationError as exc:
            raise HTTPException(422,[{"field":".".join(map(str,e["loc"])),"message":str(e["msg"])} for e in exc.errors()]) from exc
        except (ValueError,OverflowError,ZeroDivisionError) as exc:
            raise HTTPException(422,str(exc)) from exc
        finally:
            sessions.compute.release()

    @app.get("/api/runs")
    def runs():
        return storage.list_runs()

    @app.get("/api/runs/{rid}")
    def run(rid:str):
        payload = storage.get_run(rid)
        if payload is None:
            raise HTTPException(404,"Ejecución no encontrada en esta sesión.")
        return compact(payload)

    @app.get("/api/runs/{rid}/export/{format}")
    def export(rid:str,format:str):
        payload = storage.get_run(rid)
        if payload is None:
            raise HTTPException(404,"Ejecución no encontrada en esta sesión.")
        if format == "json":
            content, mime = json.dumps(payload,ensure_ascii=False,allow_nan=False), "application/json"
        elif format == "html":
            content, mime = render_report(payload), "text/html"
        elif format == "csv":
            stream = io.StringIO()
            rows = payload["result"]["series"]
            writer = csv.DictWriter(stream,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            content, mime = "\ufeff"+stream.getvalue(), "text/csv"
        else:
            raise HTTPException(404,"Formato no disponible.")
        return Response(content,media_type=mime,headers={"Content-Disposition":f'attachment; filename="sigma-demo-{rid[:8]}.{format}"'})

    app.mount("/static",StaticFiles(directory=ROOT/"static"),name="static")

    @app.get("/")
    def home():
        return FileResponse(ROOT/"static"/"index.html")

    @app.get("/robots.txt")
    def robots():
        return Response("User-agent: *\nDisallow: /\n",media_type="text/plain")

    return app


app = create_app()
