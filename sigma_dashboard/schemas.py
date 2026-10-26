from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Vehicle(StrictModel):
    ready_mass_kg: float = Field(gt=0, le=40000, title="Masa lista para operar", description="kg · Incluye batería, caja y refrigeración; excluye mercancía.")
    payload_capacity_kg: float = Field(gt=0, le=30000, title="Capacidad útil", description="kg · Confirmar después de instalar caja y batería.")
    initial_payload_kg: float = Field(ge=0, le=30000, title="Mercancía inicial", description="kg")
    rotational_mass_kg: float = Field(ge=0, le=4000, title="Inercia rotativa equivalente", description="kg")
    drag_area_m2: float = Field(gt=0, le=20, title="Producto Cd × área frontal", description="m² · Incluye configuración de la caja.")
    rolling_coefficient: float = Field(ge=0, le=.05, title="Coeficiente de rodadura", description="adimensional")
    drive_efficiency: float = Field(gt=.1, le=1, title="Eficiencia de propulsión", description="fracción · Ruedas / bus DC. Aproximación constante.")
    regen_efficiency: float = Field(ge=0, le=1, title="Eficiencia de regeneración", description="fracción · Bus DC / ruedas.")
    max_wheel_power_kw: float = Field(gt=0, le=1000, title="Potencia máxima en ruedas", description="kW mecánicos · Límite simplificado.")
    max_wheel_force_n: float = Field(gt=0, le=100000, title="Fuerza máxima en ruedas", description="N · Torque, transmisión y radio equivalente.")
    max_regen_kw: float = Field(ge=0, le=500, title="Regeneración máxima DC", description="kW eléctricos")
    friction_coefficient: float = Field(gt=0, le=1.5, title="Adherencia neumático–pavimento", description="adimensional")
    drive_axle_fraction: float = Field(gt=0, le=1, title="Fracción de peso en eje motriz", description="fracción · Aproximación estática.")
    aux_kw: float = Field(ge=0, le=20, title="Otros auxiliares", description="kW · Excluye refrigeración de mercancía.")


class Battery(StrictModel):
    capacity_kwh: float = Field(gt=0, le=1000, title="Capacidad nominal", description="kWh")
    nominal_voltage_v: float = Field(gt=24, le=1200, title="Tensión equivalente", description="V · OCV constante en este nivel de modelo.")
    resistance_ohm: float = Field(ge=0, le=1, title="Resistencia interna", description="Ω · Equivalente del paquete.")
    soh: float = Field(gt=0, le=1, title="Estado de salud", description="fracción de capacidad nominal")
    initial_soc: float = Field(ge=0, le=1, title="SOC inicial", description="fracción")
    minimum_soc: float = Field(ge=0, lt=1, title="Reserva mínima de SOC", description="fracción")
    maximum_soc: float = Field(gt=0, le=1, title="SOC máximo", description="fracción")
    max_discharge_kw: float = Field(gt=0, le=1000, title="Descarga máxima", description="kW en terminales")
    max_charge_kw: float = Field(ge=0, le=1000, title="Carga máxima", description="kW en terminales")

    @model_validator(mode="after")
    def ordered_soc(self):
        if not self.minimum_soc < self.maximum_soc or not self.minimum_soc <= self.initial_soc <= self.maximum_soc:
            raise ValueError("SOC: mínimo < máximo e inicial dentro de ambos límites.")
        return self


class Box(StrictModel):
    volume_m3: float = Field(gt=1, le=120, title="Volumen interior", description="m³")
    surface_area_m2: float = Field(gt=1, le=250, title="Superficie envolvente", description="m²")
    ua_w_k: float = Field(gt=0, le=500, title="Conductancia total UA", description="W/K · Incluye puentes térmicos.")
    wall_capacity_kj_k: float = Field(gt=10, le=10000, title="Capacidad térmica de paneles", description="kJ/K")
    solar_absorptivity: float = Field(ge=0, le=1, title="Absorptividad solar", description="fracción")
    sunlit_fraction: float = Field(ge=0, le=1, title="Fracción equivalente expuesta al sol", description="fracción · Aproximación de orientación.")
    outside_h_w_m2k: float = Field(gt=1, le=150, title="Convección exterior de referencia", description="W/(m²·K)")
    initial_air_c: float = Field(ge=-20, le=50, title="Temperatura inicial del aire", description="°C")
    initial_wall_c: float = Field(ge=-20, le=60, title="Temperatura inicial de paneles", description="°C")
    initial_product_c: float = Field(ge=-5, le=40, title="Temperatura inicial del producto", description="°C · Modelo de producto sin cambio de fase.")
    initial_relative_humidity: float = Field(ge=.01, le=1, title="Humedad relativa inicial", description="fracción")
    product_cp_j_kgk: float = Field(gt=500, le=5000, title="Calor específico del producto", description="J/(kg·K)")
    product_air_w_kgk: float = Field(gt=0, le=10, title="Acoplamiento aire–producto por kg", description="W/(kg·K) · Parámetro efectivo de empaque/estiba.")
    product_core_w_kgk: float = Field(gt=0, le=10, title="Acoplamiento superficie–centro por kg", description="W/(kg·K)")
    door_exchange_ach: float = Field(ge=0, le=120, title="Intercambio con puerta abierta", description="renovaciones/h · Parámetro efectivo por calibrar.")
    leakage_ach: float = Field(ge=0, le=10, title="Fugas con puerta cerrada", description="renovaciones/h")
    mixing_kg_s: float = Field(ge=0, le=5, title="Mezcla entre zonas", description="kg/s de aire seco")
    internal_heat_w: float = Field(ge=0, le=5000, title="Calor interior adicional", description="W · Luces/personas; excluye ventilador evaporador.")


class Refrigeration(StrictModel):
    nominal_capacity_kw: float = Field(gt=0, le=60, title="Capacidad frigorífica de referencia", description="kW térmicos, a 30 °C exteriores")
    capacity_derate_per_k: float = Field(ge=0, le=.03, title="Reducción de capacidad por calor", description="fracción/K por encima de 30 °C · Supuesto lineal.")
    carnot_fraction: float = Field(gt=.05, le=.7, title="Fracción del COP de Carnot", description="fracción · Aproximación; sustituir por mapas medidos.")
    evaporator_approach_k: float = Field(gt=0, le=25, title="Diferencia aire–evaporación", description="K")
    condenser_approach_k: float = Field(gt=0, le=30, title="Diferencia condensación–ambiente", description="K")
    on_c: float = Field(ge=-10, le=15, title="Encendido por temperatura de retorno", description="°C · Parámetro de control, distinto del límite del producto.")
    off_c: float = Field(ge=-15, le=15, title="Apagado por temperatura de retorno", description="°C")
    evaporator_fan_kw: float = Field(ge=0, le=3, title="Ventilador evaporador", description="kW eléctricos; calor liberado dentro de la caja.")
    condenser_fan_kw: float = Field(ge=0, le=3, title="Ventilador condensador", description="kW eléctricos")
    controls_kw: float = Field(ge=0, le=1, title="Controles del equipo", description="kW eléctricos")
    conversion_efficiency: float = Field(gt=.5, le=1, title="Eficiencia alimentación frigorífica", description="fracción · Equipo / bus DC.")
    coil_air_kg_s: float = Field(gt=0, le=5, title="Caudal efectivo evaporador", description="kg/s de aire seco")
    frost_derate_per_kg: float = Field(ge=0, le=1, title="Pérdida de capacidad por escarcha", description="fracción/kg · Parámetro por calibrar.")
    defrost_interval_min: float = Field(ge=0, le=1440, title="Intervalo de deshielo", description="min · 0 desactiva el deshielo programado.")
    defrost_duration_min: float = Field(ge=0, le=30, title="Duración de deshielo", description="min")
    defrost_power_kw: float = Field(ge=0, le=15, title="Potencia de deshielo eléctrico", description="kW")
    defrost_heat_fraction: float = Field(ge=0, le=1, title="Fracción de deshielo hacia la caja", description="fracción · Resto destinado a fusión/pérdidas.")

    @model_validator(mode="after")
    def control_order(self):
        if self.off_c >= self.on_c:
            raise ValueError("La temperatura de apagado debe ser menor a la de encendido.")
        return self


class Weather(StrictModel):
    ambient_c: float = Field(ge=-10, le=50, title="Temperatura exterior", description="°C")
    relative_humidity: float = Field(ge=.01, le=1, title="Humedad relativa exterior", description="fracción")
    solar_w_m2: float = Field(ge=0, le=1400, title="Irradiancia solar", description="W/m²")
    wind_m_s: float = Field(ge=-30, le=30, title="Viento longitudinal", description="m/s · Positivo a favor de la marcha.")
    air_density_kg_m3: float = Field(gt=.5, le=1.6, title="Densidad del aire", description="kg/m³")


class Charging(StrictModel):
    charger_kw: float | None = Field(default=None, gt=0, le=1000, title="Potencia AC del cargador", description="kW · Vacío: recarga no evaluable.")
    efficiency: float | None = Field(default=None, gt=.5, le=1, title="Eficiencia de recarga", description="fracción")
    window_h: float | None = Field(default=None, gt=0, le=48, title="Ventana de recarga", description="h")
    available_site_kw: float | None = Field(default=None, ge=0, le=10000, title="Potencia adicional verificada", description="kW · No derivada del pico histórico.")
    stationary_load_kw: float | None = Field(default=None, ge=0, le=100, title="Consumo simultáneo estacionario", description="kW DC · Incluir frío/preenfriamiento cuando aplique.")


class Economics(StrictModel):
    electricity_mxn_kwh: float = Field(ge=0, le=100, title="Precio de electricidad", description="MXN/kWh · Tarifa por proporcionar; excluye demanda.")
    diesel_mxn_l: float = Field(ge=0, le=100, title="Precio de diésel", description="MXN/L · Precio por proporcionar.")
    diesel_l_route: float | None = Field(default=None, ge=0, le=1000, title="Diésel por ruta comparable", description="L · Debe incluir refrigeración si se compara con ambas cargas.")
    baseline_scope_confirmed: bool = Field(default=False, title="Línea base con alcance comparable")
    annual_routes: int | None = Field(default=None, gt=0, le=10000, title="Rutas por año", description="rutas/año")
    incremental_capex_mxn: float | None = Field(default=None, ge=0, le=100000000, title="Inversión incremental", description="MXN · Vehículo, cargador y adecuaciones respecto a referencia.")


class Criteria(StrictModel):
    product_min_c: float | None = Field(default=None, ge=-5, le=15, title="Límite inferior del producto", description="°C · Confirmar aplicación con SIGMA.")
    product_max_c: float | None = Field(default=None, ge=-5, le=20, title="Límite superior del producto", description="°C")
    allowed_excursion_min: float | None = Field(default=None, ge=0, le=240, title="Excursión permitida", description="min · Criterio operativo, no certificación sanitaria.")
    confirmed: bool = Field(default=False, title="Criterios confirmados para el caso")

    @model_validator(mode="after")
    def limits(self):
        if self.product_min_c is not None and self.product_max_c is not None and self.product_min_c >= self.product_max_c:
            raise ValueError("Límite térmico inferior debe ser menor al superior.")
        return self


class RoutePoint(StrictModel):
    time_s: float = Field(ge=0, le=86400)
    speed_m_s: float = Field(ge=0, le=45)
    grade_pct: float = Field(ge=-30, le=30)


class Delivery(StrictModel):
    time_s: float = Field(ge=0, le=86400)
    door_duration_s: float = Field(ge=0, le=3600)
    unload_kg: float = Field(ge=0, le=30000)


class SimulationConfig(StrictModel):
    vehicle: Vehicle
    battery: Battery
    refrigerator_battery: Battery | None = None
    box: Box
    refrigeration: Refrigeration
    weather: Weather
    charging: Charging
    economics: Economics
    criteria: Criteria
    architecture: Literal["shared", "independent"] = "shared"
    route: list[RoutePoint] = Field(min_length=2, max_length=100000)
    deliveries: list[Delivery] = Field(max_length=300)
    step_s: float = Field(default=1, ge=.1, le=5)

    @model_validator(mode="after")
    def route_order(self):
        times = [p.time_s for p in self.route]
        if times[0] != 0 or times[-1] <= 0 or any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("La ruta debe iniciar en 0 s y tener tiempos estrictamente crecientes.")
        if len(times) > 100000 or times[-1] / self.step_s > 200000:
            raise ValueError("La ejecución excede 200 000 pasos; ajuste duración o paso.")
        if sum(e.unload_kg for e in self.deliveries) > self.vehicle.initial_payload_kg + 1e-8:
            raise ValueError("La suma de entregas excede la mercancía inicial.")
        if any(e.time_s + e.door_duration_s > times[-1] for e in self.deliveries):
            raise ValueError("Una entrega o apertura excede el final de la ruta.")
        if self.architecture == "independent" and self.refrigerator_battery is None:
            raise ValueError("La arquitectura independiente requiere batería de refrigeración.")
        return self


class Evidence(StrictModel):
    status: Literal["provided", "measured", "manufacturer", "derived", "assumed", "pending"]
    source: str = Field(max_length=2000)
    period: str | None = Field(default=None, max_length=100)


class ScenarioInput(StrictModel):
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["synthetic", "operational"]
    config: dict
    evidence: dict[str, Evidence] = Field(default_factory=dict)
    source_record: str | None = Field(default=None, max_length=100)
    notes: str = Field(default="", max_length=4000)
    route_plan: dict | None = None


GROUPS = {"vehicle": Vehicle, "battery": Battery, "refrigerator_battery": Battery, "box": Box, "refrigeration": Refrigeration, "weather": Weather, "charging": Charging, "economics": Economics, "criteria": Criteria}


def form_schema():
    return {name: cls.model_json_schema() for name, cls in GROUPS.items()}
