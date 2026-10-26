from copy import deepcopy
import math
import pytest

from sigma_dashboard.physics import road_load, BatteryState, charging_estimate, G, J_PER_KWH
from sigma_dashboard.schemas import SimulationConfig
from sigma_dashboard.scenarios import demo_scenario
from sigma_dashboard.simulation import run_simulation
from sigma_dashboard.thermal import ThermalState


@pytest.fixture
def cfg():
    return SimulationConfig.model_validate(demo_scenario().config)


def short(cfg, duration=600):
    c=cfg.model_dump()
    c['route']=[{'time_s':0,'speed_m_s':0,'grade_pct':0},{'time_s':30,'speed_m_s':10,'grade_pct':0},{'time_s':duration-30,'speed_m_s':10,'grade_pct':0},{'time_s':duration,'speed_m_s':0,'grade_pct':0}]
    c['deliveries']=[]
    return SimulationConfig.model_validate(c)


def test_steady_flat_matches_independent_analytic(cfg):
    v=10;mass=cfg.vehicle.ready_mass_kg+cfg.vehicle.initial_payload_kg
    r=road_load(cfg.vehicle,cfg.weather,cfg.vehicle.initial_payload_kg,v,v,0,1)
    expected=(mass*G*cfg.vehicle.rolling_coefficient+.5*cfg.weather.air_density_kg_m3*cfg.vehicle.drag_area_m2*v*v)*v
    assert r['power_w']==pytest.approx(expected)


def test_acceleration_energy_matches_kinetic_energy(cfg):
    c=cfg.vehicle.model_copy(update={'rolling_coefficient':0,'drag_area_m2':0})
    r=road_load(c,cfg.weather,1000,0,20,0,10)
    assert r['power_w']*10==pytest.approx(.5*(c.ready_mass_kg+1000+c.rotational_mass_kg)*20**2)


def test_grade_sign_and_payload(cfg):
    a=road_load(cfg.vehicle,cfg.weather,0,10,10,5,1)
    b=road_load(cfg.vehicle,cfg.weather,0,10,10,-5,1)
    heavy=road_load(cfg.vehicle,cfg.weather,2000,10,10,5,1)
    assert a['grade_w']>0>b['grade_w']
    assert heavy['power_w']>a['power_w']


def test_battery_charge_discharge_conservation(cfg):
    b=BatteryState.create(cfg.battery)
    start=b.soc
    for p in [20000,-10000,0]:
        b.advance(p,60)
    assert b.chemical_j==pytest.approx(b.terminal_j+b.loss_j,abs=1e-6)
    assert (start-b.soc)*cfg.battery.capacity_kwh*cfg.battery.soh*J_PER_KWH==pytest.approx(b.chemical_j)
    assert b.loss_j>0


def test_full_battery_cannot_accept_charge(cfg):
    b=BatteryState(cfg.battery,cfg.battery.maximum_soc)
    assert b.limits(1)[1]==0
    with pytest.raises(ValueError):b.advance(-1,1)


def test_torque_limit_stops_instead_of_faking_completed_route(cfg):
    c=short(cfg).model_copy(deep=True)
    c.vehicle.max_wheel_force_n=100
    r=run_simulation(c)
    assert not r['complete']
    assert r['failure']['system']=='traction'
    assert r['summary']['distance_km']==0


def test_small_battery_stops_at_reserve(cfg):
    c=short(cfg).model_copy(deep=True)
    c.battery.capacity_kwh=.1
    r=run_simulation(c)
    assert not r['complete']
    assert r['failure']['system']=='battery'
    assert r['summary']['soc_final_pct']>=c.battery.minimum_soc*100-1e-6
    assert r['charging']['grid_kwh'] is None


def test_reference_demo_balances_and_mass(cfg):
    r=run_simulation(cfg)
    assert r['complete']
    assert r['summary']['payload_final_kg']==300
    assert r['summary']['distance_km']==pytest.approx(81.24,abs=1e-6)
    assert abs(r['checks']['bus_balance_j'])<.01
    assert abs(r['checks']['battery_balance_j'])<.01
    assert abs(r['checks']['thermal_sensible_balance_j'])<.01
    assert abs(r['checks']['moisture_balance_kg'])<1e-9
    assert r['economics']['energy_saving_mxn'] is None
    assert r['viability']['thermal']=='Información insuficiente'


def test_closed_box_equilibrium(cfg):
    b=cfg.box.model_copy(update={'initial_air_c':3,'initial_wall_c':3,'initial_product_c':3,'internal_heat_w':0,'solar_absorptivity':0,'leakage_ach':0})
    w=cfg.weather.model_copy(update={'ambient_c':3,'solar_w_m2':0})
    f=cfg.refrigeration.model_copy(update={'on_c':4,'off_c':2,'evaporator_fan_kw':0,'controls_kw':0})
    t=ThermalState.create(b)
    for i in range(100):t.step(b,f,w,1000,False,0,i,1)
    assert t.air==pytest.approx([3,3,3])
    assert t.core==pytest.approx([3,3,3])


def test_open_door_adds_heat_and_moisture_and_core_lags(cfg):
    f=cfg.refrigeration.model_copy(update={'on_c':50,'off_c':40})
    closed=ThermalState.create(cfg.box);opened=deepcopy(closed)
    for i in range(60):
        closed.step(cfg.box,f,cfg.weather,1800,False,0,i,.5)
        opened.step(cfg.box,f,cfg.weather,1800,True,0,i,.5)
    assert opened.air[2]>closed.air[2]
    assert sum(opened.humidity)>sum(closed.humidity)
    assert opened.core[2]<opened.surface[2]<opened.air[2]


def test_refrigeration_consumes_while_stopped(cfg):
    c=short(cfg).model_copy(deep=True)
    for p in c.route:p.speed_m_s=0
    r=run_simulation(c)
    assert r['summary']['energy_kwh']['traction']==0
    assert r['summary']['energy_kwh']['refrigeration']>0
    assert r['summary']['consumption_kwh_km'] is None


def test_independent_battery_energy_is_not_duplicated(cfg):
    c=short(cfg).model_copy(deep=True)
    c.architecture='independent';c.refrigerator_battery=c.battery.model_copy(deep=True)
    r=run_simulation(c)
    assert r['complete']
    assert r['summary']['refrigeration_soc_final_pct']<c.refrigerator_battery.initial_soc*100
    assert abs(r['checks']['bus_balance_j'])<.01
    assert r['charging']['grid_kwh'] is None


def test_time_step_convergence(cfg):
    c=short(cfg)
    r1=run_simulation(c)
    c.step_s=.5
    r2=run_simulation(c)
    assert abs(r1['summary']['battery_net_kwh']-r2['summary']['battery_net_kwh'])/r2['summary']['battery_net_kwh']<.01
    assert abs(r1['summary']['product_max_c']-r2['summary']['product_max_c'])<.05


def test_missing_route_is_rejected():
    c=demo_scenario().config;c['route']=[]
    with pytest.raises(ValueError):SimulationConfig.model_validate(c)


def test_delivery_moving_rejected(cfg):
    cfg.deliveries[0].time_s=100
    with pytest.raises(ValueError,match='detenido'):run_simulation(cfg)


def test_nonfinite_and_invalid_soc_rejected():
    c=demo_scenario().config;c['vehicle']['ready_mass_kg']=float('nan')
    with pytest.raises(ValueError):SimulationConfig.model_validate(c)
    c=demo_scenario().config;c['battery']['minimum_soc']=.95
    with pytest.raises(ValueError):SimulationConfig.model_validate(c)


def test_site_zero_is_not_missing(cfg):
    cfg.charging.available_site_kw=0
    r=charging_estimate(cfg.battery,.5,cfg.charging)
    assert r['status']=='No viable bajo este escenario'
    cfg.charging.available_site_kw=None
    r=charging_estimate(cfg.battery,.5,cfg.charging)
    assert r['site_status']=='Información insuficiente'
