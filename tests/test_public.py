import time
from copy import deepcopy
from fastapi.testclient import TestClient
import pytest

from sigma_dashboard import storage
from sigma_dashboard.public_app import create_app, COOKIE, TTL_S, MAX_BODY
from sigma_dashboard.scenarios import demo_scenario
from sigma_dashboard.schemas import SimulationConfig
from sigma_dashboard.simulation import run_simulation

HEADERS = {"X-Sigma-Request":"local","Origin":"http://testserver"}


@pytest.fixture
def public(tmp_path):
    return create_app(tmp_path/'visitors')


def begin(client):
    assert client.get('/api/session').status_code==200
    return client.get('/api/scenarios').json()[0]['id']


def test_visitors_cannot_read_modify_or_duplicate_other_scenarios(public):
    with TestClient(public) as a, TestClient(public) as b:
        assert b.get('/api/scenarios').status_code==401
        sid=begin(a); other=begin(b)
        assert sid!=other
        value=a.get('/api/scenarios/'+sid).json()
        for suffix in ('','/duplicate','/run'):
            response=b.get('/api/scenarios/'+sid) if not suffix else b.post('/api/scenarios/'+sid+suffix,headers=HEADERS)
            assert response.status_code==404
        data={k:value[k] for k in ('name','kind','config','evidence','notes')}
        assert b.put('/api/scenarios/'+sid,json=data,headers=HEADERS).status_code==404
        assert a.get('/api/scenarios/'+sid).json()['revision']==1


def test_public_never_opens_local_database_or_imports_private_data(public,tmp_path,monkeypatch):
    private=tmp_path/'private.sqlite3'
    monkeypatch.setattr(storage,'DB',private)
    storage.init()
    source=demo_scenario().model_dump();source['name']='PRIVATE-SENTINEL'
    storage.save_scenario(source)
    before=private.read_bytes()
    with TestClient(public) as c:
        begin(c)
        assert 'PRIVATE-SENTINEL' not in c.get('/api/scenarios').text
        for path in ('/api/catalogue','/api/dictionary','/api/import-source','/api/import-workbook','/api/route-csv','/api/pilots/anything'):
            assert c.get(path).status_code==403
            assert c.post(path,headers=HEADERS,content=b'PRIVATE-SENTINEL').status_code==403
        for path in ('/data/dashboard.sqlite3','/config.local.json','/static/../data/dashboard.sqlite3','/openapi.json'):
            assert c.get(path).status_code==404
    assert private.read_bytes()==before
    assert storage.request_db.get() is None


def test_public_map_run_exports_are_isolated(public):
    with TestClient(public) as a,TestClient(public) as b:
        sid=begin(a);begin(b)
        plan={'mode':'direct','points':[{'lat':25.67,'lng':-100.31},{'lat':25.68,'lng':-100.30,'dwell_min':2,'door_min':1,'unload_kg':250}]}
        built=a.post('/api/map-route',json=plan,headers=HEADERS)
        assert built.status_code==200,built.text
        s=a.get('/api/scenarios/'+sid).json()
        data={k:s[k] for k in ('name','kind','config','evidence','notes')}
        data['config'].update({k:built.json()[k] for k in ('route','deliveries')})
        data['route_plan']=built.json()['route_plan']
        assert a.put('/api/scenarios/'+sid,json=data,headers=HEADERS).status_code==200
        run=a.post('/api/scenarios/'+sid+'/run',headers=HEADERS)
        assert run.status_code==200,run.text
        assert run.json()['result']['complete']
        rid=run.json()['id']
        assert b.get('/api/runs').json()==[]
        assert b.get('/api/runs/'+rid).status_code==404
        for fmt in ('csv','html','json'):
            assert a.get(f'/api/runs/{rid}/export/{fmt}').status_code==200
            assert b.get(f'/api/runs/{rid}/export/{fmt}').status_code==404
        assert run.json()['result']['summary']['distance_km']==pytest.approx(built.json()['route_plan']['distance_km'])


def test_csrf_forged_cookie_body_limit_and_non_synthetic_rejected(public):
    with TestClient(public) as c:
        c.cookies.set(COOKIE,'forged')
        assert c.get('/api/scenarios').status_code==401
        c.cookies.clear()
        sid=begin(c)
        url='/api/scenarios/'+sid+'/duplicate'
        assert c.post(url).status_code==403
        assert c.post(url,headers={**HEADERS,'Origin':'https://unrelated.example'}).status_code==403
        assert c.post('/api/scenarios',headers=HEADERS,content=b'x'*(MAX_BODY+1)).status_code==413
        bad=demo_scenario().model_dump();bad['kind']='operational'
        assert c.post('/api/scenarios',headers=HEADERS,json=bad).status_code==422
        assert c.get('/api/health',headers={'Host':'evil.example'}).status_code==400


def test_expiry_removes_files_and_missing_session_fails_closed(public):
    with TestClient(public) as c:
        begin(c)
        visitor=next(iter(public.state.sessions.visitors.values()))
        db=visitor.db
        assert db.exists()
        visitor.created=time.monotonic()-TTL_S-1
        assert c.get('/api/scenarios').status_code==401
        assert not db.exists()
        assert c.get('/api/session').status_code==200


def test_https_cookie_and_security_headers(tmp_path,monkeypatch):
    monkeypatch.setenv('RENDER_EXTERNAL_HOSTNAME','demo.example')
    app=create_app(tmp_path/'secure')
    with TestClient(app,base_url='https://demo.example') as c:
        response=c.get('/api/session')
        cookie=response.headers['set-cookie'].lower()
        assert 'httponly' in cookie and 'secure' in cookie and 'samesite=strict' in cookie
        assert response.headers['cache-control']=='no-store'
        assert response.headers['x-robots-tag']=='noindex, nofollow'
        assert "frame-ancestors 'none'" in response.headers['content-security-policy']
        assert c.get('/api/scenarios').status_code==200


def test_capacity_and_computation_limits(public):
    with TestClient(public) as c:
        sid=begin(c)
        for _ in range(5):
            assert c.post('/api/demo-scenario',headers=HEADERS).status_code==200
        assert c.post('/api/demo-scenario',headers=HEADERS).status_code==429
        public.state.sessions.compute.acquire()
        try:
            assert c.post('/api/scenarios/'+sid+'/run',headers=HEADERS).status_code==429
            assert c.get('/api/health').status_code==200
        finally:
            public.state.sessions.compute.release()
    with pytest.raises(ValueError,match='pasos internos'):
        run_simulation(SimulationConfig.model_validate(demo_scenario().config),max_steps=2)


def test_session_creation_is_bounded(public):
    with TestClient(public) as c:
        for _ in range(12):
            c.cookies.clear()
            assert c.get('/api/session').status_code==200
        c.cookies.clear()
        assert c.get('/api/session').status_code==429
