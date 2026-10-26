from __future__ import annotations

from bisect import bisect_right
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math

from . import MODEL_VERSION
from .schemas import SimulationConfig
from .physics import BatteryState, J_PER_KWH, road_load, charging_estimate
from .thermal import ThermalState, stable_step, AIR_DENSITY, CP_AIR


LIMITATIONS = [
    "Modelo preliminar no calibrado ni validado con operación real.",
    "Tracción con eficiencias constantes, límite combinado fuerza/potencia y reparto estático de adherencia; sin mapas torque–velocidad ni límites térmicos por duración.",
    "Frenado mecánico y ABS sin comprobación de capacidad o adherencia; el cumplimiento del perfil no valida capacidad real de frenado.",
    "Batería con OCV y resistencia constantes, SOH fijo; sin modelo térmico ni curva de fabricante.",
    "Caja RC, tres zonas, estiba homogénea y descarga proporcional; sin CFD ni conducción distribuida del producto.",
    "Volumen efectivo de aire, reparto entre zonas y propiedades de producto por calibrar; psicrometría a presión de referencia de 101325 Pa.",
    "Infiltración por renovaciones de aire ingresadas y COP por fracción de Carnot: aproximaciones por calibrar, no mapas de equipo.",
    "Condensación modelada solo en evaporador; no incluye sorción en empaques, condensación en paredes ni evaporación del producto.",
    "Clima constante y radiación solar equivalente; no se resuelve orientación ni radiación infrarroja detallada.",
    "No simula preenfriamiento conectado a red ni recogidas de mercancía. Recarga posterior es una estimación con reducción de potencia ilustrativa.",
]


def interpolate(route, times, t):
    i = max(0, min(len(times)-2, bisect_right(times, t)-1))
    a, b = route[i], route[i+1]
    w = (t-a.time_s)/(b.time_s-a.time_s)
    return a.speed_m_s+(b.speed_m_s-a.speed_m_s)*w, a.grade_pct+(b.grade_pct-a.grade_pct)*w


def run_simulation(cfg: SimulationConfig):
    times = [p.time_s for p in cfg.route]
    end = times[-1]
    if cfg.vehicle.initial_payload_kg > cfg.vehicle.payload_capacity_kg:
        raise ValueError("La carga inicial supera la capacidad útil declarada.")
    for e in cfg.deliveries:
        checks = [e.time_s, e.time_s+e.door_duration_s] + [t for t in times if e.time_s < t < e.time_s+e.door_duration_s]
        if any(interpolate(cfg.route,times,t)[0] > .05 for t in checks):
            raise ValueError("Las entregas y aperturas deben ocurrir con el vehículo detenido.")
    battery = BatteryState.create(cfg.battery)
    ref_bat = BatteryState.create(cfg.refrigerator_battery) if cfg.architecture == "independent" else None
    thermal = ThermalState.create(cfg.box)
    payload = cfg.vehicle.initial_payload_kg
    events = sorted(cfg.deliveries, key=lambda e:e.time_s)
    event_index = 0
    boundaries = sorted(set(times+[e.time_s for e in events]+[e.time_s+e.door_duration_s for e in events]))
    t = 0.0
    energy = {k: 0.0 for k in ["traction", "refrigeration", "auxiliary", "regeneration", "friction_brake", "cooling", "cooling_latent", "rolling", "aero", "grade", "inertial"]}
    distance = 0.0
    peak = {"wheel_kw": 0.0, "traction_kw": 0.0, "refrigeration_kw": 0.0, "battery_kw": 0.0}
    excursion = 0.0
    max_product = cfg.box.initial_product_c if payload>0 else None
    min_product = max_product
    max_air = max(thermal.air)
    power_fail = None
    rows = []
    delivered_thermal_j = 0.0
    water_warnings = 0
    numerical_steps = 0
    ca, ag = stable_step(cfg.box)
    initial_energy = thermal.energy(cfg.box, payload)
    outside_sensible_j = 0.0

    def record(current_t, speed, grade, road=None, ref=None, pbat=0, preg=0, ptrac=0, door=False):
        return {"time_s": round(current_t,6), "distance_km": distance/1000, "speed_kmh": speed*3.6, "grade_pct": grade, "payload_kg": payload, "traction_kw": ptrac/1000, "regeneration_kw": preg/1000, "refrigeration_kw": ref["power_dc_w"]/1000 if ref else 0, "battery_kw": pbat/1000, "soc_pct": battery.soc*100, "refrigeration_soc_pct": ref_bat.soc*100 if ref_bat else None, "air_front_c": thermal.air[0], "air_center_c": thermal.air[1], "air_rear_c": thermal.air[2], "product_core_max_c": max(thermal.core) if payload>0 else None, "product_surface_max_c": max(thermal.surface) if payload>0 else None, "wall_mean_c": sum(thermal.wall)/3, "frost_kg": thermal.frost_kg, "humidity_ratio_mean": sum(thermal.humidity)/3, "door_open": bool(door), "compressor_on": ref["compressor_on"] if ref else False, "defrost": ref["defrost"] if ref else False, "cooling_kw": ref["capacity_w"]/1000 if ref else 0, "latent_kw": ref["latent_w"]/1000 if ref else 0}

    rows.append(record(0, cfg.route[0].speed_m_s, cfg.route[0].grade_pct))
    while t < end-1e-8:
        while event_index < len(events) and events[event_index].time_s <= t+1e-8:
            old_energy = thermal.energy(cfg.box, payload)
            payload = max(0, payload-events[event_index].unload_kg)
            delivered_thermal_j += old_energy-thermal.energy(cfg.box,payload)
            event_index += 1
        next_boundary = boundaries[min(bisect_right(boundaries,t+1e-8),len(boundaries)-1)]
        product_g = payload/3*cfg.box.product_air_w_kgk
        stable = .3*min(ca/(ag+product_g), .2*cfg.box.product_cp_j_kgk/(cfg.box.product_air_w_kgk+cfg.box.product_core_w_kgk), cfg.box.wall_capacity_kj_k*1000/(4*cfg.box.ua_w_k))
        dt = min(cfg.step_s, stable, next_boundary-t, end-t)
        if dt <= 1e-9:
            raise ValueError("Paso numérico inválido.")
        numerical_steps += 1
        if numerical_steps > 300000:
            raise ValueError("Más de 300 000 pasos internos; revisar parámetros y duración.")
        v0, gr0 = interpolate(cfg.route,times,t)
        v1, gr1 = interpolate(cfg.route,times,t+dt)
        road = road_load(cfg.vehicle,cfg.weather,payload,v0,v1,(gr0+gr1)/2,dt)
        if road["force_n"] > road["force_limit_n"]+1e-6 or road["power_w"] > cfg.vehicle.max_wheel_power_kw*1000+1e-6:
            power_fail = {"time_s": t, "system": "traction", "reason": "El vehículo no sigue el perfil: límite de fuerza/adherencia o potencia en ruedas.", "requested_wheel_kw": road["power_w"]/1000, "requested_force_n": road["force_n"]}
            break
        door = any(e.time_s <= t+1e-8 < e.time_s+e.door_duration_s-1e-8 for e in events)
        candidate = deepcopy(thermal)
        ref = candidate.step(cfg.box,cfg.refrigeration,cfg.weather,payload,door,(v0+v1)/2,t,dt)
        ptrac = max(0, road["power_w"])/cfg.vehicle.drive_efficiency
        pref = ref["power_dc_w"]
        paux = cfg.vehicle.aux_kw*1000
        discharge, charge = battery.limits(dt)
        main_load = ptrac+paux+(pref if ref_bat is None else 0)
        # Below 2 m/s regenerative blending fades smoothly to zero.
        low_speed = min(1,max(0,(v0+v1)/4))
        preg = min(max(0,-road["power_w"])*cfg.vehicle.regen_efficiency*low_speed, cfg.vehicle.max_regen_kw*1000, main_load+charge)
        pbat = main_load-preg
        if pbat > discharge+1e-6:
            power_fail = {"time_s": t, "system": "battery", "reason": "Límite de potencia o reserva de la batería principal. Simulación detenida.", "requested_kw": pbat/1000, "available_kw": discharge/1000}
            break
        if ref_bat is not None and pref > ref_bat.limits(dt)[0]+1e-6:
            power_fail = {"time_s": t, "system": "refrigeration_battery", "reason": "La batería independiente no puede alimentar refrigeración. Simulación detenida."}
            break
        battery.advance(pbat,dt)
        if ref_bat is not None:
            ref_bat.advance(pref,dt)
        thermal = candidate
        outside_sensible_j += ref["external_sensible_w"]*dt
        if any(w<0 for w in thermal.humidity) or any(not math.isfinite(x) or x < -80 or x > 100 for x in thermal.air):
            raise ValueError("Estado térmico fuera del dominio del modelo; revisar parámetros y paso.")
        # Supersaturation needs surface condensation which this reduced model does not resolve.
        from .thermal import saturation_w
        if any(thermal.humidity[z] > saturation_w(thermal.air[z])*1.01 for z in range(3)):
            water_warnings += 1
        for k, val in {"traction":ptrac,"refrigeration":pref,"auxiliary":paux,"regeneration":preg,"cooling":ref["capacity_w"],"cooling_latent":ref["latent_w"], "friction_brake":max(0,-road["power_w"])-(preg/cfg.vehicle.regen_efficiency if cfg.vehicle.regen_efficiency>0 else 0)}.items():
            energy[k] += val*dt
        for k in ["rolling","aero","grade","inertial"]:
            energy[k] += road[k+"_w"]*dt
        distance += (v0+v1)/2*dt
        peak["wheel_kw"] = max(peak["wheel_kw"],road["power_w"]/1000)
        peak["traction_kw"] = max(peak["traction_kw"],ptrac/1000)
        peak["refrigeration_kw"] = max(peak["refrigeration_kw"],pref/1000)
        peak["battery_kw"] = max(peak["battery_kw"],(pbat+(pref if ref_bat else 0))/1000)
        if payload>0:
            temps = thermal.surface+thermal.core
            max_product = max(max_product,max(temps))
            min_product = min(min_product,min(temps))
            c = cfg.criteria
            if c.product_min_c is not None and c.product_max_c is not None and (min(temps)<c.product_min_c or max(temps)>c.product_max_c):
                excursion += dt
        max_air = max(max_air,max(thermal.air))
        t += dt
        rows.append(record(t,v1,gr1,road,ref,pbat,preg,ptrac,door))
    # Process deliveries at the exact final time for mass accounting.
    while event_index < len(events) and events[event_index].time_s <= t+1e-8:
        e0 = thermal.energy(cfg.box,payload)
        payload = max(0,payload-events[event_index].unload_kg)
        delivered_thermal_j += e0-thermal.energy(cfg.box,payload)
        event_index += 1
    complete = power_fail is None
    bat_terminal = battery.terminal_j+(ref_bat.terminal_j if ref_bat else 0)
    chemical = battery.chemical_j+(ref_bat.chemical_j if ref_bat else 0)
    losses = battery.loss_j+(ref_bat.loss_j if ref_bat else 0)
    bus_sum = energy["traction"]+energy["refrigeration"]+energy["auxiliary"]-energy["regeneration"]
    sensible_residual = thermal.energy(cfg.box,payload)+delivered_thermal_j-initial_energy-outside_sensible_j
    charge = charging_estimate(cfg.battery,battery.soc,cfg.charging) if complete else {"status":"No evaluable: ruta incompleta","hours":None,"grid_kwh":None}
    if ref_bat:
        charge = {"status":"Información insuficiente", "hours":None, "grid_kwh":None, "reason":"Dos baterías requieren estrategia y cargadores por rama; no se suman ventanas automáticamente."}
    eco = cfg.economics
    cost = charge["grid_kwh"]*eco.electricity_mxn_kwh if charge.get("grid_kwh") is not None else None
    diesel_cost = eco.diesel_l_route*eco.diesel_mxn_l if eco.diesel_l_route is not None and eco.baseline_scope_confirmed and complete else None
    saving = diesel_cost-cost if cost is not None and diesel_cost is not None else None
    payback = eco.incremental_capex_mxn/(saving*eco.annual_routes) if saving is not None and saving>0 and eco.annual_routes is not None and eco.incremental_capex_mxn is not None else None
    criteria = cfg.criteria
    thermal_eval = "Información insuficiente"
    if complete and criteria.confirmed and all(x is not None for x in [criteria.product_min_c,criteria.product_max_c,criteria.allowed_excursion_min]):
        thermal_eval = "Cumple criterio ingresado" if excursion/60 <= criteria.allowed_excursion_min else "No cumple criterio ingresado"
    warnings = list(LIMITATIONS)
    if water_warnings:
        warnings.append(f"Se detectó sobresaturación de aire en {water_warnings} pasos. La condensación en superficies requiere ampliar el modelo; el resultado térmico no es concluyente.")
        thermal_eval = "Información insuficiente"
    result = {"model_version":MODEL_VERSION,"created_at":datetime.now(timezone.utc).isoformat(),"input_sha256":hashlib.sha256(json.dumps(cfg.model_dump(),sort_keys=True,separators=(',',':')).encode()).hexdigest(),"complete":complete,"failure":power_fail,"validation_status":"Estimación preliminar; sin calibración operacional","limitations":warnings,
        "summary":{"duration_h":t/3600,"requested_duration_h":end/3600,"distance_km":distance/1000,"soc_final_pct":battery.soc*100,"soc_reserve_pct":cfg.battery.minimum_soc*100,"refrigeration_soc_final_pct":ref_bat.soc*100 if ref_bat else None,"battery_net_kwh":bat_terminal/J_PER_KWH,"battery_internal_loss_kwh":losses/J_PER_KWH,"battery_chemical_kwh":chemical/J_PER_KWH,"consumption_kwh_km":bat_terminal/J_PER_KWH/(distance/1000) if distance>0 else None,"product_max_c":max_product,"product_min_c":min_product,"air_max_c":max_air,"excursion_min":excursion/60,"payload_final_kg":payload,"energy_kwh":{k:v/J_PER_KWH for k,v in energy.items()},"peaks":peak},
        "viability":{"technical":"Cumple perfil bajo supuestos" if complete else "No cumple perfil solicitado","thermal":thermal_eval,"operational":"Pendiente validar ventanas, carga y servicio reales","infrastructure":"Información insuficiente" if cfg.charging.available_site_kw is None else "Revisar límite ingresado y coincidencia horaria","economic":"Información insuficiente" if saving is None else "Comparación energética parcial; TCO pendiente"},
        "charging":charge,"economics":{"grid_energy_cost_mxn":cost,"diesel_cost_mxn":diesel_cost,"energy_saving_mxn":saving,"simple_energy_payback_years":payback,"scope":"Solo energía y, si se ingresa, recuperación sobre ahorro energético; no TCO ni VAN."},
        "checks":{"bus_balance_j":bat_terminal-bus_sum,"battery_balance_j":chemical-bat_terminal-losses,"thermal_sensible_balance_j":sensible_residual,"moisture_balance_kg":thermal.moisture_residual_kg,"numerical_steps":numerical_steps,"supersaturation_steps":water_warnings},"series":rows}
    return result
