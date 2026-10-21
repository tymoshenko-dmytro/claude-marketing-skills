"""Ahrefs transports of the ahrefs skill: API v3 (ahrefs_api.py, kw.py --via api) with a stand-in HTTP layer, and
the MCP path (kw.py --via mcp + kw.py import) with saved tool outputs. No network, no real keys."""
import importlib.util
import json
import sqlite3
import urllib.parse
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('r1', str(Path(__file__).resolve().parent / 'test_cli_round1.py'))
r1 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r1)
cfg, offline = r1.cfg, r1.offline
cli, project, dump, kwcli, fake_ahrefs, api, api_error = r1.cli, r1.project, r1.dump, r1.kwcli, r1.fake_ahrefs, r1.api, r1.api_error
kw = r1.kw
ahrefs_api = kw.ahrefs_api


def units_log(cfg):
    p = Path(cfg['data']['dir']) / 'ahrefs_units.jsonl'
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


@pytest.fixture
def no_key(monkeypatch, tmp_path):
    monkeypatch.delenv('AHREFS_API_KEY', raising=False)
    monkeypatch.setattr(ahrefs_api, 'KIT_ENV', str(tmp_path / 'missing.env'))
    monkeypatch.setattr(ahrefs_api, 'UNITS_LOG', str(tmp_path / 'raw-units.jsonl'))

    def http(*a, **k):
        raise AssertionError('the MCP path must not call the API')
    monkeypatch.setattr(ahrefs_api, 'http', http)


# ---------- API v3 transport ----------

@pytest.mark.parametrize('name,path', [
    ('serp-overview', 'serp-overview/serp-overview'),
    ('batch-analysis', 'batch-analysis/batch-analysis'),
    ('site-explorer-referring-domains', 'site-explorer/refdomains'),
    ('site-explorer-linked-domains', 'site-explorer/linkeddomains'),
    ('site-explorer-organic-keywords', 'site-explorer/organic-keywords'),
    ('keywords-explorer-matching-terms', 'keywords-explorer/matching-terms'),
    ('subscription-info-limits-and-usage', 'subscription-info/limits-and-usage'),
    ('rank-tracker-serp-overview', 'rank-tracker/serp-overview'),
    ('brand-radar-ai-responses', 'brand-radar/ai-responses'),
    ('gsc-keywords', 'gsc/keywords'),
    ('site-explorer/top-pages', 'site-explorer/top-pages'),
    ('/v3/keywords-explorer/overview', 'keywords-explorer/overview')])
def test_endpoint_path_from_tool_name(name, path):
    assert ahrefs_api.api_path(name) == path


@pytest.mark.parametrize('name', ['doc', 'render-data-table'])
def test_mcp_only_tool_has_no_endpoint(name):
    with pytest.raises(SystemExit, match='MCP-only'):
        ahrefs_api.api_path(name)


@pytest.mark.parametrize('headers,expected', [
    ({'x-api-units-cost-total-actual': '57', 'x-api-units-cost-total': '60'}, (57, True)),
    ({'x-api-units-cost-total': '60'}, (60, True)),
    ({}, (0, False))])
def test_units_come_from_documented_headers(headers, expected):
    assert ahrefs_api.Response(200, headers, '{}', 'x/y').units() == expected


def test_key_from_kit_file_with_inline_comment(monkeypatch, tmp_path):
    monkeypatch.delenv('AHREFS_API_KEY', raising=False)
    env = tmp_path / 'kit.env'
    env.write_text('OTHER=1\nAHREFS_API_KEY="fixture-key-1"   # API v3 key\n')
    monkeypatch.setattr(ahrefs_api, 'KIT_ENV', str(env))
    assert ahrefs_api.api_key() == 'fixture-key-1'
    monkeypatch.setenv('AHREFS_API_KEY', 'fixture-env-wins')
    assert ahrefs_api.api_key() == 'fixture-env-wins'


def test_missing_key_names_key_file_and_guide(no_key):
    with pytest.raises(SystemExit) as e:
        ahrefs_api.api_key()
    assert 'AHREFS_API_KEY' in str(e.value) and 'missing.env' in str(e.value) and 'connections/ahrefs-mcp.md' in str(e.value)
    assert ahrefs_api.api_key(required=False) is None


def test_lookup_cli_saves_answer_and_logs_units(monkeypatch, tmp_path, capsys):
    seen = []
    monkeypatch.setenv('AHREFS_API_KEY', 'fixture-key')
    monkeypatch.setattr(ahrefs_api, 'UNITS_LOG', str(tmp_path / 'raw' / 'units.jsonl'))

    def http(method, url, headers, body=None, timeout=None):
        seen.append((method, url, headers))
        return 200, {'x-api-units-cost-total-actual': '50', 'x-api-cache': 'miss'}, json.dumps({'domain_rating': {'domain_rating': 71}})
    monkeypatch.setattr(ahrefs_api, 'http', http)
    out = tmp_path / 'raw' / 'dr.json'
    ahrefs_api.main(['site-explorer-domain-rating', 'target=example.com', 'date=2026-09-30', '--out', str(out)])
    method, url, headers = seen[0]
    parts = urllib.parse.urlsplit(url)
    assert method == 'GET' and parts.path == '/v3/site-explorer/domain-rating'
    assert dict(urllib.parse.parse_qsl(parts.query)) == {'target': 'example.com', 'date': '2026-09-30'}
    assert headers['Authorization'] == 'Bearer fixture-key'
    assert json.loads(out.read_text())['domain_rating']['domain_rating'] == 71
    rec = json.loads((tmp_path / 'raw' / 'units.jsonl').read_text())
    assert rec['tool'] == 'site-explorer-domain-rating' and rec['units'] == 50 and rec['via'] == 'ahrefs_api.py'
    assert 'units: 50' in capsys.readouterr().err


def test_lookup_cli_post_body(monkeypatch, tmp_path):
    seen = []
    monkeypatch.setenv('AHREFS_API_KEY', 'fixture-key')
    monkeypatch.setattr(ahrefs_api, 'UNITS_LOG', str(tmp_path / 'units.jsonl'))
    monkeypatch.setattr(ahrefs_api, 'http', lambda m, u, h, b=None, timeout=None: seen.append((m, u, h, b)) or (200, {}, '{"targets": []}'))
    ahrefs_api.main(['batch-analysis', '--body', '{"targets": [{"url": "example.com"}]}'])
    m, u, h, b = seen[0]
    assert m == 'POST' and u.endswith('/v3/batch-analysis/batch-analysis') and h['Content-Type'] == 'application/json'
    assert json.loads(b) == {'targets': [{'url': 'example.com'}]}
    assert json.loads((tmp_path / 'units.jsonl').read_text())['units_unreported'] is True


def test_lookup_cli_401_explains_key_type(monkeypatch, tmp_path):
    monkeypatch.setenv('AHREFS_API_KEY', 'fixture-key')
    monkeypatch.setattr(ahrefs_api, 'UNITS_LOG', str(tmp_path / 'units.jsonl'))
    monkeypatch.setattr(ahrefs_api, 'http', lambda *a, **k: (401, {}, '{"error":"unauthorized"}'))
    with pytest.raises(SystemExit, match='MCP keys do not work on API v3'):
        ahrefs_api.main(['subscription-info/limits-and-usage'])


def test_rate_limit_is_retried_once_after_retry_after(monkeypatch):
    waits, answers = [], [(429, {'retry-after': '3'}, 'slow down'), (200, {}, '{"limits_and_usage": {}}')]
    monkeypatch.setattr(ahrefs_api, 'http', lambda *a, **k: answers.pop(0))
    monkeypatch.setattr(ahrefs_api, '_sleep', waits.append)
    r = ahrefs_api.call('subscription-info-limits-and-usage', {}, key='fixture-key')
    assert r.ok and waits == [3.0] and not answers


def test_kw_logs_missing_unit_header_as_unreported(cfg, monkeypatch):
    project(cfg)
    fake_ahrefs(monkeypatch, lambda tool, args: (200, {}, json.dumps({'keywords': [{'keyword': 'translate audio'}]})))
    kwcli(monkeypatch, 'discover', '--seeds', 'translate', '--via', 'api')
    rec = units_log(cfg)[0]
    assert rec['units'] == 0 and rec['units_unreported'] is True


def test_kw_api_error_redacts_key_and_explains_401(cfg, monkeypatch):
    project(cfg)
    fake_ahrefs(monkeypatch, lambda tool, args: api_error(401, 'bad token ' + r1.API_KEY))
    with pytest.raises(RuntimeError) as e:
        kwcli(monkeypatch, 'discover', '--seeds', 'translate', '--via', 'api')
    assert r1.API_KEY not in str(e.value) and 'wrong key type' in str(e.value)
    assert r1.API_KEY not in json.dumps(units_log(cfg))


# ---------- MCP path: plan, import, same results ----------

def mcp_text(data, units=None):
    """What the Ahrefs MCP tool returns: text blocks with the data and, usually, the unit cost."""
    blocks = [{'type': 'text', 'text': json.dumps(data)}]
    if units is not None:
        blocks.append({'type': 'text', 'text': json.dumps({'apiUsageCosts': {'units-cost-total-actual': units}})})
    return blocks


def plan_calls(cfg, stage):
    plan = json.loads((project(cfg) / 'mcp_plan.json').read_text())['calls']
    return [c for c in plan if c['id'].startswith(stage + '-')]


def test_mcp_pipeline_discover_price_serp_cluster_prioritize(cfg, monkeypatch, tmp_path, no_key, capsys):
    out = tmp_path / 'outputs'
    out.mkdir()
    # discover: seeds are kept, the Ahrefs call is planned, not made
    kwcli(monkeypatch, 'discover', '--seeds', 'translate', '--per-seed', 50)
    calls = plan_calls(cfg, 'discover')
    assert [c['tool'] for c in calls] == ['keywords-explorer-matching-terms']
    assert calls[0]['arguments'] == {'keywords': 'translate', 'country': 'us', 'limit': 50, 'select': 'keyword'}
    assert 'kw.py import --project topic --call <id>' in capsys.readouterr().out
    # the agent saved the tool's raw output (data + units in two text blocks)
    f = out / 'discover.json'
    f.write_text(json.dumps(mcp_text({'keywords': [{'keyword': k} for k in
                                                   ['translate audio', 'translate video', 'translate pdf', 'translate x',
                                                    'translate y', 'translate z']]}, 50)))
    kwcli(monkeypatch, 'import', '--call', calls[0]['id'], str(f))
    cand = json.loads((project(cfg) / 'candidates.json').read_text())
    assert cand['translate']['sources'] == ['seed'] and cand['translate pdf']['sources'] == ['matching:translate']
    assert len(cand) == 7
    # importing the same file again changes nothing and logs no units
    kwcli(monkeypatch, 'import', '--call', calls[0]['id'], str(f))
    assert [r['units'] for r in units_log(cfg)] == [50]
    # discover again: the answer is cached, nothing left to plan
    capsys.readouterr()
    kwcli(monkeypatch, 'discover', '--seeds', 'translate', '--per-seed', 50)
    assert 'MCP plan' not in capsys.readouterr().out

    # price: batches of 5 by default for MCP
    kwcli(monkeypatch, 'price', '--fields', 'volume,difficulty', '--min-volume', 10)
    batches = plan_calls(cfg, 'price')
    assert [len(c['arguments']['keywords'].split(',')) for c in batches] == [5, 2]
    assert batches[0]['arguments']['keywords'].split(',')[0] == 'translate'  # seeds are priced first
    vols = {'translate': 900, 'translate audio': 300, 'translate video': 200, 'translate pdf': 100, 'translate x': 50}
    for i, c in enumerate(batches):
        rows = [{'keyword': k, 'volume': vols[k], 'difficulty': 20} for k in c['arguments']['keywords'].split(',') if k in vols]
        f = out / f'price{i}.json'
        if i == 0:  # a wrapper with the arguments, units unknown -> documented estimate
            f.write_text(json.dumps({'tool': 'mcp__ahrefs__keywords-explorer-overview', 'arguments': c['arguments'],
                                     'result': {'keywords': rows}}))
            kwcli(monkeypatch, 'import', str(f))
        else:  # the bare data the tool printed, matched to the plan by --call
            f.write_text(json.dumps({'keywords': rows}) + '\n' + json.dumps({'apiUsageCosts': {'units-cost-total-actual': 50}}))
            kwcli(monkeypatch, 'import', '--call', c['id'], str(f))
    priced = json.loads((project(cfg) / 'priced.json').read_text())
    assert priced['translate audio|us']['volume'] == 300 and priced['translate y|us']['no_data_or_below_floor']
    assert priced['translate|us']['_req'] == {'fields': ['difficulty', 'volume'], 'floor': 10}
    est = [r for r in units_log(cfg) if r.get('units_estimated')]
    assert len(est) == 1 and est[0]['units'] == max(50, 21 * 5) and est[0]['units_unreported'] is True
    capsys.readouterr()
    kwcli(monkeypatch, 'price', '--fields', 'volume,difficulty', '--min-volume', 10)
    assert 'MCP plan' not in capsys.readouterr().out  # all fresh

    # serp
    kwcli(monkeypatch, 'serp', '--min-volume', 100)
    serps = plan_calls(cfg, 'serp')
    assert [c['arguments']['keyword'] for c in serps] == ['translate', 'translate audio', 'translate video', 'translate pdf']
    shared = ['https://a.test/1', 'https://b.test/2', 'https://c.test/3']
    for i, c in enumerate(serps):
        urls = shared + [f'https://other.test/{i}'] if i < 3 else [f'https://solo.test/{n}' for n in range(4)]
        positions = [{'position': n + 1, 'url': u, 'type': ['organic'], 'page_type': '/Article/How_to'} for n, u in enumerate(urls)]
        f = out / f'serp{i}.json'
        f.write_text(json.dumps({'content': mcp_text({'positions': positions}, 60)}))
        kwcli(monkeypatch, 'import', '--call', c['id'], str(f))
    capsys.readouterr()
    kwcli(monkeypatch, 'serp', '--min-volume', 100)
    assert 'MCP plan' not in capsys.readouterr().out
    kwcli(monkeypatch, 'cluster')
    kwcli(monkeypatch, 'prioritize')
    clusters = json.loads((project(cfg) / 'clusters.json').read_text())
    assert len(clusters) == 2 and clusters[0]['keywords'] == ['translate', 'translate audio', 'translate video']
    assert clusters[0]['action'] == 'new article'
    assert (project(cfg) / 'report.md').exists()


def test_mcp_import_feeds_the_api_cache(cfg, monkeypatch, tmp_path, no_key):
    p = project(cfg)
    dump(p / 'candidates.json', {'translate': {'sources': ['seed']}})
    kwcli(monkeypatch, 'price', '--fields', 'volume', '--min-volume', 0, '--batch', 20)
    call = plan_calls(cfg, 'price')[0]
    f = tmp_path / 'out.json'
    f.write_text(json.dumps(mcp_text({'keywords': [{'keyword': 'translate', 'volume': 100}]}, 50)))
    kwcli(monkeypatch, 'import', '--call', call['id'], str(f))
    calls = fake_ahrefs(monkeypatch, lambda *a: api({'keywords': []}))
    kwcli(monkeypatch, 'price', '--fields', 'volume', '--min-volume', 0, '--via', 'api')
    assert calls == []  # the same request is already answered


@pytest.mark.parametrize('content', [
    {'keywords': [{'volume': 100}]},
    {'keywords': [{'keyword': 'translate', 'volume': 'broken'}]},
    {'isError': True, 'content': [{'type': 'text', 'text': 'Internal server error'}]}])
def test_mcp_import_rejects_unusable_output(cfg, monkeypatch, tmp_path, no_key, content):
    p = project(cfg)
    dump(p / 'candidates.json', {'translate': {'sources': ['seed']}})
    kwcli(monkeypatch, 'price', '--fields', 'volume')
    call = plan_calls(cfg, 'price')[0]
    f = tmp_path / 'out.json'
    f.write_text(json.dumps(content))
    with pytest.raises(SystemExit, match='nothing imported'):
        kwcli(monkeypatch, 'import', '--call', call['id'], str(f))
    assert not (p / 'priced.json').exists() or json.loads((p / 'priced.json').read_text()) == {}
    assert units_log(cfg) == []
    con = sqlite3.connect(Path(cfg['data']['dir']) / 'ahrefs_cache.sqlite')
    assert con.execute('SELECT COUNT(*) FROM c').fetchone()[0] == 0


def test_mcp_import_needs_to_know_the_call(cfg, monkeypatch, tmp_path, no_key):
    project(cfg)
    f = tmp_path / 'out.json'
    f.write_text(json.dumps({'keywords': [{'keyword': 'translate'}]}))
    with pytest.raises(SystemExit, match='say which call'):
        kwcli(monkeypatch, 'import', str(f))
    kwcli(monkeypatch, 'import', '--tool', 'keywords-explorer-related-terms', '--args',
          '{"keywords": "translate", "country": "us", "select": "keyword"}', str(f))
    assert json.loads((project(cfg) / 'candidates.json').read_text())['translate']['sources'] == ['related:translate', 'seed']


def test_mcp_plan_respects_monthly_cap(cfg, monkeypatch, no_key):
    p = project(cfg)
    dump(p / 'candidates.json', {k: {'sources': ['seed']} for k in ['a', 'b', 'c']})
    cfg['keywords']['monthly_unit_cap'] = 60
    with pytest.raises(SystemExit, match='unit cap'):
        kwcli(monkeypatch, 'price', '--fields', 'volume,difficulty')
    assert not (p / 'mcp_plan.json').exists()


def test_budget_without_key_points_to_mcp_tool(cfg, monkeypatch, no_key, capsys):
    kwcli(monkeypatch, 'budget')
    assert 'subscription-info-limits-and-usage' in capsys.readouterr().out
