"""Round-4 independent entry-point acceptance tests (gsc-insights, seo-tech-audit, ahrefs kw.py, run_tests.sh);
fixtures and temporary copies only."""
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import sys
import pytest

RUNNER = Path(__file__).resolve().parent / 'run_tests.sh'
spec = importlib.util.spec_from_file_location('r3', str(Path(__file__).resolve().parent / 'test_cli_round3.py'))
r3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r3)
cfg, offline = r3.cfg, r3.offline
cli, archive, recipe = r3.cli, r3.archive, r3.recipe
run_crawl, run_audit, crawldb = r3.run_crawl, r3.run_audit, r3.crawldb
Response, html, dump, project = r3.Response, r3.html, r3.dump, r3.project
fake_ahrefs, api, kwcli = r3.fake_ahrefs, r3.api, r3.kwcli
inspect, cwv, bing, kw, report = r3.inspect, r3.cwv, r3.bing, r3.kw, r3.report

def test_short_credential_must_not_break_other_secret_redaction(cfg, monkeypatch):
    folder = crawldb(cfg)
    # Force deterministic insertion order without reading/printing any real values.
    for k in list(os.environ):
        if re.search('KEY|TOKEN|SECRET|WEBHOOK|PASSWORD', k, re.I):
            monkeypatch.delenv(k)
    monkeypatch.setenv('OTHER_API_KEY', 'Q7')
    secret = 'fixture-Q7-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789'
    monkeypatch.setenv('CRUX_API_KEY', secret)
    monkeypatch.setattr(cwv.requests, 'post', lambda *a, **k: Response(status=403, text='Invalid credential: '+secret))
    with pytest.raises(SystemExit) as exc:
        cli(monkeypatch, cwv, '--crawl', folder)
    assert 'ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789' not in str(exc.value), str(exc.value)
    assert '403' in str(exc.value)

@pytest.mark.parametrize('field,value', [('type', 7), ('url', {'bad':'url'}), ('page_type', ['bad'])])
def test_serp_malformed_consumed_fields_never_enter_cache(cfg, monkeypatch, field, value):
    p = project(cfg)
    dump(p/'priced.json', {'translate|us': {'keyword':'translate','volume':100}})
    good = {'position':1, 'url':'https://other.test/a', 'type':['organic'], 'page_type':'/Text/Article'}
    calls = fake_ahrefs(monkeypatch, lambda *a: api({'positions':[{**good, field:value}]}, 7))
    error = None
    try:
        kwcli(monkeypatch, 'serp')
    except (RuntimeError, TypeError, AttributeError) as exc:
        error = repr(exc)
    con = sqlite3.connect(Path(cfg['data']['dir'])/'ahrefs_cache.sqlite')
    cached = con.execute('SELECT COUNT(*) FROM c').fetchone()[0]
    units = sum(json.loads(l)['units'] for l in (Path(cfg['data']['dir'])/'ahrefs_units.jsonl').read_text().splitlines())
    calls = fake_ahrefs(monkeypatch, lambda *a: api({'positions':[good]}, 1))
    retry_error = None
    try:
        kwcli(monkeypatch, 'serp')
    except (RuntimeError, TypeError, AttributeError) as exc:
        retry_error = repr(exc)
    assert cached == 0 and error and error.startswith('RuntimeError'), (cached, error, units, len(calls), retry_error)
    assert units == 7 and len(calls) == 1 and retry_error is None
    assert json.loads((p/'serps.json').read_text())['translate|us']['urls'] == [good['url']]

def test_pricing_rejects_malformed_intents_before_completion(cfg, monkeypatch):
    p = project(cfg)
    dump(p/'candidates.json', {'translate':{'sources':['seed']}})
    fake_ahrefs(monkeypatch, lambda *a: api({'keywords':[{'keyword':'translate','volume':100,'intents':['commercial']}]}, 7))
    error = None
    try:
        kwcli(monkeypatch, 'price', '--fields', 'volume,intents')
    except RuntimeError as exc:
        error = str(exc)
    records = json.loads((p/'priced.json').read_text())
    con = sqlite3.connect(Path(cfg['data']['dir'])/'ahrefs_cache.sqlite')
    cached = con.execute('SELECT COUNT(*) FROM c').fetchone()[0]
    # Exercise the downstream real entry point to demonstrate the practical impact.
    downstream = None
    if records:
        dump(p/'serps.json', {'translate|us':{'no_serp':True}})
        try:
            kwcli(monkeypatch, 'cluster')
        except (TypeError, AttributeError) as exc:
            downstream = repr(exc)
    units = sum(json.loads(l)['units'] for l in (Path(cfg['data']['dir'])/'ahrefs_units.jsonl').read_text().splitlines())
    calls = fake_ahrefs(monkeypatch, lambda *a: api({'keywords':[{'keyword':'translate','volume':100,'intents':{'commercial':True}}]}, 1))
    kwcli(monkeypatch, 'price', '--fields', 'volume,intents')
    assert error is not None and cached == 0 and not records, (error, cached, records, downstream, len(calls), units)
    assert units == 7 and len(calls) == 1

def test_inspection_invalid_daily_cache_is_retried_and_falls_back(cfg, monkeypatch):
    folder = crawldb(cfg)
    con = sqlite3.connect(Path(cfg['data']['dir'])/'inspect.sqlite')
    con.execute('CREATE TABLE inspect(url TEXT, day TEXT, result TEXT, PRIMARY KEY(url, day))')
    today = dt.date.today(); u = 'https://example.test/a'
    good = {'inspectionResult':{'indexStatusResult':{'verdict':'PASS','coverageState':'Indexed'}}}
    con.executemany('INSERT INTO inspect VALUES(?,?,?)', [(u, (today-dt.timedelta(days=1)).isoformat(), json.dumps(good)),
        (u,today.isoformat(),json.dumps({'inspectionResult':{'indexStatusResult':None}}))])
    con.commit()
    calls = []
    class Session:
        def post(self, *a, **k):
            calls.append(k['json']['inspectionUrl'])
            return Response(status=503,text='fixture unavailable')
    monkeypatch.setattr(inspect.seoconf,'service_account_session',lambda *a:Session())
    cli(monkeypatch,inspect,'--crawl',folder)
    result = json.loads((folder/'inspection.json').read_text())[u]
    assert calls == [u] and result['inspected'] == (today-dt.timedelta(days=1)).isoformat()
    cli(monkeypatch,inspect,'--crawl',folder)
    assert calls == [u,u]

def test_inspection_quota_counts_invalid_cached_url_as_pending(cfg, monkeypatch, capsys):
    folder = crawldb(cfg)
    con = sqlite3.connect(Path(cfg['data']['dir'])/'inspect.sqlite')
    con.execute('CREATE TABLE inspect(url TEXT, day TEXT, result TEXT, PRIMARY KEY(url, day))')
    con.execute('INSERT INTO inspect VALUES(?,?,?)', ('https://example.test/a',dt.date.today().isoformat(),json.dumps({'inspectionResult':{'indexStatusResult':None}})))
    con.commit()
    calls=[]
    class Session:
        def post(self,*a,**k):
            calls.append(k['json']['inspectionUrl'])
            return Response(status=429,text='quota')
    monkeypatch.setattr(inspect.seoconf,'service_account_session',lambda *a:Session())
    cli(monkeypatch,inspect,'--crawl',folder)
    log = capsys.readouterr()
    assert len(calls)==1 and 'after 1 requests; 1 URLs left' in log.err, (calls,log.err)
    assert json.loads((folder/'inspection.json').read_text()) == {}

@pytest.mark.parametrize('baseline', ['complete', 'incomplete'])
def test_country_device_baselines_stay_distinct(cfg, monkeypatch, capsys, baseline):
    con=archive(cfg)
    con.execute("DELETE FROM query_daily WHERE date BETWEEN '2026-03-30' AND '2026-04-05'")
    if baseline=='incomplete':
        con.execute("UPDATE pull_log SET final=0 WHERE date='2026-04-01'")
    con.commit()
    for name in ['countries','devices']:
        cli(monkeypatch,r3.recipes,name,'--format','json','--days',7,'--end','2026-04-12')
        data=json.loads(capsys.readouterr().out)
        row=data['rows'][0]
        assert row['clicks']==70
        if name=='countries': assert row['clicks_prev'] == (0 if baseline=='complete' else None)
        assert row['clicks_change_pct'] is None
        if baseline=='incomplete': assert 'comparison unavailable' in json.dumps(data)

@pytest.mark.parametrize('state', ['empty', 'skipped', 'unavailable'])
def test_report_section_states(cfg, monkeypatch, tmp_path, state):
    archive(cfg)
    sql=tmp_path/'fixture.sql';sql.write_text('SELECT 1')
    cfg['conversions']={'sql':str(sql),'bq_project':'fixture'}
    class Session:
        def post(self,*a,**k):
            if state=='unavailable':return Response(status=403,text='fixture denied')
            return Response({'jobComplete':True,'schema':{'fields':[{'name':'page'},{'name':'organic_sessions'}]},'rows':[]})
    monkeypatch.setattr(report.seoconf,'service_account_session',lambda *a:Session())
    cli(monkeypatch,report,'--week','2026-W15','--no-sheet',*(['--no-conversions'] if state=='skipped' else []))
    data=json.loads((Path(cfg['data']['dir'])/'reports/2026-W15.json').read_text())
    assert data['sections']['conversions']['status']=={'empty':'ok','skipped':'skipped','unavailable':'unavailable'}[state]
    assert data['sections']['page_losers']['status']==data['sections']['page_gainers']['status']=='ok'

def test_both_page_movers_unavailable(cfg, monkeypatch):
    archive(cfg,start='2026-04-06')
    cli(monkeypatch,report,'--week','2026-W15','--no-sheet','--no-conversions')
    d=Path(cfg['data']['dir'])/'reports'
    data=json.loads((d/'2026-W15.json').read_text())
    for key in ['page_losers','page_gainers']:
        assert data['sections'][key]['status']=='unavailable'
    md=(d/'2026-W15.md').read_text().split('## Pages that lost',1)[1].split('## Striking',1)[0]
    assert md.count('unavailable')==2 and '_none_' not in md

@pytest.mark.parametrize('partial',[False,True])
def test_ticket_exposure_coverage(cfg, monkeypatch, partial):
    con=archive(cfg,clicks=2)
    if partial: con.execute("UPDATE pull_log SET final=0 WHERE date BETWEEN '2026-03-16' AND '2026-03-22'")
    con.commit()
    folder=crawldb(cfg,[{'status':404}],[('https://example.test/source','https://example.test/a','broken',0,1)])
    findings=run_audit(monkeypatch,folder)
    tickets=(folder/'tickets.md').read_text()
    assert next(f for f in findings if f['rule']=='R01')['priority']==('P2' if partial else 'P1')
    if partial: assert '42 clicks / 2100 impressions' in tickets and '21/28 final days' in tickets and 'partial' in tickets
    else: assert '56 clicks / 2800 impressions in Google over 28 days' in tickets and 'partial' not in tickets.lower()

@pytest.mark.parametrize('mode',['pass','assertion','collection'])
def test_runner_real_pytest_status_and_process_isolation(tmp_path, mode):
    # run_tests.sh runs the test_*.py files that sit next to it; this Python has pytest.
    runner=tmp_path/'runner';runner.mkdir()
    shutil.copyfile(RUNNER,runner/'run_tests.sh')
    source='import os\nfrom pathlib import Path\ndef test_fixture():\n    Path(__file__).with_suffix(".pid").write_text(str(os.getpid()))\n'
    (runner/'test_first.py').write_text(source + ('    assert False\n' if mode=='assertion' else '    assert True\n'))
    (runner/'test_second.py').write_text('def broken(:\n' if mode=='collection' else source)
    proc=subprocess.run(['sh',str(runner/'run_tests.sh')],env={**os.environ,'PYTHON':sys.executable},capture_output=True,text=True)
    assert (proc.returncode==0)==(mode=='pass'), (proc.returncode,proc.stdout,proc.stderr)
    if mode!='collection':
        pids=[p.read_text() for p in runner.glob('*.pid')]
        assert len(pids)==2 and len(set(pids))==2

@pytest.mark.parametrize('bad', [None, {'volume':100}, {'keyword':'translate','volume':'broken'}])
def test_original_malformed_price_can_retry_valid_response(cfg, monkeypatch, bad):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    calls=fake_ahrefs(monkeypatch,lambda *a:api({'keywords':[bad]},7))
    with pytest.raises(RuntimeError):kwcli(monkeypatch,'price','--fields','volume')
    con=sqlite3.connect(Path(cfg['data']['dir'])/'ahrefs_cache.sqlite')
    assert con.execute('SELECT COUNT(*) FROM c').fetchone()[0]==0
    assert json.loads((p/'priced.json').read_text())=={}
    calls=fake_ahrefs(monkeypatch,lambda *a:api({'keywords':[{'keyword':'translate','volume':100}]},3))
    kwcli(monkeypatch,'price','--fields','volume')
    kwcli(monkeypatch,'price','--fields','volume')
    assert len(calls)==1 and json.loads((p/'priced.json').read_text())['translate|us']['volume']==100
    assert [json.loads(l)['units'] for l in (Path(cfg['data']['dir'])/'ahrefs_units.jsonl').read_text().splitlines()]==[7,3]

def test_legitimate_nullable_metrics_and_empty_serp(cfg, monkeypatch):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    calls=fake_ahrefs(monkeypatch,lambda tool,args:api({'positions':[]} if tool=='serp-overview' else
        {'keywords':[{'keyword':'translate','volume':100,'difficulty':None,'intents':None,'traffic_potential':None}]}))
    kwcli(monkeypatch,'price')
    kwcli(monkeypatch,'serp')
    kwcli(monkeypatch,'cluster')
    assert len(calls)==2 and json.loads((p/'clusters.json').read_text())[0]['no_serp'] is True
    kwcli(monkeypatch,'price');kwcli(monkeypatch,'serp')
    assert len(calls)==2

def test_split_provenance_includes_nodata_and_poison(cfg, monkeypatch):
    p=project(cfg)
    dump(p/'candidates.json',{k:{'sources':['seed']} for k in ['good','poison','missing','other']})
    def respond(tool,args):
        if 'poison' in args['keywords']:raise RuntimeError('500 internal server error')
        return api({'keywords':[{'keyword':k,'volume':100} for k in args['keywords'].split(',') if k!='missing']})
    calls=fake_ahrefs(monkeypatch,respond)
    kwcli(monkeypatch,'price','--fields','volume')
    records=json.loads((p/'priced.json').read_text())
    for keyword, expected in [('good','good'),('poison','poison'),('missing','missing,other'),('other','missing,other')]:
        ck=records[keyword+'|us']['_ck']
        assert json.loads(ck[len('keywords-explorer-overview'):])['keywords']==expected
    assert records['poison|us']['poison'] and records['missing|us']['no_data_or_below_floor']
    calls.clear();kwcli(monkeypatch,'price','--fields','volume')
    assert [c['arguments']['keywords'] for c in calls]==['poison']
    con=sqlite3.connect(Path(cfg['data']['dir'])/'ahrefs_cache.sqlite')
    con.execute("UPDATE c SET day='2000-01-01' WHERE k=?",(records['good|us']['_ck'],));con.commit()
    calls.clear();kwcli(monkeypatch,'price','--fields','volume')
    assert any(c['arguments']['keywords']=='good' for c in calls)
    assert all('other' not in c['arguments']['keywords'] and 'missing' not in c['arguments']['keywords'] for c in calls)
