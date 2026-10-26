"""SI units. Powers in watts; battery current positive on discharge."""
from __future__ import annotations

import math
from dataclasses import dataclass
from .schemas import Battery, Vehicle, Weather

G = 9.80665
J_PER_KWH = 3_600_000


def road_load(vehicle: Vehicle, weather: Weather, payload: float, v0: float, v1: float, grade_pct: float, dt: float):
    v = (v0 + v1) / 2
    acceleration = (v1 - v0) / dt
    theta = math.atan(grade_pct / 100)
    mass = vehicle.ready_mass_kg + payload
    # Standstill rolling resistance does not demand power; start force is evaluated above zero.
    rolling = mass * G * vehicle.rolling_coefficient * math.cos(theta) if v > 1e-9 else 0.0
    relative = v - weather.wind_m_s
    aero = .5 * weather.air_density_kg_m3 * vehicle.drag_area_m2 * relative * abs(relative)
    grade = mass * G * math.sin(theta)
    inertial = (mass + vehicle.rotational_mass_kg) * acceleration
    force = inertial + rolling + aero + grade
    power = force * v
    force_limit = min(vehicle.max_wheel_force_n, vehicle.friction_coefficient * mass * G * math.cos(theta) * vehicle.drive_axle_fraction)
    return {"force_n": force, "power_w": power, "force_limit_n": force_limit, "acceleration_m_s2": acceleration, "rolling_w": rolling*v, "aero_w": aero*v, "grade_w": grade*v, "inertial_w": inertial*v}


@dataclass
class BatteryState:
    config: Battery
    soc: float
    terminal_j: float = 0
    chemical_j: float = 0
    loss_j: float = 0

    @classmethod
    def create(cls, config):
        return cls(config, config.initial_soc)

    @property
    def capacity_c(self):
        return self.config.capacity_kwh * J_PER_KWH * self.config.soh / self.config.nominal_voltage_v

    def limits(self, dt):
        c = self.config
        v, r = c.nominal_voltage_v, c.resistance_ohm
        i_dis = max(0, (self.soc - c.minimum_soc) * self.capacity_c / dt)
        i_ch = max(0, (c.maximum_soc - self.soc) * self.capacity_c / dt)
        if r > 0:
            i_dis = min(i_dis, v / (2*r))
        discharge = min(c.max_discharge_kw * 1000, max(0, v*i_dis-r*i_dis*i_dis))
        charge = min(c.max_charge_kw * 1000, max(0, v*i_ch+r*i_ch*i_ch))
        return discharge, charge

    def advance(self, power_w, dt):
        discharge, charge = self.limits(dt)
        if power_w > discharge + 1e-6 or -power_w > charge + 1e-6:
            raise ValueError("Demanda fuera de los límites de batería; no se recorta silenciosamente.")
        v, r = self.config.nominal_voltage_v, self.config.resistance_ohm
        discriminant = max(0, v*v-4*r*power_w)
        current = power_w/v if r == 0 else 2*power_w/(v+math.sqrt(discriminant))
        loss = current*current*r
        self.soc -= current*dt/self.capacity_c
        self.terminal_j += power_w*dt
        self.chemical_j += v*current*dt
        self.loss_j += loss*dt
        return {"current_a": current, "voltage_v": v-current*r, "loss_w": loss}


def charging_estimate(config, end_soc, charging):
    if any(x is None for x in [charging.charger_kw, charging.efficiency, charging.window_h, charging.stationary_load_kw]):
        return {"status": "Información insuficiente", "reason": "Faltan cargador, eficiencia, ventana o consumo estacionario.", "hours": None, "grid_kwh": None}
    if end_soc >= config.initial_soc - 1e-9:
        return {"status": "Sin reposición necesaria", "hours": 0, "grid_kwh": 0, "site_status": "Información insuficiente" if charging.available_site_kw is None else "Por evaluar con demanda coincidente"}
    b = BatteryState(config=config, soc=end_soc)
    seconds, grid_j = 0, 0
    while b.soc < config.initial_soc - 1e-8 and seconds < 48*3600:
        # Documented illustrative taper; replace with a manufacturer's charging curve.
        taper = 1.0 if b.soc <= .8 else max(.08, (1-b.soc)/.2)
        input_kw = charging.charger_kw
        if charging.available_site_kw is not None:
            input_kw = min(input_kw, charging.available_site_kw)
        available = input_kw*charging.efficiency*1000 - charging.stationary_load_kw*1000
        if available <= 0:
            return {"status": "No viable bajo este escenario", "reason": "La potencia no cubre los consumos estacionarios.", "hours": None, "grid_kwh": None}
        _, max_charge = b.limits(10)
        # Limit the last step to the desired initial SOC, with battery losses.
        target_i = max(0, (config.initial_soc-b.soc)*b.capacity_c/10)
        target_power = config.nominal_voltage_v*target_i+config.resistance_ohm*target_i*target_i
        accepted = min(available, max_charge*taper, target_power)
        if accepted < 1e-6:
            return {"status": "No viable bajo este escenario", "reason": "Límite de carga impide alcanzar el SOC objetivo.", "hours": None, "grid_kwh": None}
        b.advance(-accepted, 10)
        grid_j += (accepted+charging.stationary_load_kw*1000)/charging.efficiency*10
        seconds += 10
    hours = seconds/3600
    return {"status": "Cumple ventana estimada" if hours <= charging.window_h else "No cumple ventana estimada", "hours": hours, "grid_kwh": grid_j/J_PER_KWH, "site_status": "Información insuficiente" if charging.available_site_kw is None else "Límite ingresado; verificar procedencia", "assumption": "Curva de carga sintética: constante hasta 80 % y reducción posterior; no calibrada."}
