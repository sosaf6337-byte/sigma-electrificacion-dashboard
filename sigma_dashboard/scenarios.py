"""Explicit synthetic examples and empty operational drafts."""
from .schemas import ScenarioInput


def demo_scenario():
    route = [{"time_s": 0, "speed_m_s": 0, "grade_pct": 0}]
    deliveries = []
    for j in range(6):
        t = j*1800
        for offset, speed, grade in [(30,12,0),(400,12,1),(600,10,-1),(900,12,0),(1170,12,0),(1200,0,0),(1800,0,0)]:
            route.append({"time_s": t+offset, "speed_m_s": speed, "grade_pct": grade})
        deliveries.append({"time_s": t+1200, "door_duration_s": 180, "unload_kg": 250})
    cfg = {
        "vehicle": {"ready_mass_kg": 4900, "payload_capacity_kg": 2500, "initial_payload_kg": 1800, "rotational_mass_kg": 180, "drag_area_m2": 4.2, "rolling_coefficient": .008, "drive_efficiency": .88, "regen_efficiency": .65, "max_wheel_power_kw": 140, "max_wheel_force_n": 14000, "max_regen_kw": 70, "friction_coefficient": .6, "drive_axle_fraction": .6, "aux_kw": .6},
        "battery": {"capacity_kwh": 120, "nominal_voltage_v": 400, "resistance_ohm": .08, "soh": .95, "initial_soc": .9, "minimum_soc": .15, "maximum_soc": .95, "max_discharge_kw": 180, "max_charge_kw": 70},
        "refrigerator_battery": None,
        "box": {"volume_m3": 20, "surface_area_m2": 50, "ua_w_k": 25, "wall_capacity_kj_k": 500, "solar_absorptivity": .35, "sunlit_fraction": .35, "outside_h_w_m2k": 10, "initial_air_c": 3, "initial_wall_c": 3, "initial_product_c": 3, "initial_relative_humidity": .75, "product_cp_j_kgk": 3300, "product_air_w_kgk": .05, "product_core_w_kgk": .12, "door_exchange_ach": 20, "leakage_ach": .1, "mixing_kg_s": .25, "internal_heat_w": 50},
        "refrigeration": {"nominal_capacity_kw": 6, "capacity_derate_per_k": .015, "carnot_fraction": .35, "evaporator_approach_k": 8, "condenser_approach_k": 12, "on_c": 3.8, "off_c": 2.2, "evaporator_fan_kw": .15, "condenser_fan_kw": .2, "controls_kw": .03, "conversion_efficiency": .94, "coil_air_kg_s": .3, "frost_derate_per_kg": .08, "defrost_interval_min": 120, "defrost_duration_min": 5, "defrost_power_kw": 1.5, "defrost_heat_fraction": .35},
        "weather": {"ambient_c": 35, "relative_humidity": .6, "solar_w_m2": 600, "wind_m_s": 0, "air_density_kg_m3": 1.15},
        "charging": {"charger_kw": 30, "efficiency": .92, "window_h": 9, "available_site_kw": None, "stationary_load_kw": 1},
        "economics": {"electricity_mxn_kwh": 3, "diesel_mxn_l": 25, "diesel_l_route": None, "baseline_scope_confirmed": False, "annual_routes": None, "incremental_capex_mxn": None},
        "criteria": {"product_min_c": 2, "product_max_c": 4, "allowed_excursion_min": 0, "confirmed": False},
        "architecture": "shared", "route": route, "deliveries": deliveries, "step_s": 1,
    }
    evidence = {g: {"status": "assumed", "source": "Ejemplo sintético de desarrollo; no representa un vehículo ni una ruta SIGMA."} for g in cfg if g not in ("step_s",)}
    return ScenarioInput(name="Demostración · reparto de 3 horas", kind="synthetic", config=cfg, evidence=evidence, notes="Ruta, vehículo, equipo y clima sintéticos. Los precios son ilustrativos. Ningún resultado acredita viabilidad de la flota real.")


def operational_draft(record, source):
    return ScenarioInput(
        name=f"Piloto por completar · equipo {record['equipment']}", kind="operational",
        source_record=record["record_id"],
        config={"vehicle":{"payload_capacity_kg":record.get("capacity_kg")},
                "architecture":"shared","route":[],"deliveries":[],"step_s":1,
                "economics":{"baseline_scope_confirmed":False},"criteria":{"confirmed":False}},
        evidence={"vehicle.payload_capacity_kg":{"status":"provided" if record.get("capacity_kg") is not None else "pending",
                  "source":f"BD Comercial Occidente!D{record['source_row']}; capacidad actual, confirmar equivalente eléctrico. SHA256 {source['sha256']}"}},
        notes="Borrador real sin perfil temporal ni parámetros físicos. Completar precios y criterios térmicos con su fuente. No contiene valores del ejemplo sintético.")
