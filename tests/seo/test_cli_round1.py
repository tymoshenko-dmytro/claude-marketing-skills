"""Round-1 offline contract tests for the CLI entry points of gsc-insights, seo-tech-audit and ahrefs (kw.py).

No network, no credentials: every HTTP exchange is a stand-in. Run through run_tests.sh (one process per file)."""
import asyncio
import datetime as dt
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import sqlite3
import sys
import types
import urllib.parse
import urllib.robotparser

import pytest
import requests
import httpx
ORIGINAL_ASYNC_REQUEST = httpx.AsyncClient.request

ROOT = Path(__file__).resolve().parents[2] / 'skills'  # the repo's skills/ folder
def module(name, skill):
    directory = ROOT / skill / 'scripts'
    sys.path.insert(0, str(directory))
    spec = importlib.util.spec_from_file_location(name, directory / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

pull = module('gsc_pull', 'gsc-insights')
recipes = module('gsc_recipes', 'gsc-insights')
report = module('gsc_report', 'gsc-insights')
sheets = module('sheets', 'gsc-insights')
crawl = module('crawl', 'seo-tech-audit')
audit = module('audit', 'seo-tech-audit')
inspect = module('inspect_urls', 'seo-tech-audit')
cwv = module('cwv', 'seo-tech-audit')
bing = module('bing', 'seo-tech-audit')
render = module('render_check', 'seo-tech-audit')
kw = module('kw', 'ahrefs')

@pytest.fixture(autouse=True)
def offline(monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError('Unexpected network operation')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(socket.socket, 'connect_ex', forbidden)
    monkeypatch.setattr(requests.sessions.Session, 'request', forbidden)
    monkeypatch.setattr(httpx.Client, 'request', forbidden)
    monkeypatch.setattr(httpx.AsyncClient, 'request', forbidden)
    monkeypatch.delenv('SLACK_WEBHOOK_URL', raising=False)

@pytest.fixture
def cfg(tmp_path, monkeypatch):
    c = {'site': {'name': 'fixture', 'hosts': ['example.test'], 'start_urls': ['https://example.test/'],
                  'sitemaps': [], 'locales': ['es', 'ar'], 'gsc_property': 'sc-domain:example.test',
                  'bing_site': 'https://example.test/'},
         'data': {'dir': str(tmp_path)}, 'brand': {'patterns': ['fixture app'], 'ambiguous': [r'\bfixture\b']},
         'keywords': {'default_country': 'us'}, 'report': {}}
    monkeypatch.setattr(pull.seoconf, 'load', lambda *a: c)
    return c

def cli(monkeypatch, mod, *args):
    monkeypatch.setattr(sys, 'argv', [mod.__name__, *map(str, args)])
    return mod.main()

def archive(cfg, start='2026-01-01', end='2026-04-12', clicks=10):
    con = pull.connect(cfg)
    a, b = dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    for i in range((b-a).days+1):
        day = (a+dt.timedelta(days=i)).isoformat()
        pull.store(con, {'day': day, 'final': 1,
            'site': [{'clicks': clicks, 'impressions':100, 'position': 8}],
            'pages': [{'keys':['https://example.test/a'], 'clicks': clicks, 'impressions':100, 'position':8}],
            'queries': [{'keys':['how translate', 'https://example.test/a', 'usa', 'MOBILE'], 'clicks': clicks, 'impressions':100, 'position':8}]})
    return con

def recipe(monkeypatch, capsys, name, *args):
    cli(monkeypatch, recipes, name, '--format', 'json', *args)
    return json.loads(capsys.readouterr().out)['rows']

class Response:
    def __init__(self, data=None, status=200, text=None, headers=None, content=None):
        self.status_code = status
        self.data = data
        self.text = text if text is not None else json.dumps(data)
        self.headers = headers or {}
        self.content = content if content is not None else self.text.encode()
    def json(self): return self.data

# GSC pull: actual CLI, actual pagination and storage, stand-in session only.
def test_pull_pagination_grains_replacement(cfg, monkeypatch):
    calls=[]
    class Session:
        def post(self, url, json, **kw):
            calls.append(json)
            dims=json['dimensions']; offset=json['startRow']
            if dims == ['date']:
                rows=[{'keys':['2026-04-12'],'clicks':11,'impressions':100,'position':4}]
                return Response({'rows':rows,'metadata':{'firstIncompleteDate':'2026-04-12'}})
            keysets=([['https://example.test/a'],['https://example.test/b'],['https://example.test/c']]
                     if dims == ['page'] else [[f'q{i}',f'https://example.test/{i}','usa','MOBILE'] for i in range(3)])
            rows=[{'keys':k,'clicks':2,'impressions':10,'position':i+1} for i,k in enumerate(keysets)][offset:offset+2]
            return Response({'rows':rows})
    monkeypatch.setattr(pull.seoconf,'service_account_session',lambda *a:Session())
    monkeypatch.setattr(pull,'ROW_LIMIT',2)
    cli(monkeypatch,pull,'--start','2026-04-12','--end','2026-04-12','--workers',1)
    cli(monkeypatch,pull,'--start','2026-04-12','--end','2026-04-12','--workers',1)
    con=pull.connect(cfg)
    assert con.execute('SELECT clicks,impressions,pos_x_impr,final FROM site_daily').fetchone()==(11,100,400,0)
    assert con.execute('SELECT COUNT(*),SUM(pos_x_impr) FROM page_daily').fetchone()==(3,60)
    assert con.execute('SELECT COUNT(*) FROM query_daily').fetchone()[0]==3
    assert any(c['startRow']==2 for c in calls)

@pytest.mark.defect
def test_pull_revisits_stranded_provisional_day(cfg, monkeypatch):
    con=archive(cfg,start='2026-04-01',end='2026-04-12')
    con.execute("UPDATE pull_log SET final=0 WHERE date='2026-04-01'"); con.commit()
    seen=[]
    class Fake:
        def __init__(self,*a): pass
        def rows(self,day,dims,aggregation):
            seen.append(day); return [],{}
    monkeypatch.setattr(pull,'GSC',Fake)
    cli(monkeypatch,pull,'--end','2026-04-12','--workers',1)
    assert '2026-04-01' in seen

@pytest.mark.parametrize('name',list(recipes.RECIPES))
def test_all_recipes_complete_archive_smoke(cfg,monkeypatch,capsys,name):
    archive(cfg)
    rows=recipe(monkeypatch,capsys,name,'--end','2026-04-12','--days',7,'--date','2026-03-01')
    assert isinstance(rows,list)

@pytest.mark.defect
@pytest.mark.parametrize('name',['striking','decay','countries','update_impact'])
def test_recipes_reject_nonfinal_or_missing_days(cfg,monkeypatch,name):
    con=archive(cfg)
    bad='2026-03-10' if name=='update_impact' else '2026-04-10'
    con.execute('UPDATE pull_log SET final=0 WHERE date=?',(bad,)); con.commit()
    with pytest.raises(SystemExit):
        cli(monkeypatch,recipes,name,'--end','2026-04-12','--days',7,'--date','2026-03-01','--format','json')

@pytest.mark.defect
def test_brand_honors_historical_end(cfg,monkeypatch,capsys):
    archive(cfg)
    rows=recipe(monkeypatch,capsys,'brand','--days',7,'--end','2026-01-11')
    assert any(r['week']=='2026-W02' and r['non-brand_clicks']==70 for r in rows)
    assert all(r['week'] <= '2026-W02' for r in rows)

@pytest.mark.defect
def test_ctr_curve_uses_nearest_observed_bucket(cfg,monkeypatch,capsys):
    con=archive(cfg)
    con.execute('DELETE FROM query_daily')
    for pos,clicks in [(1,100),(5,50),(10,20),(15,10),(20,5)]:
        con.execute('INSERT INTO query_daily VALUES(?,?,?,?,?,?,?,?)',('2026-04-12',f'train {pos}','https://example.test/a','usa','MOBILE',clicks,1000,pos*1000))
    con.execute('INSERT INTO query_daily VALUES(?,?,?,?,?,?,?,?)',('2026-04-12','target','https://example.test/b','usa','MOBILE',0,100,800))
    con.commit()
    rows=recipe(monkeypatch,capsys,'ctr_gap','--end','2026-04-12')
    assert next(r for r in rows if r['query']=='target')['expected_clicks']==2

@pytest.mark.defect
def test_cannibal_switches_scoped_to_locale(cfg,monkeypatch,capsys):
    con=archive(cfg)
    con.execute('DELETE FROM query_daily')
    for day in ['2026-04-11','2026-04-12']:
        for path,imp in [('es/a',30),('es/b',30),('ar/a' if day.endswith('11') else 'ar/b',100)]:
            con.execute('INSERT INTO query_daily VALUES(?,?,?,?,?,?,?,?)',(day,'translate','https://example.test/'+path,'usa','MOBILE',1,imp,imp*8))
    con.commit()
    rows=recipe(monkeypatch,capsys,'cannibal','--end','2026-04-12')
    assert next(r for r in rows if r['locale']=='es')['top_page_switches']==1

@pytest.mark.parametrize('q,expected',[('fixture app','brand'),('fixture meaning','ambiguous'),('how translate','non-brand'),('', 'anonymized')])
def test_brand_classifier_in_entry_point(cfg,monkeypatch,capsys,q,expected):
    con=archive(cfg)
    con.execute('UPDATE query_daily SET query=?',(q,));con.commit()
    rows=recipe(monkeypatch,capsys,'striking','--end','2026-04-12','--include-brand')
    assert rows[0]['brand']==expected

def test_weighted_aggregation_and_recipe_thresholds(cfg,monkeypatch,capsys):
    con=archive(cfg,start='2026-04-11',end='2026-04-12')
    con.execute("UPDATE query_daily SET clicks=1,impressions=10,pos_x_impr=20 WHERE date='2026-04-11'")
    con.execute("UPDATE query_daily SET clicks=9,impressions=90,pos_x_impr=900 WHERE date='2026-04-12'")
    con.commit()
    rows=recipe(monkeypatch,capsys,'striking','--end','2026-04-12','--days',2,'--min-impr',100)
    assert (rows[0]['ctr_pct'],rows[0]['position'])==(10,9.2)
    assert recipe(monkeypatch,capsys,'striking','--end','2026-04-12','--days',2,'--min-impr',101)==[]

@pytest.mark.defect
def test_report_with_zero_previous_week(cfg,monkeypatch):
    con=archive(cfg)
    for table in ("site_daily", "page_daily", "query_daily"):
        con.execute(f"UPDATE {table} SET clicks=0 WHERE date BETWEEN '2026-03-30' AND '2026-04-05'")
    con.commit()
    cli(monkeypatch,report,'--week','2026-W15','--no-sheet','--no-conversions')
    assert (Path(cfg['data']['dir'])/'reports/2026-W15.slack.txt').exists()

@pytest.mark.defect
def test_report_falls_back_to_last_complete_week(cfg,monkeypatch):
    con=archive(cfg)
    con.execute("UPDATE pull_log SET final=0 WHERE date='2026-04-10'");con.commit()
    cli(monkeypatch,report,'--no-sheet','--no-conversions')
    assert (Path(cfg['data']['dir'])/'reports/2026-W14.json').exists()

@pytest.mark.defect
def test_report_clears_empty_detail_tabs(cfg,monkeypatch):
    archive(cfg); cfg['report']['sheet_id']='fixture-sheet'
    written={}
    class Sheet:
        def __init__(self,*a):pass
        def upsert_row(self,*a):pass
        def overwrite(self,title,rows):written[title]=rows
    monkeypatch.setattr(sheets,'Sheet',Sheet)
    cli(monkeypatch,report,'--week','2026-W15','--no-conversions')
    assert 'Decaying pages' in written and 'Organic landing pages' in written

@pytest.mark.defect
def test_report_paginates_conversion_results(cfg,monkeypatch):
    archive(cfg)
    sql=Path(cfg['data']['dir'])/'fixture.sql';sql.write_text('SELECT fixture')
    cfg['conversions']={'sql':str(sql),'bq_project':'fixture'}
    class Session:
        def post(self,*a,**k): return Response({'jobComplete':True,'jobReference':{'projectId':'fixture','jobId':'j'},'pageToken':'next','totalRows':'2',
            'schema':{'fields':[{'name':'landing_page'},{'name':'organic_sessions'}]},'rows':[{'f':[{'v':'/a'},{'v':'3'}]}]})
        def get(self,*a,**k): return Response({'jobComplete':True,'rows':[{'f':[{'v':'/b'},{'v':'7'}]}]})
    monkeypatch.setattr(report.seoconf,'service_account_session',lambda *a:Session())
    cli(monkeypatch,report,'--week','2026-W15','--no-sheet')
    result=json.loads((Path(cfg['data']['dir'])/'reports/2026-W15.json').read_text())
    assert sum(r['organic_sessions'] for r in result['conversions'])==10

def test_sheet_upsert_idempotent(cfg,monkeypatch):
    class Session:
        rows=[['week','clicks'],['2026-W14','1'],['2026-W15','2'],['2026-W15','3']]
        def get(self,url,**k):return Response({'sheets':[{'properties':{'title':'Weekly','sheetId':1}}]} if '/values/' not in url else {'values':self.rows})
        def post(self,*a,**k):return Response({})
        def put(self,url,**k):self.rows=k['json']['values'];return Response({})
    session=Session();monkeypatch.setattr(sheets.seoconf,'service_account_session',lambda *a:session)
    sh=sheets.Sheet(cfg,'fixture');sh.upsert_row('Weekly',['week','clicks'],['2026-W15',8]);sh.upsert_row('Weekly',['week','clicks'],['2026-W15',8])
    assert session.rows==[['week','clicks'],['2026-W14','1'],['2026-W15','8']]

# Crawl CLI: no server, every GET served from an in-memory route map.
def run_crawl(cfg,monkeypatch,routes):
    seen=[]
    class Client:
        def __init__(self,*a,**k):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def get(self,url,**k):
            seen.append(url)
            return routes.get(url,Response(status=404,text='',headers={}))
    monkeypatch.setattr(crawl.httpx,'AsyncClient',Client)
    cli(monkeypatch,crawl,'--delay',0,'--concurrency',1)
    folder=Path(cfg['data']['dir'])/'crawls/latest'
    return sqlite3.connect(folder/'crawl.sqlite'),seen,folder

def html(body):return Response(text='<html><head><title>Fixture page with enough title</title></head><body>'+body+'</body></html>',headers={'content-type':'text/html'})

@pytest.mark.defect
@pytest.mark.parametrize('target',['https://outside.test/private','https://example.test/private'])
def test_crawl_redirect_targets_obey_scope_and_robots(cfg,monkeypatch,target):
    routes={'https://example.test/robots.txt':Response(text='User-agent: *\nDisallow: /private'),
            'https://example.test/':Response(status=302,headers={'location':target}),target:html('private')}
    db,seen,_=run_crawl(cfg,monkeypatch,routes)
    assert target not in seen

@pytest.mark.defect
def test_crawl_robots_wildcards(cfg,monkeypatch):
    cfg['site']['start_urls']=['https://example.test/private/item']
    db,seen,_=run_crawl(cfg,monkeypatch,{'https://example.test/robots.txt':Response(text='User-agent: *\nDisallow: /private/*'),
        'https://example.test/private/item':html('blocked')})
    assert 'https://example.test/private/item' not in seen

@pytest.mark.defect
def test_crawl_robots_503_is_not_allow_all(cfg,monkeypatch):
    db,seen,_=run_crawl(cfg,monkeypatch,{'https://example.test/robots.txt':Response(status=503,text='unavailable'),
        'https://example.test/':html('blocked until robots available')})
    assert 'https://example.test/' not in seen

@pytest.mark.defect
def test_crawl_html_base_link_resolution(cfg,monkeypatch):
    db,seen,_=run_crawl(cfg,monkeypatch,{'https://example.test/':html('<base href="https://example.test/docs/"><a href="guide">guide</a>')})
    assert db.execute('SELECT dst FROM links').fetchone()[0]=='https://example.test/docs/guide'

@pytest.mark.defect
def test_crawl_gzipped_sitemap(cfg,monkeypatch):
    import gzip
    cfg['site']['sitemaps']=['https://example.test/sitemap.xml.gz']
    xml=b'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://example.test/only-in-map</loc></url></urlset>'
    db,seen,_=run_crawl(cfg,monkeypatch,{'https://example.test/sitemap.xml.gz':Response(content=gzip.compress(xml),headers={'content-type':'application/gzip'}),
        'https://example.test/':html('home')})
    assert 'https://example.test/only-in-map' in seen

def test_crawl_sitemap_index_robots_and_links(cfg,monkeypatch):
    cfg['site']['sitemaps']=['https://example.test/index.xml']
    ns='xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'
    db,seen,_=run_crawl(cfg,monkeypatch,{
        'https://example.test/robots.txt':Response(text='User-agent: *\nDisallow: /private'),
        'https://example.test/index.xml':Response(text=f'<sitemapindex {ns}><sitemap><loc>https://example.test/map.xml</loc></sitemap></sitemapindex>'),
        'https://example.test/map.xml':Response(text=f'<urlset {ns}><url><loc>https://example.test/a</loc><lastmod>2026-04-01</lastmod></url></urlset>'),
        'https://example.test/':html('<a href="/a#fragment" rel="nofollow">A</a><a href="/private">P</a><a href="https://outside.test/">O</a><script>throw Error("must not execute")</script>'),
        'https://example.test/a':html('A')})
    assert 'https://example.test/private' not in seen and 'https://outside.test/' not in seen
    assert db.execute("SELECT lastmod FROM sitemap_urls WHERE url LIKE '%/a'").fetchone()[0]=='2026-04-01'
    assert db.execute("SELECT nofollow,internal FROM links WHERE dst LIKE '%/a'").fetchone()==(1,1)

def crawldb(cfg, pages=None, links=None):
    folder=Path(cfg['data']['dir'])/'audit';folder.mkdir(exist_ok=True)
    db=sqlite3.connect(folder/'crawl.sqlite');db.executescript(crawl.SCHEMA)
    db.execute("INSERT INTO meta VALUES('started','fixture')")
    for extra in pages or [{}]:
        row={'url':'https://example.test/a','depth':0,'status':200,'final_url':'https://example.test/a',
             'redirect_chain':'[]','content_type':'text/html','ttfb_ms':20,'title':'A sufficiently descriptive title',
             'meta_description':'x'*120,'h1':'["Heading"]','canonical':'https://example.test/a',
             'hreflang':'[]','jsonld_types':'[]','word_count':500,'internal_links':0,'external_links':0,
             'images':0,'images_no_alt':0,'in_sitemap':1,'blocked_by_robots':0,'html_lang':'en'}
        row.update(extra)
        db.execute(f"INSERT INTO pages({','.join(row)}) VALUES({','.join('?' for _ in row)})",list(row.values()))
    db.executemany('INSERT INTO links VALUES(?,?,?,?,?)', links or [])
    db.commit();return folder

def run_audit(monkeypatch,folder):
    cli(monkeypatch,audit,'--crawl',folder)
    return json.loads((folder/'findings.json').read_text())['findings']

@pytest.mark.defect
def test_audit_unlinked_404_not_internal_link_finding(cfg,monkeypatch):
    folder=crawldb(cfg,[{'status':404}])
    fs=run_audit(monkeypatch,folder)
    assert not any(f['rule']=='R01' for f in fs)

@pytest.mark.defect
def test_decorative_empty_alt_is_not_missing_alt(cfg,monkeypatch):
    db,seen,folder=run_crawl(cfg,monkeypatch,{'https://example.test/':html('<img src="a" alt=""><img src="b" alt=""><img src="c" alt="">')})
    fs=run_audit(monkeypatch,folder)
    assert not any(f['rule']=='R15' for f in fs)

@pytest.mark.defect
def test_audit_unavailable_inspection_is_not_nonindexed_evidence(cfg,monkeypatch):
    folder=crawldb(cfg)
    (folder/'inspection.json').write_text(json.dumps({'https://example.test/a':{'verdict':None,'coverageState':None,'inspected':'2026-04-12'}}))
    fs=run_audit(monkeypatch,folder)
    assert not any(f['rule']=='R07' and f['severity']!='info' for f in fs)

@pytest.mark.defect
def test_audit_exposure_excludes_provisional_future_days(cfg,monkeypatch):
    con=archive(cfg,clicks=1)
    pull.store(con,{'day':'2026-04-13','final':0,'site':[],'queries':[],
        'pages':[{'keys':['https://example.test/a'],'clicks':1000,'impressions':2000,'position':1}]})
    folder=crawldb(cfg,[{'status':404}], [('https://example.test/','https://example.test/a','A',0,1)])
    fs=run_audit(monkeypatch,folder)
    f=next(f for f in fs if f['rule']=='R01')
    assert (f['gsc_clicks_28d'],f['priority'])==(28,'P2')

@pytest.mark.defect
def test_audit_valid_script_region_hreflang(cfg,monkeypatch):
    folder=crawldb(cfg,[{'html_lang':'zh-Hans-CN','hreflang':json.dumps([{'lang':'zh-Hans-CN','href':'https://example.test/a'}])}])
    fs=run_audit(monkeypatch,folder)
    assert not any(f['title']=='hreflang: invalid language code' for f in fs)

@pytest.mark.defect
def test_audit_none_robots_means_noindex(cfg,monkeypatch):
    folder=crawldb(cfg,[{'meta_robots':'none'}])
    fs=run_audit(monkeypatch,folder)
    assert any(f['rule']=='R05' for f in fs)

def test_audit_priorities_and_tickets(cfg,monkeypatch):
    archive(cfg,clicks=10)
    folder=crawldb(cfg,[{'status':404}], [('https://example.test/','https://example.test/a','A',0,1)])
    fs=run_audit(monkeypatch,folder)
    f=next(f for f in fs if f['rule']=='R01')
    assert (f['gsc_clicks_28d'],f['priority'])==(280,'P1')
    assert '[P1] Internal links' in (folder/'tickets.md').read_text()
    assert '280' in (folder/'report.md').read_text()

# Optional evidence collectors and their error paths.
def test_inspection_success_cached_and_quota_error_no_fabrication(cfg,monkeypatch):
    folder=crawldb(cfg)
    calls=[]
    class Session:
        def post(self,*a,**k):
            calls.append(k)
            return Response({'inspectionResult':{'indexStatusResult':{'verdict':'PASS','coverageState':'Indexed'}}})
    monkeypatch.setattr(inspect.seoconf,'service_account_session',lambda *a:Session())
    cli(monkeypatch,inspect,'--crawl',folder);cli(monkeypatch,inspect,'--crawl',folder)
    assert len(calls)==1
    assert json.loads((folder/'inspection.json').read_text())['https://example.test/a']['verdict']=='PASS'

@pytest.mark.defect
def test_inspection_stops_dispatching_after_quota(cfg,monkeypatch):
    folder=crawldb(cfg);urls=folder/'urls.txt';urls.write_text('\n'.join('https://example.test/'+str(i) for i in range(30)))
    calls=[]
    class Session:
        def post(self,*a,**k):calls.append(k);return Response(status=429,text='quota')
    monkeypatch.setattr(inspect.seoconf,'service_account_session',lambda *a:Session())
    cli(monkeypatch,inspect,'--crawl',folder,'--urls',urls)
    assert len(calls)<=5

@pytest.mark.defect
def test_inspection_network_failure_keeps_prior_success(cfg,monkeypatch):
    folder=crawldb(cfg);urls=folder/'urls.txt';urls.write_text('https://example.test/a\nhttps://example.test/b')
    class Session:
        def post(self,*a,**k):
            if k['json']['inspectionUrl'].endswith('/b'):raise requests.Timeout('synthetic timeout')
            return Response({'inspectionResult':{'indexStatusResult':{'verdict':'PASS'}}})
    monkeypatch.setattr(inspect.seoconf,'service_account_session',lambda *a:Session())
    cli(monkeypatch,inspect,'--crawl',folder,'--urls',urls)
    assert 'https://example.test/a' in json.loads((folder/'inspection.json').read_text())

@pytest.mark.parametrize('status',[404,200])
def test_cwv_no_data_and_success(cfg,monkeypatch,status):
    folder=crawldb(cfg);monkeypatch.setenv('CRUX_API_KEY','fixture-secret')
    def post(url,**k):
        if status==404:return Response(status=404,data={})
        if url.endswith('queryHistoryRecord'):
            return Response({'record':{'metrics':{'largest_contentful_paint':{'percentilesTimeseries':{'p75s':[2500,4001]}}}}})
        return Response({'record':{'collectionPeriod':{'lastDate':{'year':2026,'month':4,'day':12}},
            'metrics':{'largest_contentful_paint':{'percentiles':{'p75':2500}},'interaction_to_next_paint':{'percentiles':{'p75':501}}}}})
    monkeypatch.setattr(cwv.requests,'post',post)
    cli(monkeypatch,cwv,'--crawl',folder)
    result=json.loads((folder/'cwv.json').read_text())
    assert 'fixture-secret' not in (folder/'cwv.json').read_text()
    if status==200:
        assert result['origins']['https://example.test']['PHONE']['largest_contentful_paint']['rating']=='good'
        assert result['origins']['https://example.test']['PHONE']['interaction_to_next_paint']['rating']=='poor'
    else:assert 'status' in result['origins']['https://example.test']['PHONE']

@pytest.mark.defect
def test_bing_response_secret_is_redacted(cfg,monkeypatch):
    folder=crawldb(cfg);monkeypatch.setenv('BING_WMT_API_KEY','fixture-secret')
    monkeypatch.setattr(bing.requests,'get',lambda *a,**k:Response(status=403,text='invalid request ?apikey=fixture-secret'))
    cli(monkeypatch,bing,'--crawl',folder)
    assert 'fixture-secret' not in (folder/'bing.json').read_text()

@pytest.mark.defect
def test_bing_page_stats_failure_not_silently_dropped(cfg,monkeypatch):
    folder=crawldb(cfg);monkeypatch.setenv('BING_WMT_API_KEY','fixture-secret')
    monkeypatch.setattr(bing.requests,'get',lambda url,**k:Response(status=403,text='denied') if url.endswith('GetPageStats') else Response({'d':[]}))
    cli(monkeypatch,bing,'--crawl',folder)
    result=json.loads((folder/'bing.json').read_text())
    assert 'error' in json.dumps(result)

# Keyword staged CLI: the real API v3 transport, cache and unit log; only the HTTP exchange is a stand-in.
API_KEY='fixture-api-key'
def project(cfg):
    p=Path(cfg['data']['dir'])/'keywords/topic';p.mkdir(parents=True,exist_ok=True);return p

def dump(p,data):p.write_text(json.dumps(data))

def api(data,units=1):
    """A successful API v3 answer: JSON body and the documented unit header."""
    return (200,{'content-type':'application/json','x-api-units-cost-total-actual':str(units)},json.dumps(data))

def api_error(status,text,units=0):
    return (status,{'x-api-units-cost-total-actual':str(units)},text)

def fake_ahrefs(monkeypatch, fn):
    """Replace only ahrefs_api.http; fn(tool, args) returns (status, headers, body) or raises like a network error."""
    calls=[]
    monkeypatch.setenv('AHREFS_API_KEY',API_KEY)
    def http(method,url,headers,body=None,timeout=None):
        assert url.startswith(kw.ahrefs_api.BASE) and headers['Authorization']=='Bearer '+API_KEY,(url,headers)
        parts=urllib.parse.urlsplit(url)
        tool=kw.ahrefs_api.tool_name(parts.path[len('/v3/'):])
        args=dict(urllib.parse.parse_qsl(parts.query))
        calls.append({'name':tool,'arguments':args})
        return fn(tool,args)
    monkeypatch.setattr(kw.ahrefs_api,'http',http)
    monkeypatch.setattr(kw.ahrefs_api,'_sleep',lambda seconds:None)
    return calls

def kwcli(monkeypatch,stage,*args):return cli(monkeypatch,kw,stage,'--project','topic',*args)

def test_kw_discover_cache_keys_and_unit_logging(cfg,monkeypatch):
    calls=fake_ahrefs(monkeypatch,lambda tool,args:api({'keywords':[{'keyword':'translate audio'}]},50))
    kwcli(monkeypatch,'discover','--seeds','translate','--country','us')
    kwcli(monkeypatch,'discover','--seeds','translate','--country','us')
    kwcli(monkeypatch,'discover','--seeds','translate','--country','de')
    assert len(calls)==2
    rows=[json.loads(l) for l in (Path(cfg['data']['dir'])/'ahrefs_units.jsonl').read_text().splitlines()]
    assert sum(r['units'] for r in rows)==100
    assert all('keywords' not in r['args'] for r in rows)

@pytest.mark.defect
@pytest.mark.parametrize('change',['fields','floor'])
def test_kw_price_revalidates_changed_fields_or_floor(cfg,monkeypatch,change):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    calls=fake_ahrefs(monkeypatch,lambda tool,args:api({'keywords':([] if json.loads(args.get('where','{}')).get('is',[None,0])[1]>5 else [{'keyword':'translate','volume':5,'difficulty':9}])}))
    if change=='fields':
        kwcli(monkeypatch,'price','--fields','volume','--min-volume',0)
        kwcli(monkeypatch,'price','--fields','volume,difficulty','--min-volume',0)
    else:
        kwcli(monkeypatch,'price','--min-volume',10)
        kwcli(monkeypatch,'price','--min-volume',0)
    assert len(calls)==2

@pytest.mark.defect
def test_kw_serp_refreshes_expired_project_entry(cfg,monkeypatch):
    p=project(cfg);dump(p/'priced.json',{'translate|us':{'keyword':'translate','volume':100}})
    calls=fake_ahrefs(monkeypatch,lambda tool,args:api({'positions':[{'type':['organic'],'position':1,'url':'https://other.test/a'}]}))
    kwcli(monkeypatch,'serp')
    con=sqlite3.connect(Path(cfg['data']['dir'])/'ahrefs_cache.sqlite');con.execute("UPDATE c SET day='2000-01-01'");con.commit()
    # Age the real cached response; project summaries have no date to permit a TTL check.
    kwcli(monkeypatch,'serp')
    assert len(calls)==2

@pytest.mark.defect
def test_kw_monthly_cap_reserves_next_call(cfg,monkeypatch):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    cfg['keywords']['monthly_unit_cap']=100
    log=Path(cfg['data']['dir'])/'ahrefs_units.jsonl'
    log.write_text(json.dumps({'ts':dt.date.today().isoformat(),'tool':'fixture','units':99})+'\n')
    calls=fake_ahrefs(monkeypatch,lambda tool,args:api({'keywords':[{'keyword':'translate','volume':10}]},32))
    try:kwcli(monkeypatch,'price')
    except SystemExit:pass
    assert not calls

@pytest.mark.defect
def test_kw_error_cost_is_logged(cfg,monkeypatch):
    project(cfg)
    fake_ahrefs(monkeypatch,lambda tool,args:api_error(500,json.dumps({'error':'Internal Server Error'}),50))
    with pytest.raises(RuntimeError):kwcli(monkeypatch,'discover','--seeds','translate')
    log=Path(cfg['data']['dir'])/'ahrefs_units.jsonl'
    assert log.exists() and sum(json.loads(l)['units'] for l in log.read_text().splitlines())==50

@pytest.mark.defect
def test_kw_api_error_is_not_cached_as_no_data(cfg,monkeypatch):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    calls=fake_ahrefs(monkeypatch,lambda tool,args:api_error(401,json.dumps({'error':'unauthorized'})))
    try:kwcli(monkeypatch,'price')
    except (RuntimeError,SystemExit):pass
    con=sqlite3.connect(Path(cfg['data']['dir'])/'ahrefs_cache.sqlite')
    assert con.execute('SELECT COUNT(*) FROM c').fetchone()[0]==0

@pytest.mark.defect
def test_kw_singleton_transient_error_remains_retryable(cfg,monkeypatch):
    p=project(cfg);dump(p/'candidates.json',{'translate':{'sources':['seed']}})
    attempts=[]
    def fake(tool,args):
        attempts.append(1)
        if len(attempts)==1:raise RuntimeError('429 Too Many Requests')
        return api({'keywords':[{'keyword':'translate','volume':100}]})
    fake_ahrefs(monkeypatch,fake)
    try:kwcli(monkeypatch,'price')
    except RuntimeError:pass
    kwcli(monkeypatch,'price')
    assert len(attempts)==2
    assert json.loads((p/'priced.json').read_text())['translate|us']['volume']==100

def test_kw_poison_batch_split(cfg,monkeypatch):
    p=project(cfg);dump(p/'candidates.json',{k:{'sources':['seed']} for k in ['good','poison','also good']})
    def fake(tool,args):
        if 'poison' in args['keywords']:raise RuntimeError('500 internal server error')
        return api({'keywords':[{'keyword':k,'volume':100} for k in args['keywords'].split(',')]})
    fake_ahrefs(monkeypatch,fake)
    kwcli(monkeypatch,'price')
    priced=json.loads((p/'priced.json').read_text())
    assert priced['good|us']['volume']==100 and priced['also good|us']['volume']==100
    assert priced['poison|us']['no_data_or_below_floor']

def serp_entry(urls,**kwd):return {'urls':urls,'page_types':{'Article':len(urls)},'ai_overview':False,'our_position':None,'our_url':None,**kwd}

def test_kw_union_find_transitive_and_no_serp(cfg,monkeypatch):
    p=project(cfg)
    dump(p/'serps.json',{'a|us':serp_entry(['1','2','3']), 'b|us':serp_entry(['1','2','3','4','5','6']),
        'c|us':serp_entry(['4','5','6']),'empty|us':serp_entry([],no_serp=True)})
    dump(p/'priced.json',{f'{k}|us':{'volume':100,'difficulty':10} for k in ['a','b','c','empty']})
    kwcli(monkeypatch,'cluster');kwcli(monkeypatch,'prioritize')
    rows=json.loads((p/'clusters.json').read_text())
    assert len(rows)==2
    assert any(set(r['keywords'])=={'a','b','c'} for r in rows)
    assert next(r for r in rows if r.get('no_serp'))['action']=='no SERP in Ahrefs: check Google by hand'

@pytest.mark.defect
def test_kw_clustering_does_not_merge_countries(cfg,monkeypatch):
    p=project(cfg);dump(p/'serps.json',{'a|us':serp_entry(['1','2','3']),'a|de':serp_entry(['1','2','3'])})
    dump(p/'priced.json',{'a|us':{'volume':100},'a|de':{'volume':200}})
    try:
        kwcli(monkeypatch,'cluster')
    except SystemExit as e:
        assert e.code
        return
    rows=json.loads((p/'clusters.json').read_text())
    assert len(rows)==2 and {r['country'] for r in rows}=={'us','de'}

def cluster_entry(**extra):
    return {'head':'translate','country':'us','keywords':['translate'],'volume':100,'kd_avg':10,
        'intents':{'commercial':1},'serp_page_types':{'Article':10},'ai_overview':False,
        'our_position':None,'our_url':None,**extra}

@pytest.mark.defect
def test_kw_gsc_join_is_market_specific(cfg,monkeypatch):
    con=archive(cfg);con.execute('DELETE FROM query_daily')
    for country,imp,pos,page in [('usa',100,12,'us'),('deu',10000,1,'de')]:
        con.execute('INSERT INTO query_daily VALUES(?,?,?,?,?,?,?,?)',('2026-04-12','translate','https://example.test/'+page,country,'MOBILE',5,imp,imp*pos))
    con.commit()
    p=project(cfg);dump(p/'clusters.json',[cluster_entry()])
    kwcli(monkeypatch,'prioritize')
    row=json.loads((p/'clusters.json').read_text())[0]
    assert row['gsc_position']==12 and row['action']=='improve existing page (https://example.test/us)'

@pytest.mark.defect
def test_kw_kd_zero_keeps_full_ease(cfg,monkeypatch):
    p=project(cfg);dump(p/'clusters.json',[cluster_entry(kd_avg=0)])
    kwcli(monkeypatch,'prioritize')
    assert json.loads((p/'clusters.json').read_text())[0]['score']==100

@pytest.mark.defect
def test_kw_serp_mix_not_truncated_before_action(cfg,monkeypatch):
    p=project(cfg)
    dump(p/'serps.json',{'translate|us':serp_entry(list(map(str,range(10))),page_types={'App_Store':4,'Article':2,'Landing_Page':1,'Homepage':1,'Product_Page':1,'Other':1})})
    dump(p/'priced.json',{'translate|us':{'volume':100,'difficulty':10}})
    kwcli(monkeypatch,'cluster');kwcli(monkeypatch,'prioritize')
    row=json.loads((p/'clusters.json').read_text())[0]
    assert row['action']!='skip: SERP is app stores'

@pytest.mark.defect
def test_kw_own_position_keeps_matching_url(cfg,monkeypatch):
    p=project(cfg)
    dump(p/'serps.json',{'a|us':serp_entry(['1','2','3'],our_position=9,our_url='https://example.test/a'),
        'b|us':serp_entry(['1','2','3'],our_position=2,our_url='https://example.test/b')})
    dump(p/'priced.json',{'a|us':{'volume':200},'b|us':{'volume':100}})
    kwcli(monkeypatch,'cluster');kwcli(monkeypatch,'prioritize')
    row=json.loads((p/'clusters.json').read_text())[0]
    assert (row['our_position'],row['our_url'])==(2,'https://example.test/b')

@pytest.mark.parametrize('position,expected',[(2,'hold: we already rank top 3'),(12,'improve existing page (https://example.test/a)'),(30,'new article')])
def test_kw_action_rules_real_prioritize(cfg,monkeypatch,position,expected):
    con=archive(cfg)
    con.execute('UPDATE query_daily SET query=?,pos_x_impr=impressions*?',('translate',position));con.commit()
    p=project(cfg);dump(p/'clusters.json',[cluster_entry()])
    kwcli(monkeypatch,'prioritize')
    assert json.loads((p/'clusters.json').read_text())[0]['action']==expected

# render_check.py's CLI with deterministic browser stand-ins. Real Chromium probe is separate.
@pytest.mark.parametrize('mode',['same','changed','timeout'])
def test_render_entry_point_evidence_and_timeout(cfg,monkeypatch,mode):
    folder=crawldb(cfg)
    raw='<html><head><title>Before</title></head><body><h1>A</h1></body></html>'
    class Browser:
        def new_context(self,**k):return self
        def new_page(self):return self
        def goto(self,*a,**k):
            if mode=='timeout':raise RuntimeError('synthetic navigation timeout')
        def wait_for_timeout(self,*a):pass
        def evaluate(self,*a):pass
        def content(self):return raw.replace('Before','After') if mode=='changed' else raw
        def close(self):pass
    class Playwright:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        @property
        def chromium(self):return self
        def launch(self,**k):return Browser()
    monkeypatch.setattr(render,'sync_playwright',lambda:Playwright())
    monkeypatch.setattr(render.httpx if hasattr(render,'httpx') else httpx,'get',lambda *a,**k:Response(text=raw))
    cli(monkeypatch,render,'--crawl',folder)
    row=json.loads((folder/'render.json').read_text())[0]
    if mode=='timeout':assert row['error']=='synthetic navigation timeout'
    else:assert row['differs']==(['title'] if mode=='changed' else [])

@pytest.mark.defect
def test_crawl_malformed_link_cannot_deadlock_queue(cfg,monkeypatch):
    cfg['site']['start_urls']=['https://example.test/','https://example.test/other']
    original=asyncio.run
    class AsyncShim:
        def __getattr__(self,name):return getattr(asyncio,name)
        def run(self,coro):return original(asyncio.wait_for(coro,timeout=0.2))
    monkeypatch.setattr(crawl,'asyncio',AsyncShim())
    db,seen,folder=run_crawl(cfg,monkeypatch,{'https://example.test/':html('<a href="http://[">malformed URL</a>'),
        'https://example.test/other':html('other')})
    assert db.execute('SELECT COUNT(*) FROM pages').fetchone()[0]==2

@pytest.mark.defect
def test_crawl_ttfb_excludes_body_transfer_time(cfg,monkeypatch):
    clock=[0.0]
    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            clock[0]+=2.0
            yield b'<html><body>large body</body></html>'
    async def handler(request):
        if request.url.path=='/robots.txt':return httpx.Response(200,text='')
        clock[0]+=0.01 # headers arrive in 10 ms
        return httpx.Response(200,headers={'content-type':'text/html'},stream=Stream())
    original=httpx.AsyncClient
    # Use real httpx buffering behavior, replacing only its transport.
    def client(*a,**k):return original(*a,transport=httpx.MockTransport(handler),**k)
    # The test-wide request blocker is replaced with the original method for this transport only.
    monkeypatch.setattr(httpx.AsyncClient,'request',ORIGINAL_ASYNC_REQUEST)
    monkeypatch.setattr(crawl.httpx,'AsyncClient',client)
    monkeypatch.setattr(crawl,'time',types.SimpleNamespace(monotonic=lambda:clock[0],time=lambda:clock[0]))
    cli(monkeypatch,crawl,'--delay',0,'--concurrency',1)
    folder=Path(cfg['data']['dir'])/'crawls/latest'
    db=sqlite3.connect(folder/'crawl.sqlite')
    assert db.execute('SELECT ttfb_ms FROM pages').fetchone()[0]<100

@pytest.mark.parametrize('name',['coverage','decay','new_queries','page_map','brand','countries','devices','questions','update_impact'])
def test_recipe_numeric_contracts(cfg,monkeypatch,capsys,name):
    con=archive(cfg)
    if name=='coverage':
        con.execute('UPDATE query_daily SET clicks=5');con.commit()
    if name=='decay':
        con.execute("UPDATE page_daily SET clicks=8 WHERE date BETWEEN '2026-04-06' AND '2026-04-12'");con.commit()
    if name=='new_queries':
        con.execute("DELETE FROM query_daily WHERE date < '2026-04-06'");con.commit()
    rows=recipe(monkeypatch,capsys,name,'--end','2026-04-12','--days',7,'--date','2026-03-01')
    if name=='coverage':assert rows[0]['click_coverage_pct']==50
    if name=='decay':assert (rows[0]['clicks_prev'],rows[0]['clicks_now'],rows[0]['clicks_change_pct'])==(70,56,-20)
    if name=='new_queries':assert (rows[0]['impressions'],rows[0]['clicks'],rows[0]['position'])==(700,70,8)
    if name=='page_map':assert (rows[0]['queries'],rows[0]['clicks_without_query_pct'])==(1,0)
    if name=='brand':assert next(r for r in rows if r['week']=='2026-W15')['non-brand_clicks']==70
    if name in ('countries','devices'):assert (rows[0]['clicks'],rows[0]['ctr_pct'],rows[0]['position'])==(70,10,8)
    if name=='questions':assert (rows[0]['query'],rows[0]['clicks'])==('how translate',70)
    if name=='update_impact':assert (rows[0]['clicks_before'],rows[0]['clicks_after'])==(70,70)

@pytest.mark.parametrize('recipe_name',['coverage','striking','decay','countries'])
def test_empty_archive_stops(cfg,monkeypatch,recipe_name):
    with pytest.raises(SystemExit,match='Archive is empty'):
        cli(monkeypatch,recipes,recipe_name)

@pytest.mark.defect
def test_report_does_not_treat_incomplete_comparison_as_full_week(cfg,monkeypatch):
    con=archive(cfg)
    con.execute("DELETE FROM pull_log WHERE date='2026-04-01'")
    con.execute("DELETE FROM site_daily WHERE date='2026-04-01'");con.commit()
    try:
        cli(monkeypatch,report,'--week','2026-W15','--no-sheet','--no-conversions')
    except SystemExit as e:
        assert e.code
        return
    result=json.loads((Path(cfg['data']['dir'])/'reports/2026-W15.json').read_text())
    # Either refuse the comparison or mark it unavailable; it must not be a full-week baseline.
    assert result['prev_week'].get('complete') is False or result['prev_week'].get('clicks') is None

@pytest.mark.defect
def test_kw_gsc_join_uses_exactly_90_final_days(cfg,monkeypatch):
    con=archive(cfg,start='2026-01-01',end='2026-04-12')
    con.execute("UPDATE query_daily SET query='translate'")
    pull.store(con,{'day':'2026-04-13','final':0,'site':[],'pages':[],
        'queries':[{'keys':['translate','https://example.test/a','usa','MOBILE'],'clicks':1,'impressions':100000,'position':1}]})
    con.commit()
    p=project(cfg);dump(p/'clusters.json',[cluster_entry()])
    kwcli(monkeypatch,'prioritize')
    row=json.loads((p/'clusters.json').read_text())[0]
    assert (row['gsc_impressions_90d'],row['gsc_position'])==(9000,8)

@pytest.mark.defect
def test_brand_retains_all_hidden_week(cfg,monkeypatch,capsys):
    con=archive(cfg);con.execute("DELETE FROM query_daily WHERE date BETWEEN '2026-04-06' AND '2026-04-12'");con.commit()
    rows=recipe(monkeypatch,capsys,'brand','--end','2026-04-12','--days',7)
    assert any(r['week']=='2026-W15' and r['hidden_clicks']==70 for r in rows)

@pytest.mark.defect
def test_locale_root_querystring_not_cannibalized_with_default(cfg,monkeypatch,capsys):
    con=archive(cfg);con.execute('DELETE FROM query_daily')
    for page in ['https://example.test/es?x=1','https://example.test/a']:
        con.execute('INSERT INTO query_daily VALUES(?,?,?,?,?,?,?,?)',('2026-04-12','translate',page,'usa','MOBILE',5,100,800))
    con.commit()
    assert recipe(monkeypatch,capsys,'cannibal','--end','2026-04-12')==[]

@pytest.mark.defect
def test_audit_variant_redirect_must_reach_configured_canonical_host(cfg,monkeypatch):
    con=archive(cfg);con.execute("UPDATE page_daily SET page='http://example.test/a'");con.commit()
    folder=crawldb(cfg)
    monkeypatch.setattr(audit.httpx,'get',lambda *a,**k:Response(status=301,headers={'location':'http://example.test/a'}))
    fs=run_audit(monkeypatch,folder)
    assert any(f['rule']=='R10' for f in fs)

@pytest.mark.defect
def test_audit_hreflang_exposure_uses_real_urls(cfg,monkeypatch):
    archive(cfg)
    folder=crawldb(cfg,[{'hreflang':json.dumps([{'lang':'en','href':'https://example.test/a'},{'lang':'es','href':'https://example.test/es/b'}])},
        {'url':'https://example.test/es/b','canonical':'https://example.test/es/b','html_lang':'es'}])
    fs=run_audit(monkeypatch,folder)
    f=next(f for f in fs if f['title']=='hreflang: missing return link')
    assert f['priority']=='P2' and f['gsc_clicks_28d']==280
    assert 'https://example.test/a' in f['urls']

@pytest.mark.defect
def test_audit_exposure_not_double_counted_by_url_aliases(cfg,monkeypatch):
    con=archive(cfg,clicks=1)
    folder=crawldb(cfg,[{'url':'https://example.test/a','title':None},
        {'url':'https://example.test/a/','title':None,'canonical':'https://example.test/a/'}])
    fs=run_audit(monkeypatch,folder)
    f=next(f for f in fs if f['rule']=='R11')
    assert (f['gsc_clicks_28d'],f['priority'])==(28,'P3')

@pytest.mark.parametrize('rule,extra',[
    ('R02',{'redirect_chain':json.dumps([{'url':'/a','status':301},{'url':'/b','status':301},{'url':'/c','status':200}])}),
    ('R04',{'in_sitemap':0}),('R05',{'meta_robots':'noindex'}),('R06',{'canonical':None}),
    ('R11',{'title':None}),('R11b',{'title':'short'}),('R12',{'meta_description':None}),
    ('R13',{'h1':'[]'}),('R14',{'word_count':249}),('R15',{'images':3,'images_no_alt':3}),
    ('R16',{'jsonld_types':'["INVALID_JSON"]'}),('R18',{'ttfb_ms':1001})])
def test_audit_rule_positive_controls(cfg,monkeypatch,rule,extra):
    folder=crawldb(cfg,[extra])
    assert any(f['rule']==rule for f in run_audit(monkeypatch,folder))

def test_audit_supplemental_rule_positive_controls(cfg,monkeypatch):
    cfg['site']['excluded_hosts']=['app.example.test']
    folder=crawldb(cfg,[{'status':404,'redirect_chain':'[]'}],
        [('https://example.test/a','https://example.test/a?utm_source=x','tracking',0,1)])
    db=sqlite3.connect(folder/'crawl.sqlite');db.execute('INSERT INTO sitemap_urls VALUES(?,?,?)',('map','https://example.test/a',None));db.commit()
    dump(folder/'bing.json',{'excluded_host_pages':[{'url':'https://app.example.test/','impressions':2}], 'crawl_issues':[{'Url':'https://example.test/b'}]})
    dump(folder/'cwv.json',{'origins':{'https://example.test':{'PHONE':{'largest_contentful_paint':{'p75':5000,'rating':'poor'}}}}})
    dump(folder/'render.json',[{'url':'https://example.test/a','differs':['title'],'raw':{'title':'x'},'rendered':{'title':'y'}}])
    (folder/'robots_example.test.txt').write_text('User-agent: *\nDisallow: /')
    rules={f['rule'] for f in run_audit(monkeypatch,folder)}
    assert {'R03','R08','R09','R18b','R19','R20','R21'}<=rules
