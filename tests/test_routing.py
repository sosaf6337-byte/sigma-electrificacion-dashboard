import asyncio
import pytest
import httpx
from pydantic import ValidationError
from sigma_dashboard.routing import RoutePlan, compile_profile, build_route
from sigma_dashboard.schemas import SimulationConfig
from sigma_dashboard.scenarios import demo_scenario
from sigma_dashboard.simulation import run_simulation
from test_api import client, HEADERS


def plan(**kw):
    return RoutePlan.model_validate({"mode":"direct","points":[
        {"lat":25.67,"lng":-100.31,"name":"Salida"},
        {"lat":25.68,"lng":-100.30,"name":"Entrega","dwell_min":10,"door_min":3,"unload_kg":250}],**kw})


@pytest.mark.parametrize('distance',[10,300,12345.67])
def test_profile_conserves_distance_and_stops(distance):
    r,d,it=compile_profile(plan(),[distance])
    integrated=sum((b['time_s']-a['time_s'])*(a['speed_m_s']+b['speed_m_s'])/2 for a,b in zip(r,r[1:]))
    assert integrated==pytest.approx(distance,abs=1e-7)
    assert all(b['time_s']>a['time_s'] for a,b in zip(r,r[1:]))
    assert r[-1]['speed_m_s']==r[-2]['speed_m_s']==0
    assert d[0]['time_s']==r[-2]['time_s']
    assert it[-1]['departure_s']-it[-1]['arrival_s']==pytest.approx(600)


def test_route_and_refrigeration_share_clock():
    built=asyncio.run(build_route(plan()))
    c=demo_scenario().config
    c.update({k:built[k] for k in ('route','deliveries')})
    result=run_simulation(SimulationConfig.model_validate(c))
    assert result['complete']
    assert result['summary']['distance_km']==pytest.approx(built['route_plan']['distance_km'])
    assert result['series'][-1]['payload_kg']==1550
    stopped=[s for s in result['series'] if s['door_open']]
    assert stopped and all(s['speed_kmh']<1e-6 for s in stopped)
    assert sum(s['refrigeration_kw'] for s in stopped)>0


def test_invalid_stop_and_duplicate_point():
    with pytest.raises(ValidationError):
        plan(points=[{'lat':0,'lng':0},{'lat':0,'lng':1,'door_min':2,'dwell_min':1}])
    with pytest.raises(ValueError):
        compile_profile(plan(),[0])


def test_map_save_reload_invalidation_and_duplicate(client):
    built=client.post('/api/map-route',headers=HEADERS,json=plan().model_dump()).json()
    s=client.post('/api/demo-scenario',headers=HEADERS).json()
    payload={k:s[k] for k in ('name','kind','config','evidence','source_record','notes')}
    payload['config'].update({k:built[k] for k in ('route','deliveries')})
    payload['route_plan']=built['route_plan']
    url='/api/scenarios/'+s['id']
    saved=client.put(url,headers=HEADERS,json=payload)
    assert saved.status_code==200
    assert client.get(url).json()['route_plan']['distance_km']>0
    assert client.post(url+'/duplicate',headers=HEADERS).status_code==200
    result=client.post(url+'/run',headers=HEADERS)
    assert result.status_code==200 and result.json()['result']['complete']
    assert result.json()['scenario']['route_plan']['provider']=='Segmentos geodésicos directos'
    payload['config']['route'][1]['speed_m_s']+=1
    assert client.put(url,headers=HEADERS,json=payload).json()['route_plan'] is None


def test_provider_failure_is_explicit(client,monkeypatch):
    async def fail(points):
        raise httpx.ConnectTimeout('offline')
    monkeypatch.setattr('sigma_dashboard.routing.road_route',fail)
    response=client.post('/api/map-route',headers=HEADERS,json=plan(mode='roads').model_dump())
    assert response.status_code==502
    assert 'reintenta' in response.json()['detail']
