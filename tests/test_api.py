from pathlib import Path
from fastapi.testclient import TestClient
import pytest
from sigma_dashboard import storage
from sigma_dashboard.app import app

HEADERS={'X-Sigma-Request':'local'}


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(storage,'DB',tmp_path/'test.sqlite3')
    with TestClient(app) as c:yield c


def test_full_save_run_export_revision_flow(client):
    s=client.get('/api/scenarios').json()[0]
    old=client.get('/api/scenarios/'+s['id']).json()
    response=client.post('/api/scenarios/'+s['id']+'/run',headers=HEADERS)
    assert response.status_code==200,response.text
    run=response.json();rid=run['id']
    assert run['result']['complete']
    assert not run['stale']
    assert run['result']['series_count_full']>len(run['result']['series'])
    for fmt in ['csv','json','html']:
        assert client.get(f'/api/runs/{rid}/export/{fmt}').status_code==200
    report=client.get(f'/api/runs/{rid}/export/html').text
    assert 'Conservación térmica' in report
    assert 'Sin dato / no evaluable' in report
    assert 'no representa operación SIGMA' in report
    new={k:old[k] for k in ['name','kind','config','evidence','source_record','notes'] if k in old}
    new['config']['weather']['ambient_c']=40
    assert client.put('/api/scenarios/'+s['id'],json=new,headers=HEADERS).status_code==200
    historical=client.get('/api/runs/'+rid).json()
    assert historical['stale']
    assert historical['scenario']['config']['weather']['ambient_c']==35


def test_real_draft_has_no_invented_vehicle_params(client):
    r={'record_id':'synthetic-row','equipment':'TEST-001','capacity_kg':2000,'source_row':2}
    import importlib
    api_module=importlib.import_module('sigma_dashboard.app')
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(api_module,'catalogue',lambda:{'vehicles':[r],'source':{'sha256':'synthetic'}})
        new=client.post('/api/pilots/'+r['record_id'],headers=HEADERS).json()
    assert new['kind']=='operational'
    assert new['config']['vehicle']=={'payload_capacity_kg':r['capacity_kg']}
    result=client.post('/api/scenarios/'+new['id']+'/run',headers=HEADERS)
    assert result.status_code==422
    assert any(e['field']=='battery' for e in result.json()['detail'])


def test_no_cross_origin_mutations(client):
    sid=client.get('/api/scenarios').json()[0]['id']
    assert client.post('/api/scenarios/'+sid+'/duplicate').status_code==403
    assert client.post('/api/scenarios/'+sid+'/duplicate',headers={**HEADERS,'Origin':'https://unrelated.example'}).status_code==403


def test_csv_units_validation(client):
    result=client.post('/api/route-csv',content='time_s,speed_m_s,grade_pct\n0,0,0\n10,5,1',headers={**HEADERS,'Content-Type':'text/csv'})
    assert result.status_code==200
    assert result.json()['route'][1]['speed_m_s']==5
    assert client.post('/api/route-csv',content='time,kmh\n0,10',headers=HEADERS).status_code==422


def test_route_provenance_survives_edit_without_becoming_measured(client):
    sid=client.get('/api/scenarios').json()[0]['id']
    old=client.get('/api/scenarios/'+sid).json()
    new={k:old[k] for k in ['name','kind','config','evidence','source_record','notes'] if k in old}
    new['config']['route'][1]['speed_m_s']=11
    new['evidence']['route']={'status':'provided','source':'CSV ruta-prueba.csv; SHA256 de prueba'}
    response=client.put('/api/scenarios/'+sid,json=new,headers=HEADERS)
    assert response.status_code==200
    evidence=response.json()['evidence']['route']
    assert evidence['status']=='assumed'
    assert evidence['source']=='CSV ruta-prueba.csv; SHA256 de prueba'
