"""Reduced RC/three-zone model. Explicit parameters, no manufactured calibration."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from .schemas import Box, Refrigeration, Weather

CP_AIR = 1006.0
LV = 2_500_000.0
LF = 334_000.0
AIR_DENSITY = 1.2


def saturation_w(t_c):
    # Buck-type approximation, liquid above 0 C and ice below. 101325 Pa reference.
    if t_c >= 0:
        ps = 611.21*math.exp((18.678-t_c/234.5)*(t_c/(257.14+t_c)))
    else:
        ps = 611.15*math.exp((23.036-t_c/333.7)*(t_c/(279.82+t_c)))
    return .62198*ps/(101325-ps)


def humidity_ratio(t_c, relative_humidity):
    ws = saturation_w(t_c)
    ps = 101325*ws/(.62198+ws)
    pv = ps*relative_humidity
    return .62198*pv/(101325-pv)


@dataclass
class ThermalState:
    air: list[float]
    wall: list[float]
    surface: list[float]
    core: list[float]
    humidity: list[float]
    frost_kg: float = 0
    compressor_on: bool = False
    sensible_residual_j: float = 0
    moisture_residual_kg: float = 0
    max_sensible_residual_j: float = 0

    @classmethod
    def create(cls, box):
        return cls([box.initial_air_c]*3, [box.initial_wall_c]*3, [box.initial_product_c]*3, [box.initial_product_c]*3, [humidity_ratio(box.initial_air_c, box.initial_relative_humidity)]*3)

    def energy(self, box, payload):
        ca = AIR_DENSITY*box.volume_m3/3*CP_AIR
        cw = box.wall_capacity_kj_k*1000/3
        cp = payload/3*box.product_cp_j_kgk
        return sum(ca*self.air[z]+cw*self.wall[z]+.2*cp*self.surface[z]+.8*cp*self.core[z] for z in range(3))

    def step(self, box: Box, fridge: Refrigeration, weather: Weather, payload, door, speed, t, dt):
        before = self.energy(box, payload)
        ca_mass = AIR_DENSITY*box.volume_m3/3
        moisture_before = sum(self.humidity)*ca_mass
        ca, cw = ca_mass*CP_AIR, box.wall_capacity_kj_k*1000/3
        cp = payload/3*box.product_cp_j_kgk
        ua = box.ua_w_k/3
        # Two equal resistances around a wall capacity: steady-state conductance is UA.
        go = gi = 2*ua
        ho = box.outside_h_w_m2k + 2*abs(speed-weather.wind_m_s)**.5
        sol_air = weather.ambient_c + box.solar_absorptivity*box.sunlit_fraction*weather.solar_w_m2/ho
        total_exchange = AIR_DENSITY*box.volume_m3*(box.leakage_ach + (box.door_exchange_ach if door else 0))/3600
        # Door is at the rear. Background leaks are distributed; door exchange is rear weighted.
        weights = [.1, .2, .7] if door else [1/3]*3
        infil = [total_exchange*x for x in weights]
        outside_w = humidity_ratio(weather.ambient_c, weather.relative_humidity)
        ret = sum(self.air)/3
        if ret >= fridge.on_c:
            self.compressor_on = True
        elif ret <= fridge.off_c:
            self.compressor_on = False
        interval = fridge.defrost_interval_min*60
        defrost = bool(interval > 0 and t >= interval and t % interval < fridge.defrost_duration_min*60)
        active = self.compressor_on and not defrost
        # Evaporation and condensation approximations, not a measured refrigerant map.
        tevap = ret-fridge.evaporator_approach_k
        tcond = weather.ambient_c+fridge.condenser_approach_k
        lift = max(3, tcond-tevap)
        cop = fridge.carnot_fraction*(tevap+273.15)/lift
        cop = max(.2, cop)
        capacity = fridge.nominal_capacity_kw*1000*max(.25, 1-fridge.capacity_derate_per_k*max(0, weather.ambient_c-30))*max(.25, 1-fridge.frost_derate_per_kg*self.frost_kg) if active else 0
        fan_w = 0 if defrost else fridge.evaporator_fan_kw*1000
        cond_w = fridge.condenser_fan_kw*1000 if active else 0
        defrost_w = fridge.defrost_power_kw*1000 if defrost else 0
        electrical = capacity/cop + fan_w + cond_w + fridge.controls_kw*1000 + defrost_w
        latent_per_kg = LV + (LF if tevap < 0 else 0)
        potential_water = fridge.coil_air_kg_s*max(0, sum(self.humidity)/3-saturation_w(tevap)) if active else 0
        available_water = sum(self.humidity)*ca_mass/dt
        remove = min(potential_water, available_water, .65*capacity/latent_per_kg)
        latent = remove*latent_per_kg
        sensible = capacity-latent
        if tevap < 0:
            self.frost_kg += remove*dt
        if defrost:
            self.frost_kg = max(0, self.frost_kg-defrost_w*(1-fridge.defrost_heat_fraction)*dt/LF)
        supply = [.45, .33, .22]
        da, dwall, ds, dc, dh = [], [], [], [], []
        external_sensible_w = 0
        moisture_net = 0
        for z in range(3):
            wall_outer = go*(sol_air-self.wall[z])
            wall_inner = gi*(self.wall[z]-self.air[z])
            p_to_air = payload/3*box.product_air_w_kgk*(self.surface[z]-self.air[z])
            core_to_s = payload/3*box.product_core_w_kgk*(self.core[z]-self.surface[z])
            qinf = infil[z]*CP_AIR*(weather.ambient_c-self.air[z])
            qinternal = (box.internal_heat_w+fan_w+defrost_w*fridge.defrost_heat_fraction)/3
            # Pairwise adjacent mixing is anti-symmetric, preserving energy and water.
            neighbours = [j for j in [z-1,z+1] if 0 <= j < 3]
            mix = sum(box.mixing_kg_s*CP_AIR*(self.air[j]-self.air[z]) for j in neighbours)
            mixw = sum(box.mixing_kg_s*(self.humidity[j]-self.humidity[z]) for j in neighbours)
            water_share = remove*(self.humidity[z]/sum(self.humidity) if sum(self.humidity)>0 else 1/3)
            netw = infil[z]*(outside_w-self.humidity[z])+mixw-water_share
            qair = wall_inner+p_to_air+qinf+qinternal+mix-sensible*supply[z]
            da.append(qair/ca)
            dwall.append((wall_outer-wall_inner)/cw)
            ds.append((-p_to_air+core_to_s)/(.2*cp) if cp > 0 else 0)
            dc.append(-core_to_s/(.8*cp) if cp > 0 else 0)
            dh.append(netw/ca_mass)
            external_sensible_w += wall_outer+qinf+qinternal-sensible*supply[z]
            moisture_net += infil[z]*(outside_w-self.humidity[z])-water_share
        for z in range(3):
            self.air[z] += da[z]*dt
            self.wall[z] += dwall[z]*dt
            self.surface[z] += ds[z]*dt
            self.core[z] += dc[z]*dt
            self.humidity[z] += dh[z]*dt
        after = self.energy(box, payload)
        error = after-before-external_sensible_w*dt
        self.sensible_residual_j += error
        self.max_sensible_residual_j = max(self.max_sensible_residual_j, abs(error))
        self.moisture_residual_kg += sum(self.humidity)*ca_mass-moisture_before-moisture_net*dt
        return {"power_dc_w": electrical/fridge.conversion_efficiency, "capacity_w": capacity, "sensible_w": sensible, "latent_w": latent, "cop_compressor": cop if active else None, "compressor_on": active, "defrost": defrost, "infiltration_sensible_w": sum(infil[z]*CP_AIR*(weather.ambient_c-self.air[z]) for z in range(3)), "external_sensible_w": external_sensible_w}


def stable_step(box: Box):
    ca = AIR_DENSITY*box.volume_m3/3*CP_AIR
    air_g = 2*box.ua_w_k/3+2*box.mixing_kg_s*CP_AIR+AIR_DENSITY*box.volume_m3*(box.door_exchange_ach+box.leakage_ach)/3600*CP_AIR
    # Product term is added by the caller because payload changes.
    return ca, air_g
