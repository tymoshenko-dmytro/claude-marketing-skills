"""Round-2 CLI acceptance tests (gsc-insights, seo-tech-audit, ahrefs kw.py). No network, models or real credentials."""
import importlib.util
import json
import sqlite3
import sys
import datetime as dt
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import pytest
import httpx

spec = importlib.util.spec_from_file_location('r1', str(Path(__file__).resolve().parent / 'test_cli_round1.py'))
r1 = importlib.util.module_from_spec(spec)
# REVIEW_SNAPSHOT=<a copy of the skills/ folder> runs these tests against that copy instead of the repo.
anchor = "ROOT = Path(__file__).resolve().parents[2] / 'skills'"
source = Path(spec.origin).read_text()
assert anchor in source
source = source.replace(anchor, "ROOT = Path(os.environ.get('REVIEW_SNAPSHOT', str(Path(__file__).resolve().parents[2] / 'skills')))")
exec(compile(source, spec.origin, 'exec'), r1.__dict__)
# Import only fixtures/helpers, not test functions (so this run has independent counts).
cfg, offline = r1.cfg, r1.offline
cli, archive, recipe = r1.cli, r1.archive, r1.recipe
run_crawl, run_audit, crawldb = r1.run_crawl, r1.run_audit, r1.crawldb
Response, html, dump, project = r1.Response, r1.html, r1.dump, r1.project
fake_ahrefs, api, api_error, kwcli, cluster_entry = r1.fake_ahrefs, r1.api, r1.api_error, r1.kwcli, r1.cluster_entry
crawl, audit, kw, recipes, report, pull, bing = r1.crawl, r1.audit, r1.kw, r1.recipes, r1.report, r1.pull, r1.bing

@pytest.mark.parametrize('path,rule', [('/%70rivate/a','/private/'),('/caf%C3%A9','/café'),('/private/a','/%70rivate/')])
def test_robots_equivalent_encoded_paths(cfg,monkeypatch,path,rule):
    target='https://example.test'+path
    cfg['site']['start_urls']=[target]
    db,seen,_=run_crawl(cfg,monkeypatch,{'https://example.test/robots.txt':Response(text=f'User-agent: *\nDisallow: {rule}'),target:html('private')})
    assert target not in seen, seen

def test_robots_rate_limit_defers_host(cfg,monkeypatch):
    db,seen,_=run_crawl(cfg,monkeypatch,{'https://example.test/robots.txt':Response(status=429,text='retry later'),'https://example.test/':html('home')})
    assert 'https://example.test/' not in seen, seen

@pytest.mark.parametrize('mode',['redirect','index'])
def test_sitemap_requests_obey_scope(cfg,monkeypatch,mode):
    cfg['site']['sitemaps']=['https://example.test/map.xml']
    outside='https://outside.test/private'
    seen=[]
    async def handler(req):
        seen.append(str(req.url))
        if req.url.path=='/robots.txt': return httpx.Response(200,text='')
        if str(req.url)=='https://example.test/map.xml':
            if mode=='redirect':return httpx.Response(302,headers={'location':outside})
            return httpx.Response(200,text=f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><sitemap><loc>{outside}</loc></sitemap></sitemapindex>')
        return httpx.Response(200,text='<urlset/>')
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx.AsyncClient,'request',r1.ORIGINAL_ASYNC_REQUEST)
    monkeypatch.setattr(crawl.httpx,'AsyncClient',lambda *a,**k:original(*a,transport=httpx.MockTransport(handler),**k))
    cli(monkeypatch,crawl,'--delay',0,'--concurrency',1)
    assert outside not in seen, seen

def test_redirect_target_does_not_invent_terminal_status(cfg,monkeypatch):
    routes={f'https://example.test/{i}':Response(status=301,headers={'location':f'/{i+1}'}) for i in range(10)}
    cfg['site']['start_urls']=['https://example.test/0']
    db,seen,_=run_crawl(cfg,monkeypatch,routes)
    chain=json.loads(db.execute("SELECT redirect_chain FROM pages WHERE url='https://example.test/0'").fetchone()[0])
    assert not any(h['url']=='https://example.test/10' and h.get('status')==301 for h in chain),chain

def test_blocked_redirect_is_not_a_two_hop_chain(cfg,monkeypatch):
    db,seen,folder=run_crawl(cfg,monkeypatch,{'https://example.test/':Response(status=301,headers={'location':'/b'}),
        'https://example.test/b':Response(status=301,headers={'location':'https://outside.test/c'})})
    # two observed redirects DO make a chain; this is a positive check on evidence semantics.
    assert any(f['rule']=='R02' for f in run_audit(monkeypatch,folder))

def test_bing_redacts_before_truncating(cfg,monkeypatch,capsys):
    folder=crawldb(cfg)
    secret='fixture-ABCDEFGHIJKLMNOPQRSTUVWXYZ-0123456789'
    monkeypatch.setenv('BING_WMT_API_KEY',secret)
    monkeypatch.setattr(bing.requests,'get',lambda *a,**k:Response(status=403,text='x'*185+secret))
    cli(monkeypatch,bing,'--crawl',folder)
    out=capsys.readouterr()
    assert secret[:15] not in (folder/'bing.json').read_text()+out.out+out.err

def test_audit_preserves_bing_host_evidence_failure(cfg,monkeypatch):
    folder=crawldb(cfg)
    monkeypatch.setenv('BING_WMT_API_KEY','fixture-secret')
    monkeypatch.setattr(bing.requests,'get',lambda url,**k:Response(status=403,text='page stats unavailable') if url.endswith('GetPageStats') else Response({'d':[]}))
    cli(monkeypatch,bing,'--crawl',folder)
    run_audit(monkeypatch,folder)
    output=(folder/'findings.json').read_text()+(folder/'report.md').read_text()
    assert 'page stats unavailable' in output or 'page_stats_error' in output,output

def test_audit_unavailable_robots_is_visible(cfg,monkeypatch):
    _,_,folder=run_crawl(cfg,monkeypatch,{'https://example.test/robots.txt':Response(status=503,text='unavailable')})
    run_audit(monkeypatch,folder)
    output=(folder/'findings.json').read_text()+(folder/'report.md').read_text()
    assert '503' in output or 'robots_unavailable' in output,output

@pytest.mark.parametrize('bad',['missing','provisional'])
def test_ctr_training_window_finality(cfg,monkeypatch,capsys,bad):
    con=archive(cfg)
    con.execute('DELETE FROM query_daily')
    for pos in [1,3,5,10,15]:
        con.execute('INSERT INTO query_daily VALUES(?,?,?,?,?,?,?,?)',('2026-03-01',f'train {pos}','https://example.test/a','usa','MOBILE',900,1000,pos*1000))
    con.execute('INSERT INTO query_daily VALUES(?,?,?,?,?,?,?,?)',('2026-04-12','target','https://example.test/b','usa','MOBILE',0,100,500))
    if bad=='missing':con.execute("DELETE FROM pull_log WHERE date='2026-03-01'")
    else:con.execute("UPDATE pull_log SET final=0 WHERE date='2026-03-01'")
    con.commit()
    try: rows=recipe(monkeypatch,capsys,'striking','--days',7,'--end','2026-04-12')
    except SystemExit:return
    assert next(r for r in rows if r['query']=='target')['potential_clicks']==8,rows

def test_report_marks_degraded_json_sections(cfg,monkeypatch):
    archive(cfg,start='2026-04-06')
    cli(monkeypatch,report,'--week','2026-W15','--no-sheet','--no-conversions')
    p=Path(cfg['data']['dir'])/'reports/2026-W15.json'
    data=json.loads(p.read_text())
    assert 'unavailable' in json.dumps(data).lower(),data

def test_report_current_country_totals_survive_missing_comparison(cfg,monkeypatch):
    archive(cfg,start='2026-04-06')
    cli(monkeypatch,report,'--week','2026-W15','--no-sheet','--no-conversions')
    p=Path(cfg['data']['dir'])/'reports/2026-W15.md'
    countries=p.read_text().split('## Countries this week',1)[1]
    assert 'usa' in countries or 'unavailable' in countries.lower(),countries

@pytest.mark.parametrize('bad',['missing','provisional'])
def test_keyword_join_does_not_label_partial_history_90d(cfg,monkeypatch,bad):
    con=archive(cfg)
    con.execute("UPDATE query_daily SET query='translate'")
    if bad=='missing':
        con.execute("DELETE FROM pull_log WHERE date='2026-03-01'")
        con.execute("DELETE FROM query_daily WHERE date='2026-03-01'")
    else:con.execute("UPDATE pull_log SET final=0 WHERE date='2026-03-01'")
    con.commit()
    p=project(cfg);dump(p/'clusters.json',[cluster_entry()])
    try:kwcli(monkeypatch,'prioritize')
    except SystemExit:return
    row=json.loads((p/'clusters.json').read_text())[0]
    assert row['gsc_impressions_90d'] is None or row.get('gsc_complete') is False,row

def test_keyword_unmapped_country_is_not_worldwide(cfg,monkeypatch):
    con=archive(cfg)
    con.execute('DELETE FROM query_daily')
    for country,imp,pos,page in [('bwa',100,12,'bw'),('deu',10000,1,'de')]:
        con.execute('INSERT INTO query_daily VALUES(?,?,?,?,?,?,?,?)',('2026-04-12','translate','https://example.test/'+page,country,'MOBILE',5,imp,imp*pos))
    con.commit()
    p=project(cfg);dump(p/'clusters.json',[cluster_entry(country='bw')])
    try:kwcli(monkeypatch,'prioritize')
    except SystemExit:return
    row=json.loads((p/'clusters.json').read_text())[0]
    assert row['gsc_page'] in (None,'https://example.test/bw'),row

def test_price_refreshes_expired_metrics(cfg,monkeypatch):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    calls=fake_ahrefs(monkeypatch,lambda tool,args:api({'keywords':[{'keyword':'translate','volume':100,'difficulty':10}]}))
    kwcli(monkeypatch,'price')
    con=sqlite3.connect(Path(cfg['data']['dir'])/'ahrefs_cache.sqlite');con.execute("UPDATE c SET day='2000-01-01'");con.commit()
    kwcli(monkeypatch,'price')
    assert len(calls)==2,calls

def test_invalid_success_shape_not_cached(cfg,monkeypatch):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    fake_ahrefs(monkeypatch,lambda tool,args:api({'keywords':None}))
    try:kwcli(monkeypatch,'price')
    except (RuntimeError,TypeError):pass
    con=sqlite3.connect(Path(cfg['data']['dir'])/'ahrefs_cache.sqlite')
    assert con.execute('SELECT COUNT(*) FROM c').fetchone()[0]==0

def test_transient_error_text_with_500_not_poison(cfg,monkeypatch):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    def fake(tool,args):
        return api_error(429,'Too Many Requests; retry in 500 ms')
    fake_ahrefs(monkeypatch,fake)
    try:kwcli(monkeypatch,'price')
    except RuntimeError:pass
    data=json.loads((p/'priced.json').read_text())
    assert 'translate|us' not in data,data

def test_budget_command_is_free_even_at_cap(cfg,monkeypatch):
    cfg['keywords']['monthly_unit_cap']=50
    log=Path(cfg['data']['dir'])/'ahrefs_units.jsonl'
    log.write_text(json.dumps({'ts':dt.date.today().isoformat(),'units':50,'tool':'fixture'})+'\n')
    calls=fake_ahrefs(monkeypatch,lambda tool,args:api({'limits':{}},0))
    try:kwcli(monkeypatch,'budget')
    except SystemExit:pass
    assert len(calls)==1,calls

def test_concurrent_calls_reserve_budget(cfg,monkeypatch):
    project(cfg)
    cfg['keywords']['monthly_unit_cap']=50
    # Pre-create cache so this fixture measures the budget race, not schema creation.
    kw.Ahrefs(cfg).cache.close()
    barrier=threading.Barrier(2)
    def fake(tool,args):
        try:barrier.wait(timeout=1)
        except threading.BrokenBarrierError:pass
        return api({'keywords':[{'keyword':'translate'}]},50)
    calls=fake_ahrefs(monkeypatch,fake)
    monkeypatch.setattr(sys,'argv',['kw','discover','--project','topic','--seeds','translate','--per-seed','1'])
    def invoke():
        try:kw.main()
        except SystemExit:pass
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:invoke(),range(2)))
    assert len(calls)<=1,calls

def test_pull_explicit_range_does_not_replace_older_day(cfg,monkeypatch):
    con=archive(cfg,start='2026-04-01')
    con.execute("UPDATE pull_log SET final=0 WHERE date='2026-04-01'");con.commit()
    seen=[]
    class Fake:
        def __init__(self,*a):pass
        def rows(self,day,*a):seen.append(day);return [],{}
    monkeypatch.setattr(pull,'GSC',Fake)
    cli(monkeypatch,pull,'--start','2026-04-12','--end','2026-04-12','--workers',1)
    assert set(seen)=={'2026-04-12'},seen

def test_redirected_robots_policy_is_loaded(cfg,monkeypatch):
    seen=[]
    async def handler(req):
        seen.append(str(req.url))
        if req.url.path=='/robots.txt':return httpx.Response(301,headers={'location':'/policy.txt'})
        if req.url.path=='/policy.txt':return httpx.Response(200,text='User-agent: *\nDisallow: /private')
        return httpx.Response(200,text='<html><body>home</body></html>',headers={'content-type':'text/html'})
    original=httpx.AsyncClient
    monkeypatch.setattr(httpx.AsyncClient,'request',r1.ORIGINAL_ASYNC_REQUEST)
    monkeypatch.setattr(crawl.httpx,'AsyncClient',lambda *a,**k:original(*a,transport=httpx.MockTransport(handler),**k))
    cli(monkeypatch,crawl,'--delay',0,'--concurrency',1)
    assert 'https://example.test/policy.txt' in seen and 'https://example.test/' in seen,seen

def test_variant_redirect_stays_on_configured_hosts(cfg,monkeypatch):
    con=archive(cfg);con.execute("UPDATE page_daily SET page='http://example.test/a'");con.commit()
    folder=crawldb(cfg);seen=[]
    def get(url,**k):
        seen.append(url)
        if url=='http://example.test/a':return Response(status=301,headers={'location':'https://outside.test/private'})
        return Response(status=200)
    monkeypatch.setattr(audit.httpx,'get',get)
    run_audit(monkeypatch,folder)
    assert 'https://outside.test/private' not in seen,seen

def test_unspecified_inspection_verdict_is_not_nonindexed(cfg,monkeypatch):
    folder=crawldb(cfg)
    dump(folder/'inspection.json',{'https://example.test/a':{'verdict':'VERDICT_UNSPECIFIED','coverageState':'Unknown'}})
    findings=run_audit(monkeypatch,folder)
    assert not any(f['rule']=='R07' and f['severity']!='info' for f in findings),findings

def test_inspection_invalid_200_does_not_poison_daily_cache(cfg,monkeypatch):
    folder=crawldb(cfg,[{}, {'url':'https://example.test/b'}])
    class Session:
        def post(self,*a,**k):
            if k['json']['inspectionUrl'].endswith('/b'):return Response(status=200,text='<html>temporary proxy error</html>')
            return Response({'inspectionResult':{'indexStatusResult':{'verdict':'PASS','coverageState':'Indexed'}}})
    monkeypatch.setattr(r1.inspect.seoconf,'service_account_session',lambda *a:Session())
    try:cli(monkeypatch,r1.inspect,'--crawl',folder)
    except json.JSONDecodeError:pass
    con=sqlite3.connect(Path(cfg['data']['dir'])/'inspect.sqlite')
    assert con.execute("SELECT COUNT(*) FROM inspect WHERE url LIKE '%/b'").fetchone()[0]==0
    assert 'https://example.test/a' in json.loads((folder/'inspection.json').read_text())

def test_audit_partial_exposure_is_not_full_28_days(cfg,monkeypatch):
    con=archive(cfg,clicks=2)
    con.execute("UPDATE pull_log SET final=0 WHERE date BETWEEN '2026-03-16' AND '2026-03-22'");con.commit()
    folder=crawldb(cfg,[{'title':None}])
    run_audit(monkeypatch,folder)
    res=json.loads((folder/'findings.json').read_text())
    f=next(f for f in res['findings'] if f['rule']=='R11')
    assert f['gsc_clicks_28d'] is None or res.get('exposure_complete') is False or f.get('exposure_complete') is False,f

# Broader passing controls for previous acceptance criteria that their original tests did not exercise.
@pytest.mark.parametrize('name',['coverage','striking','ctr_gap','cannibal','decay','new_queries','page_map','brand','countries','devices','questions','update_impact'])
def test_all_recipes_reject_missing_current_evidence(cfg,monkeypatch,name):
    con=archive(cfg)
    bad='2026-03-10' if name=='update_impact' else '2026-04-10'
    con.execute('DELETE FROM pull_log WHERE date=?',(bad,));con.commit()
    with pytest.raises(SystemExit):cli(monkeypatch,recipes,name,'--end','2026-04-12','--days',7,'--date','2026-03-01')

@pytest.mark.parametrize('path,expected',[('/private/item',False),('/private/public',True),('/private/public/x',False),('/other',True)])
def test_robots_wildcard_anchor_allow_controls(cfg,monkeypatch,path,expected):
    target='https://example.test'+path;cfg['site']['start_urls']=[target]
    db,seen,_=run_crawl(cfg,monkeypatch,{'https://example.test/robots.txt':Response(text='User-agent: *\nDisallow: /private/*\nAllow: /private/public$'),target:html('hello')})
    assert (target in seen)==expected

def test_complete_valid_variant_redirect_chain(cfg,monkeypatch):
    con=archive(cfg);con.execute("UPDATE page_daily SET page='http://example.test/a'");con.commit()
    folder=crawldb(cfg)
    monkeypatch.setattr(audit.httpx,'get',lambda u,**k:Response(status=301,headers={'location':'https://example.test/a'}) if u.startswith('http:') else Response(status=200))
    assert not any(f['rule']=='R10' for f in run_audit(monkeypatch,folder))

def test_explicit_incomplete_week_still_stops(cfg,monkeypatch):
    con=archive(cfg);con.execute("UPDATE pull_log SET final=0 WHERE date='2026-04-10'");con.commit()
    with pytest.raises(SystemExit,match='6/7'):cli(monkeypatch,report,'--week','2026-W15','--no-sheet','--no-conversions')

def test_brand_old_partial_week_is_labeled(cfg,monkeypatch,capsys):
    con=archive(cfg);con.execute("UPDATE pull_log SET final=0 WHERE date='2026-03-24'");con.commit()
    rows=recipe(monkeypatch,capsys,'brand','--days',7,'--end','2026-04-12')
    row=next(r for r in rows if r['week']=='2026-W13')
    assert row['days']==6 and row['site_clicks']==60 and row['non-brand_clicks']==60

def test_serp_fresh_cache_is_free(cfg,monkeypatch):
    p=project(cfg);dump(p/'priced.json',{'translate|us':{'keyword':'translate','volume':100}})
    calls=fake_ahrefs(monkeypatch,lambda *a:api({'positions':[]}))
    kwcli(monkeypatch,'serp');kwcli(monkeypatch,'serp')
    assert len(calls)==1

def test_inspection_short_quota_batch_reports_actual_counts(cfg,monkeypatch,capsys):
    folder=crawldb(cfg)
    class Session:
        def post(self,*a,**k):return Response(status=429,text='quota')
    monkeypatch.setattr(r1.inspect.seoconf,'service_account_session',lambda *a:Session())
    cli(monkeypatch,r1.inspect,'--crawl',folder)
    err=capsys.readouterr().err
    assert 'after 1 requests' in err and '-4 URLs' not in err,err

def test_malformed_page_link_leaves_diagnostic(cfg,monkeypatch,capsys):
    db,seen,folder=run_crawl(cfg,monkeypatch,{'https://example.test/':html('<a href="http://[">bad</a>')})
    row=db.execute('SELECT error FROM pages').fetchone()
    output=capsys.readouterr()
    assert row[0] or 'malformed' in output.err.lower() or 'invalid' in output.err.lower()

@pytest.mark.parametrize('value',['fixture-plain-secret','abc12'])
def test_known_plain_secret_is_always_redacted(cfg,monkeypatch,capsys,value):
    folder=crawldb(cfg);monkeypatch.setenv('BING_WMT_API_KEY',value)
    monkeypatch.setattr(bing.requests,'get',lambda *a,**k:Response(status=403,text='Invalid credential: '+value))
    cli(monkeypatch,bing,'--crawl',folder)
    out=capsys.readouterr()
    assert value not in (folder/'bing.json').read_text()+out.out+out.err

@pytest.mark.parametrize('rule,extra', [('R07',{'verdict':'FAIL','coverageState':'Crawled - currently not indexed'}),('R05',None)])
def test_audit_real_exclusion_controls(cfg,monkeypatch,rule,extra):
    folder=crawldb(cfg,[{'meta_robots':'none'}] if rule=='R05' else None)
    if extra:dump(folder/'inspection.json',{'https://example.test/a':extra})
    assert any(f['rule']==rule for f in run_audit(monkeypatch,folder))
