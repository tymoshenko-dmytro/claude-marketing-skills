"""Round-3 independent CLI checks (gsc-insights, seo-tech-audit, ahrefs kw.py); fixtures only."""
import importlib.util
import os
import subprocess
from pathlib import Path
import json
import sqlite3
import pytest

RUNNER = Path(__file__).resolve().parent / 'run_tests.sh'
spec = importlib.util.spec_from_file_location('r2', str(Path(__file__).resolve().parent / 'test_cli_round2.py'))
r2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r2)
cfg, offline = r2.cfg, r2.offline
cli, archive, recipe = r2.cli, r2.archive, r2.recipe
run_crawl, run_audit, crawldb = r2.run_crawl, r2.run_audit, r2.crawldb
Response, html, dump, project = r2.Response, r2.html, r2.dump, r2.project
fake_ahrefs, api, kwcli = r2.fake_ahrefs, r2.api, r2.kwcli
crawl, audit, kw, recipes, report, bing = r2.crawl, r2.audit, r2.kw, r2.recipes, r2.report, r2.bing
inspect, cwv = r2.r1.inspect, r2.r1.cwv

def test_crux_redacts_before_truncating(cfg, monkeypatch):
    folder = crawldb(cfg)
    secret = 'fixture-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789'
    monkeypatch.setenv('CRUX_API_KEY', secret)
    monkeypatch.setattr(cwv.requests, 'post', lambda *a, **k: Response(status=403, text='x'*285+secret))
    with pytest.raises(SystemExit) as exc:
        cli(monkeypatch, cwv, '--crawl', folder)
    assert secret[:15] not in str(exc.value), str(exc.value)

@pytest.mark.parametrize('secret', ['Q7', 'Z'])
def test_short_known_credentials_are_redacted(cfg, monkeypatch, capsys, secret):
    folder = crawldb(cfg)
    monkeypatch.setenv('BING_WMT_API_KEY', secret)
    monkeypatch.setattr(bing.requests, 'get', lambda *a, **k: Response(status=403, text='Invalid credential: '+secret))
    cli(monkeypatch, bing, '--crawl', folder)
    captured = capsys.readouterr()
    assert 'Invalid credential: '+secret not in (folder/'bing.json').read_text()+captured.out+captured.err

@pytest.mark.parametrize('bad', [None, [], 'wrong'])
def test_inspection_nested_invalid_result_is_retryable(cfg, monkeypatch, bad):
    folder = crawldb(cfg, [{}, {'url':'https://example.test/b'}])
    calls = []
    class Session:
        def post(self, *a, **k):
            u = k['json']['inspectionUrl']; calls.append(u)
            return Response({'inspectionResult': {'indexStatusResult': bad if u.endswith('/b') else {'verdict':'PASS','coverageState':'Indexed'}}})
    monkeypatch.setattr(inspect.seoconf, 'service_account_session', lambda *a: Session())
    failure = None
    try:
        cli(monkeypatch, inspect, '--crawl', folder)
    except (AttributeError, TypeError) as exc:
        failure = repr(exc)
    con = sqlite3.connect(Path(cfg['data']['dir'])/'inspect.sqlite')
    poisoned = con.execute("SELECT COUNT(*) FROM inspect WHERE url LIKE '%/b'").fetchone()[0]
    assert failure is None and poisoned == 0, (failure, poisoned)
    assert 'https://example.test/a' in json.loads((folder/'inspection.json').read_text())
    cli(monkeypatch, inspect, '--crawl', folder)
    assert calls.count('https://example.test/b') == 2

@pytest.mark.parametrize('bad', [None, {'volume':100}, {'keyword':'translate','volume':'broken'}])
def test_ahrefs_malformed_rows_do_not_poison_cache(cfg, monkeypatch, bad):
    p = project(cfg); dump(p/'candidates.json', {'translate':{'sources':['seed']}})
    calls = fake_ahrefs(monkeypatch, lambda *a: api({'keywords':[bad]}, 7))
    try:
        kwcli(monkeypatch, 'price', '--fields', 'volume')
    except (RuntimeError, KeyError, TypeError):
        pass
    con = sqlite3.connect(Path(cfg['data']['dir'])/'ahrefs_cache.sqlite')
    assert con.execute('SELECT COUNT(*) FROM c').fetchone()[0] == 0
    assert 'translate|us' not in json.loads((p/'priced.json').read_text())
    assert sum(json.loads(l)['units'] for l in (Path(cfg['data']['dir'])/'ahrefs_units.jsonl').read_text().splitlines()) == 7

def test_robots_encoded_allow_does_not_outrank_longer_disallow(cfg, monkeypatch):
    target = 'https://example.test/private/a'; cfg['site']['start_urls'] = [target]
    _, seen, _ = run_crawl(cfg, monkeypatch, {
        'https://example.test/robots.txt': Response(text='User-agent: *\nAllow: /%70%72%69\nDisallow: /private/'),
        target: html('private')})
    assert target not in seen, seen

def test_split_pricing_tracks_each_child_cache(cfg, monkeypatch):
    p = project(cfg); dump(p/'candidates.json', {k:{'sources':['seed']} for k in ['good','poison','other']})
    def respond(tool, args):
        if 'poison' in args['keywords']:
            raise RuntimeError('500 internal server error')
        return api({'keywords':[{'keyword':k,'volume':100} for k in args['keywords'].split(',')]})
    calls = fake_ahrefs(monkeypatch, respond)
    kwcli(monkeypatch, 'price', '--fields', 'volume')
    con = sqlite3.connect(Path(cfg['data']['dir'])/'ahrefs_cache.sqlite')
    keys = [k for (k,) in con.execute('SELECT k FROM c') if json.loads(k[len('keywords-explorer-overview'):])['keywords']=='good']
    assert len(keys) == 1
    con.execute("UPDATE c SET day='2000-01-01' WHERE k=?", (keys[0],)); con.commit()
    calls.clear()
    kwcli(monkeypatch, 'price', '--fields', 'volume')
    assert any(c['arguments']['keywords']=='good' for c in calls), (calls, json.loads((p/'priced.json').read_text()))

def test_partial_exposure_is_labeled_in_developer_tickets(cfg, monkeypatch):
    con = archive(cfg, clicks=2)
    con.execute("UPDATE pull_log SET final=0 WHERE date BETWEEN '2026-03-16' AND '2026-03-22'"); con.commit()
    folder = crawldb(cfg, [{'status':404}], [('https://example.test/source','https://example.test/a','broken',0,1)])
    run_audit(monkeypatch, folder)
    tickets = (folder/'tickets.md').read_text()
    assert 'R01' in (folder/'findings.json').read_text()
    assert 'partial' in tickets.lower() or '21/28' in tickets, tickets

def test_report_page_movers_have_unavailable_state(cfg, monkeypatch):
    archive(cfg, start='2026-04-06')
    cli(monkeypatch, report, '--week','2026-W15','--no-sheet','--no-conversions')
    folder = Path(cfg['data']['dir'])/'reports'
    data = json.loads((folder/'2026-W15.json').read_text())
    assert data.get('sections',{}).get('page_losers',{}).get('status') == 'unavailable', data.get('sections')
    section = (folder/'2026-W15.md').read_text().split('## Pages that lost',1)[1].split('## Striking',1)[0]
    assert 'unavailable' in section.lower() and '_none_' not in section

def test_report_conversion_error_is_not_ok(cfg, monkeypatch, tmp_path):
    archive(cfg)
    sql = tmp_path/'fixture.sql'; sql.write_text('SELECT 1')
    cfg['conversions'] = {'sql': str(sql), 'bq_project':'fixture'}
    class Session:
        def post(self,*a,**k): return Response(status=403,text='fixture access denied')
    monkeypatch.setattr(report.seoconf,'service_account_session',lambda *a:Session())
    cli(monkeypatch, report, '--week','2026-W15','--no-sheet')
    data=json.loads((Path(cfg['data']['dir'])/'reports/2026-W15.json').read_text())
    assert data['sections']['conversions']['status']=='unavailable',data['sections']['conversions']

def test_country_absent_in_complete_baseline_is_zero(cfg, monkeypatch, capsys):
    con=archive(cfg)
    con.execute("DELETE FROM query_daily WHERE date BETWEEN '2026-03-30' AND '2026-04-05'");con.commit()
    row=recipe(monkeypatch,capsys,'countries','--days',7,'--end','2026-04-12')[0]
    assert row['clicks_prev']==0,row

def test_runner_propagates_failing_pytest_exit(tmp_path):
    fake = tmp_path/'fixture-python'
    fake.write_text('#!/bin/sh\nprintf "1 failed in 0.01s\\n"\nexit 1\n')
    fake.chmod(0o755)
    proc=subprocess.run(['sh',str(RUNNER)],env={**os.environ,'PYTHON':str(fake)},capture_output=True,text=True)
    assert proc.returncode!=0,(proc.returncode,proc.stdout)

# Additional positive controls for acceptance alternatives and request boundaries.
def test_reserved_slash_stays_distinct(cfg, monkeypatch):
    target='https://example.test/a%2Fb';cfg['site']['start_urls']=[target]
    _, seen, _=run_crawl(cfg,monkeypatch,{'https://example.test/robots.txt':Response(text='User-agent: *\nDisallow: /a/b'),target:html('allowed')})
    assert target in seen

@pytest.mark.parametrize('location',['/robots.txt','https://outside.test/policy.txt'])
def test_robots_failed_redirect_keeps_host_unassessed(cfg,monkeypatch,location):
    _, seen, folder=run_crawl(cfg,monkeypatch,{'https://example.test/robots.txt':Response(status=301,headers={'location':location})})
    assert 'https://example.test/' not in seen and 'https://outside.test/policy.txt' not in seen
    fs=run_audit(monkeypatch,folder)
    assert any(f['rule']=='R20x' for f in fs)

def test_price_identical_fresh_request_is_free(cfg,monkeypatch):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    calls=fake_ahrefs(monkeypatch,lambda *a:api({'keywords':[{'keyword':'translate','volume':100}]}))
    kwcli(monkeypatch,'price','--fields','volume');kwcli(monkeypatch,'price','--fields','volume')
    assert len(calls)==1

def test_valid_empty_ahrefs_collection_is_cached(cfg,monkeypatch):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    calls=fake_ahrefs(monkeypatch,lambda *a:api({'keywords':[]}))
    kwcli(monkeypatch,'price');kwcli(monkeypatch,'price')
    assert len(calls)==1 and json.loads((p/'priced.json').read_text())['translate|us']['no_data_or_below_floor']

def test_inspection_html_error_retries_and_preserves_success(cfg,monkeypatch,capsys):
    folder=crawldb(cfg,[{}, {'url':'https://example.test/b'}]);calls=[]
    class Session:
        def post(self,*a,**k):
            u=k['json']['inspectionUrl'];calls.append(u)
            if u.endswith('/b') and calls.count(u)==1:return Response(status=200,text='<html>proxy failure</html>')
            return Response({'inspectionResult':{'indexStatusResult':{'verdict':'PASS','coverageState':'Indexed'}}})
    monkeypatch.setattr(inspect.seoconf,'service_account_session',lambda *a:Session())
    cli(monkeypatch,inspect,'--crawl',folder)
    assert 'https://example.test/a' in json.loads((folder/'inspection.json').read_text())
    assert 'proxy failure' in capsys.readouterr().err
    cli(monkeypatch,inspect,'--crawl',folder)
    assert calls.count('https://example.test/a')==1 and calls.count('https://example.test/b')==2
    assert len(json.loads((folder/'inspection.json').read_text()))==2

def test_discovery_unmapped_market_does_not_import_worldwide(cfg,monkeypatch,capsys):
    import datetime as dt
    today=dt.date.today().isoformat()
    con=archive(cfg,start=today,end=today)
    con.execute("UPDATE query_daily SET query='translate german',country='deu'");con.commit()
    p=project(cfg)
    fake_ahrefs(monkeypatch,lambda *a:api({'keywords':[]}))
    kwcli(monkeypatch,'discover','--country','bw','--seeds','translate','--from-gsc')
    assert 'translate german' not in json.loads((p/'candidates.json').read_text())
    assert 'mapping' in capsys.readouterr().err

def test_redirect_limit_and_malformed_link_evidence(cfg,monkeypatch):
    cfg['site']['start_urls']=['https://example.test/0','https://example.test/html']
    routes={f'https://example.test/{i}':Response(status=301,headers={'location':f'/{i+1}'}) for i in range(10)}
    routes['https://example.test/html']=html('<a href="http://[">broken</a>')
    db,seen,_=run_crawl(cfg,monkeypatch,routes)
    chain=json.loads(db.execute("SELECT redirect_chain FROM pages WHERE url LIKE '%/0'").fetchone()[0])
    assert len(chain)==11 and chain[-1]['status'] is None and 'limit' in chain[-1]['not_followed']
    assert 'https://example.test/10' not in seen
    assert json.loads(db.execute("SELECT link_errors FROM pages WHERE url LIKE '%/html'").fetchone()[0])['malformed_links']==1

def test_cross_process_cap_reserves_and_releases(cfg,monkeypatch,tmp_path):
    # The first real CLI waits inside a local transport stand-in while a second process tries the same cap.
    import time
    project(cfg);cfg['keywords']['monthly_unit_cap']=50
    kw.Ahrefs(cfg).cache.close()
    entered=tmp_path/'entered';release=tmp_path/'release';second=tmp_path/'second-result'
    def respond(*a):
        entered.write_text(str(os.getpid()))
        deadline=time.monotonic()+5
        while not release.exists() and time.monotonic()<deadline:time.sleep(.01)
        return api({'keywords':[]},50)
    fake_ahrefs(monkeypatch,respond)
    first_pid=os.fork()
    if first_pid==0:
        try:
            kwcli(monkeypatch,'discover','--seeds','first','--per-seed',1)
        except BaseException:
            os._exit(2)
        os._exit(0)
    try:
        deadline=time.monotonic()+5
        while not entered.exists() and time.monotonic()<deadline:time.sleep(.01)
        assert entered.exists()
        second_pid=os.fork()
        if second_pid==0:
            try:
                kwcli(monkeypatch,'discover','--seeds','second','--per-seed',1)
            except SystemExit as exc:
                second.write_text(str(exc));os._exit(0)
            except BaseException:
                os._exit(2)
            os._exit(3)
        _,status=os.waitpid(second_pid,0)
        assert os.waitstatus_to_exitcode(status)==0
        assert 'reserved' in second.read_text()
    finally:
        release.touch()
        _,status=os.waitpid(first_pid,0)
    assert os.waitstatus_to_exitcode(status)==0
    assert json.loads((Path(cfg['data']['dir'])/'ahrefs_units.jsonl.reserved').read_text())=={}
    assert sum(json.loads(l)['units'] for l in (Path(cfg['data']['dir'])/'ahrefs_units.jsonl').read_text().splitlines())==50
