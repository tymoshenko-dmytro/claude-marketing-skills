"""Tests for gsc-insights weekly_digest.py and seo-tech-audit backlog.py, in the Russian output language
([report].language = "ru", a feature). Offline: BigQuery, Bing and Sheets are stand-ins."""
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2] / "skills"  # the repo's skills/ folder


def module(name, skill):
    d = ROOT / skill / "scripts"
    sys.path.insert(0, str(d))
    spec = importlib.util.spec_from_file_location(name, d / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


digest = module("weekly_digest", "gsc-insights")
backlog = module("backlog", "seo-tech-audit")


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    c = {"site": {"name": "t", "hosts": ["example.test"], "gsc_property": "sc-domain:example.test", "locales": []},
         "data": {"dir": str(tmp_path)}, "brand": {"patterns": [], "ambiguous": []},
         "report": {"language": "ru", "trend_weeks": 2}, "digest": {"sources_sql": str(tmp_path / "s.sql")},
         "conversions": {"bq_project": "p"}}
    (tmp_path / "s.sql").write_text("SELECT {{start}} {{end}}")
    monkeypatch.setattr(digest.seoconf, "load", lambda *a: c)
    monkeypatch.setattr(backlog.seoconf, "load", lambda *a: c)
    return c


def run(monkeypatch, mod, *args):
    monkeypatch.setattr(sys, "argv", [mod.__name__, *map(str, args)])
    return mod.main()


@pytest.mark.parametrize("n,form", [(1, "триал"), (2, "триала"), (5, "триалов"), (11, "триалов"), (21, "триал"),
                                    (22, "триала"), (112, "триалов"), (0, "триалов")])
def test_plural(n, form):
    assert digest.plural(n, "триал", "триала", "триалов") == form


@pytest.mark.parametrize("now,prev,out", [(110, 100, "+10%"), (90, 100, "−10%"), (100, 100, "0%"),
                                          (5, 0, "новое"), (0, 0, "0%"), (5, None, "н/д")])
def test_change(now, prev, out):
    assert digest.chg(now, prev, "ru") == out


def finding(rule, title, count=3, prio="P2"):
    return {"rule": rule, "title": title, "priority": prio, "severity": "high", "count": count, "urls": ["u"],
            "gsc_clicks_28d": 5, "exposure_complete": True, "owner": "Frontend"}


def test_backlog_status_cycle():
    st = {}
    s1 = backlog.update(st, [finding("R01", "a"), finding("R08", "b")], "2026-10-06", "ru")
    assert len(s1["new"]) == 2 and st["items"]["R01|a"]["status"] == "new"
    s2 = backlog.update(st, [finding("R01", "a", 2)], "2026-10-13", "ru")
    assert st["items"]["R01|a"]["status"] == "open" and s2["fixed"] == ["R08|b"]
    assert st["items"]["R01|a"]["history"] == [["2026-10-06", 3], ["2026-10-13", 2]]
    s3 = backlog.update(st, [finding("R01", "a"), finding("R08", "b")], "2026-10-20", "ru")
    assert s3["reopened"] == ["R08|b"] and "fixed_on" not in st["items"]["R08|b"]
    assert next(t for t in s3["top"] if t["id"] == "R01|a")["weeks_open"] == 3
    assert st["items"]["R01|a"]["title"] == "Внутренние ссылки ведут на страницы с ошибкой"


def test_backlog_ignores_info_and_same_day_rerun_keeps_new():
    st = {}
    backlog.update(st, [finding("R01", "a"), finding("R20", "x", prio="info")], "2026-10-06", "ru")
    assert list(st["items"]) == ["R01|a"]
    backlog.update(st, [finding("R01", "a")], "2026-10-06", "ru")
    assert st["items"]["R01|a"]["status"] == "new" and len(st["items"]["R01|a"]["history"]) == 1


def test_backlog_translates_index_state():
    f = finding("R07", "Indexable pages not in Google's index: Crawled - currently not indexed")
    assert backlog.title_for(f, "ru").endswith("просканированы, но не проиндексированы")


def test_backlog_sheet_keeps_owner_and_comment(cfg, monkeypatch, tmp_path):
    crawl = tmp_path / "crawl"
    crawl.mkdir()
    (crawl / "findings.json").write_text(json.dumps({"findings": [finding("R01", "a")]}))
    written = {}

    class Sheet:
        def __init__(self, *a):
            pass

        def ensure_tab(self, t):
            pass

        def read(self, t):
            h = ["ID", "Комментарий", "Ответственный"]  # an older or reordered layout: columns are found by name
            return [h, ["R01|a", "в работе", "Команда сайта"]]

        def overwrite(self, t, rows):
            written[t] = rows

    cfg["report"]["sheet_id"] = "s"
    sys.modules["sheets"] = type(sys)("sheets")
    sys.modules["sheets"].Sheet = Sheet
    run(monkeypatch, backlog, "--crawl", crawl, "--date", "2026-10-13")
    h = written["Бэклог аудита"][0]
    row = written["Бэклог аудита"][1]
    assert row[0] == "R01|a" and row[h.index("Ответственный")] == "Команда сайта" and row[h.index("Комментарий")] == "в работе"
    assert row[h.index("Что сделать")].startswith("Для каждого адреса")
    urls = written["Адреса аудита"]
    assert urls[0][3] == "Адрес" and urls[1][0] == "R01|a"


def test_sitemap_reason_explains_same_post_in_two_sections():
    import backlog_details as bd
    u = "https://blog.example.test/cat-a/post-x/"
    f = {"rule": "R03", "urls": [u], "evidence": {}}
    pages = {u: {"status": 200, "canonical": "https://blog.example.test/cat-b/post-x/", "meta_robots": "index, follow"}}
    r = bd.url_reasons(f, pages, {}, {}, "ru")[0][1]
    assert "canonical страницы ведёт на https://blog.example.test/cat-b/post-x/" in r and "другой рубрике" in r


def test_cwv_reason_is_readable():
    import backlog_details as bd
    f = {"rule": "R18b", "urls": ["https://blog.example.test PHONE largest_contentful_paint"],
         "evidence": {"https://blog.example.test PHONE largest_contentful_paint": {"p75": 3080, "rating": "needs improvement"}}}
    assert bd.url_reasons(f, {}, {}, {}, "ru")[0][1] == "LCP, загрузка главного блока (телефоны): 3080 мс у 75% визитов, нужно улучшить"


def rows_for(weeks, days=7):
    out = []
    for w in weeks:
        out.append({"week": w, "channel": "_days", "sessions": str(days), "registrations": "0", "trials": "0"})
        for ch, s, r, t in (("Google", 1000, 100, 10), ("AI assistants", 100, 20, 5), ("Bing", 50, 5, 1), ("Other search", 20, 0, 0)):
            out.append({"week": w, "channel": ch, "sessions": str(s), "registrations": str(r), "trials": str(t)})
    return out


def test_digest_stops_on_incomplete_ga4_week(cfg, monkeypatch):
    monkeypatch.setattr(digest, "bq_rows", lambda *a: rows_for(["2026-W40"], 7) + [
        {"week": "2026-W41", "channel": "_days", "sessions": "6", "registrations": "0", "trials": "0"}])
    with pytest.raises(SystemExit, match="6/7"):
        run(monkeypatch, digest, "--week", "2026-W41", "--no-sheet", "--no-bing")


def test_digest_text_and_files(cfg, monkeypatch, tmp_path):
    monkeypatch.setattr(digest, "bq_rows", lambda *a: rows_for(["2026-W40", "2026-W41"]))
    import gsc_report
    monkeypatch.setattr(gsc_report, "conversions", lambda *a: (None, "skipped"))
    run(monkeypatch, digest, "--week", "2026-W41", "--no-sheet", "--no-bing")
    rep = tmp_path / "reports"
    text = (rep / "2026-W41.digest.md").read_text()
    assert "1 170 визитов (0%)" in text and "125 регистраций" in text and "16 триалов" in text
    assert "| ИИ-ассистенты | 100 | 0% | 20 | 5 | 5,0% |" in text and "| Другие поисковики | 20 | 0% | 0 | 0 | 0% |" in text
    assert "{{ACTIONS}}" in text and "Search Console ещё не закрыл" in text
    assert (rep / "2026-W41.trend.png").stat().st_size > 10_000
    data = json.loads((rep / "2026-W41.digest.json").read_text())
    assert data["totals"] == {"sessions": 1170, "registrations": 125, "trials": 16}
