"""Map planning -> explicit synthetic driving cycle. No measured speed/elevation."""
from __future__ import annotations

import hashlib
import json
import math
import time
import asyncio
from datetime import datetime, timezone
from typing import Literal

import httpx
from pydantic import Field, model_validator
from .schemas import StrictModel

_road_lock = asyncio.Lock()
_last_request = 0.


class Waypoint(StrictModel):
    name: str = Field(default="Parada", max_length=80)
    lat: float = Field(ge=-85, le=85)
    lng: float = Field(ge=-180, le=180)
    dwell_min: float = Field(default=0, ge=0, le=120)
    door_min: float = Field(default=0, ge=0, le=60)
    unload_kg: float = Field(default=0, ge=0, le=30000)

    @model_validator(mode="after")
    def stop_valid(self):
        if self.door_min > self.dwell_min:
            raise ValueError("El tiempo de puerta abierta no puede superar la parada.")
        if self.unload_kg and not self.door_min:
            raise ValueError("Una descarga requiere tiempo de puerta abierta.")
        return self


class RoutePlan(StrictModel):
    points: list[Waypoint] = Field(min_length=2, max_length=25)
    mode: Literal["roads", "direct"] = "roads"
    cruise_kmh: float = Field(default=35, ge=5, le=100)
    acceleration_m_s2: float = Field(default=.4, ge=.1, le=1.5)
    grade_pct: float = Field(default=0, ge=-15, le=15)


def distance_m(a, b):
    lat1, lat2 = math.radians(a.lat), math.radians(b.lat)
    dlat, dlng = lat2-lat1, math.radians(b.lng-a.lng)
    h = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlng/2)**2
    return 6371000*2*math.asin(min(1,math.sqrt(h)))


async def road_route(points):
    global _last_request
    coords = ";".join(f"{p.lng:.6f},{p.lat:.6f}" for p in points)
    url = f"https://router.project-osrm.org/route/v1/driving/{coords}"
    # Fixed origin; coordinates are validated numbers. No arbitrary upstream URLs.
    async with _road_lock:
        if time.monotonic()-_last_request < 1.1:
            raise ValueError("Espera un segundo antes de volver a calcular por calles.")
        _last_request = time.monotonic()
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            response = await client.get(url, params={"overview":"full","geometries":"geojson","steps":"false"}, headers={"User-Agent":"SigmaRouteResearch/0.2"})
            response.raise_for_status()
    data = response.json()
    if data.get("code") != "Ok" or not data.get("routes"):
        raise ValueError("No se encontró una ruta entre los puntos seleccionados.")
    r = data["routes"][0]
    if len(r["legs"]) != len(points)-1:
        raise ValueError("El proveedor devolvió tramos incompletos.")
    # Snapping far from a selected stop can silently produce a different journey.
    if any(w.get("distance",0)>500 for w in data.get("waypoints",[])):
        raise ValueError("Un punto está a más de 500 m de una calle. Acércalo al acceso vial.")
    return r


def compile_profile(plan, distances):
    if len(distances) != len(plan.points)-1:
        raise ValueError("Faltan distancias de los tramos.")
    route = [{"time_s":0., "speed_m_s":0., "grade_pct":plan.grade_pct}]
    deliveries, itinerary = [], []
    t = 0.

    def add(speed):
        route.append({"time_s":t,"speed_m_s":speed,"grade_pct":plan.grade_pct})

    def stop(p, index):
        nonlocal t
        itinerary.append({"index":index,"name":p.name,"arrival_s":t,"departure_s":t+p.dwell_min*60,"unload_kg":p.unload_kg})
        if p.door_min or p.unload_kg:
            deliveries.append({"time_s":t,"door_duration_s":p.door_min*60,"unload_kg":p.unload_kg})
        if p.dwell_min:
            t += p.dwell_min*60
            add(0.)

    stop(plan.points[0],0)
    for i,d in enumerate(distances):
        if not math.isfinite(d) or d < 10 or d > 1000000:
            raise ValueError("Cada tramo debe medir entre 10 m y 1,000 km; separa los puntos repetidos.")
        a = plan.acceleration_m_s2
        v = min(plan.cruise_kmh/3.6,math.sqrt(d*a))
        ramp = v/a
        cruise = max(0., (d-v*v/a)/v)
        t += ramp
        add(v)
        if cruise > 1e-7:
            t += cruise
            add(v)
        t += ramp
        add(0.)
        stop(plan.points[i+1],i+1)
    if t > 86400:
        raise ValueError("La ruta supera 24 horas. Divide la jornada en escenarios.")
    return route, deliveries, itinerary


async def build_route(plan):
    if plan.mode == "roads":
        r = await road_route(plan.points)
        distances = [leg["distance"] for leg in r["legs"]]
        geometry, estimated_s = r["geometry"], r["duration"]
    else:
        distances = [distance_m(a,b) for a,b in zip(plan.points,plan.points[1:])]
        geometry = {"type":"LineString","coordinates":[[p.lng,p.lat] for p in plan.points]}
        estimated_s = None
    route, deliveries, itinerary = compile_profile(plan, distances)
    profile = {"route":route,"deliveries":deliveries}
    return {**profile, "route_plan":{
        "input":plan.model_dump(),"geometry":geometry,"leg_distances_m":distances,
        "distance_km":sum(distances)/1000,"duration_s":route[-1]["time_s"],
        "provider_driving_s":estimated_s,"itinerary":itinerary,
        "provider":"OSRM driving (automóvil)" if plan.mode=="roads" else "Segmentos geodésicos directos",
        "created":datetime.now(timezone.utc).isoformat(),
        "profile_sha256":profile_hash(profile),
        "limitations":["Velocidad y aceleración sintéticas; sin tráfico ni semáforos.","Pendiente constante supuesta; sin elevación medida.","OSRM driving no comprueba restricciones de peso, altura o acceso para camiones." if plan.mode=="roads" else "Segmentos directos: no representan calles transitables."]}}


def profile_hash(config):
    # JSON round-trip ensures identical numerical representation on save.
    data = {k:[{f:float(v) for f,v in row.items()} for row in config[k]] for k in ("route","deliveries")}
    return hashlib.sha256(json.dumps(data,sort_keys=True).encode()).hexdigest()
