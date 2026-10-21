"""Plain-language task details for the audit backlog: what is wrong, why it matters, what to do, how to check,
and a specific reason for every affected URL (from the crawl, URL Inspection and GSC exposure).

Written for the people who fix things (developers, content editors), not for SEO specialists. Russian texts are
used when [report].language = "ru"; otherwise the English why/fix from audit.py.
"""
from __future__ import annotations

import json
import urllib.parse

RU = {
    "R01": ("На сайте есть ссылки, которые ведут на страницы с ошибкой (404 или 5xx).",
            "Посетитель упирается в ошибку, а Google тратит обход на пустые страницы.",
            "Для каждого адреса: починить страницу, или поставить 301-редирект на ближайшую живую страницу, или убрать ссылку. Где стоят ссылки, указано на вкладке «Адреса аудита».",
            "Открыть адрес: страница отвечает 200, или ссылок на неё больше нет."),
    "R02": ("Адрес ведёт на конечную страницу через несколько редиректов подряд.",
            "Каждый шаг замедляет загрузку, и часть ссылочного веса теряется.",
            "Сделать один редирект сразу на конечный адрес. Цепочка по каждому адресу — на вкладке «Адреса аудита».",
            "Первый адрес отдаёт 301 сразу на конечную страницу."),
    "R02b": ("Внутренние ссылки ведут на адреса, которые редиректят.",
             "Лишний шаг для пользователя и для Google.",
             "Заменить ссылку на конечный адрес.",
             "Ссылка ведёт прямо на страницу с ответом 200."),
    "R03": ("В сайтмапе стоят адреса, которые Google не должен индексировать: редирект, ошибка, noindex или canonical на другой адрес.",
            "Сайтмап говорит Google «индексируй это», а страница говорит обратное. Смешанный сигнал, обход тратится впустую.",
            "Оставить в сайтмапе только главные адреса страниц. Если статья открывается по двум адресам (например, пост в двух рубриках), сайтмап и canonical должны указывать на один и тот же адрес; второй адрес — 301 на главный.",
            "В сайтмапе нет этого адреса, или адрес совпадает с canonical страницы."),
    "R04": ("Страница открывается и может индексироваться, но её нет в сайтмапе.",
            "Google находит такие страницы позже и проверяет реже.",
            "Добавить страницу в сайтмап. Если она не нужна в поиске — поставить noindex.",
            "Адрес есть в сайтмапе или на странице стоит noindex."),
    "R05": ("На страницах стоит noindex: Google их не показывает.",
            "Для служебных страниц это правильно, для продуктовых — потеря трафика.",
            "Пройтись по списку. Где страница должна быть в поиске — убрать noindex. Остальные оставить.",
            "Нужные страницы без noindex; в «Комментарий» отметить, что остальные проверены."),
    "R06": ("На странице нет тега canonical.",
            "Google сам выбирает главную версию; варианты с параметрами или другим регистром могут конкурировать.",
            "Добавить в шаблон <link rel=\"canonical\" href=\"<адрес самой страницы>\">.",
            "В HTML страницы есть canonical на её собственный адрес."),
    "R06c": ("Canonical ведёт на адрес с ошибкой или noindex.",
             "Google получает противоречивые указания и может не проиндексировать ни одну версию.",
             "Указать в canonical живую индексируемую страницу.",
             "Canonical ведёт на страницу с ответом 200 без noindex."),
    "R06d": ("Google выбрал главной не ту версию, что указана в canonical.",
             "Google игнорирует наш canonical — обычно из-за дублей или противоречивых ссылок.",
             "Сравнить две версии; внутренние ссылки, сайтмап и редиректы направить на нужную.",
             "Проверка URL в Search Console: «Канонический адрес, выбранный Google» совпадает с нашим."),
    "R07": ("Страницы открываются и могут индексироваться, но Google их не проиндексировал.",
            "Страница, которой нет в индексе, не приносит трафика.",
            "Поставить на эти страницы ссылки с уже проиндексированных страниц, держать их в сайтмапе, усилить уникальный контент. Повторная отправка на индексацию сама по себе не помогает.",
            "Проверка URL показывает «Страница проиндексирована» (появится после следующего обхода Google)."),
    "R08": ("Во внутренних ссылках зашиты параметры аналитики (_gl, utm_, gclid).",
            "Получаются дубли адресов, robots.txt их закрывает, а сессии в аналитике ломаются.",
            "Заменить такие ссылки на чистые адреса. Параметр _gl Google Analytics добавляет сам в момент клика, руками его вставлять не нужно.",
            "На страницах-источниках ссылки без параметров."),
    "R09": ("Страницы приложения, платформы или старого сайта видны в поиске.",
            "Из поиска приходят на логин и экраны приложения вместо сайта. Если в адресах есть идентификаторы пользователей, это ещё и вопрос приватности.",
            "На app.* и platform.* отдавать noindex (meta или заголовок X-Robots-Tag) для всех страниц, которые не должны быть в поиске; old.* — 301 на соответствующие страницы www. robots.txt не закрывать, иначе Google не увидит noindex.",
            "Через 2–4 недели эти адреса пропадают из Search Console и Bing."),
    "R10": ("Варианты адреса (http:// или без www) получают показы, но не ведут редиректом 301 на главный адрес.",
            "Сигналы делятся между несколькими версиями сайта.",
            "Настроить 301 с каждого варианта сразу на https://www.",
            "Вариант отдаёт 301 на https-адрес основного хоста."),
    "R11": ("Нет title или одинаковый title на нескольких страницах.",
            "Title — главный текст сниппета в поиске; дубли мешают Google понять, какая страница о чём.",
            "Написать уникальный title для каждой страницы.",
            "У каждой страницы свой title."),
    "R11b": ("Title слишком длинный (больше 60 символов) или слишком короткий (меньше 20).",
             "Длинный Google обрезает или переписывает, короткий не использует место.",
             "Уложить главную фразу в первые 50–60 символов.",
             "Длина title 20–60 символов."),
    "R12": ("Meta description нет, он повторяется или его длина не 70–160 символов.",
            "Хороший description повышает кликабельность там, где Google его показывает.",
            "Написать уникальное описание на 120–160 символов, которое отвечает на главный запрос страницы.",
            "Description уникальный, 70–160 символов."),
    "R13": ("На странице нет H1 или их несколько.",
            "Один H1 ясно говорит, о чём страница.",
            "Оставить ровно один H1.",
            "На странице один H1."),
    "R14": ("Мало текста: меньше 250 слов.",
            "Такие страницы редко ранжируются, если это не навигация.",
            "Дописать полезный контент или поставить noindex служебным страницам.",
            "Больше 250 слов или noindex."),
    "R15": ("У картинок нет атрибута alt (пустой alt=\"\" для декоративных картинок — норма).",
            "Alt нужен для поиска по картинкам и доступности.",
            "Добавить alt с описанием картинки.",
            "У содержательных картинок есть alt."),
    "R16": ("Разметка JSON-LD с ошибкой синтаксиса.",
            "Google её не читает.",
            "Исправить JSON в блоке <script type=\"application/ld+json\">.",
            "JSON разбирается без ошибок (validator.schema.org)."),
    "R17": ("Ошибка в разметке языковых версий (hreflang).",
            "Google показывает не ту языковую версию или игнорирует связки.",
            "Каждая языковая версия должна ссылаться на все остальные и на себя; ссылки — только на живые страницы с canonical на себя.",
            "Связки полные и взаимные."),
    "R18": ("Сервер долго отвечает: больше 1 секунды до первого байта.",
            "Медленный ответ замедляет всю загрузку страницы (LCP) и снижает частоту обхода Google.",
            "Включить кэширование страниц для анонимных посетителей (CDN или page cache) и проверить скорость сервера.",
            "Время ответа меньше 800 мс; через 28 дней улучшение видно в CrUX."),
    "R18b": ("Core Web Vitals у реальных пользователей хуже нормы (данные Chrome за 28 дней).",
             "Google учитывает их в оценке удобства страницы.",
             "Найти медленный шаблон в Lighthouse или DevTools; сначала ускорить ответ сервера, потом скрипты.",
             "Метрики в CrUX в зелёной зоне: LCP до 2,5 с, INP до 200 мс, CLS до 0,1."),
    "R19": ("JavaScript меняет title, canonical или robots после загрузки.",
            "Google видит одно, другие боты и ИИ-краулеры — другое.",
            "Отдавать финальные значения сразу в HTML.",
            "В исходном HTML и после рендера значения совпадают."),
    "R19b": ("После выполнения JavaScript на странице сильно больше текста и ссылок.",
             "Если основной текст появляется только после JS, боты без рендера его не видят. Если добавляется виджет (баннер cookies, чат), это не проблема.",
             "Проверить, что добавляет JS; основной контент отдавать в HTML.",
             "Основной текст есть в исходном HTML."),
    "R20": ("robots.txt закрывает поисковых или ИИ-ботов.",
            "Закрытый поисковый бот не покажет сайт в своей выдаче.",
            "Решить, каких ботов пускаем; поисковых (Googlebot, Bingbot, OAI-SearchBot, Claude-SearchBot, PerplexityBot) — пускать.",
            "robots.txt соответствует решению; в Cloudflare нет блокировки этих ботов."),
    "R20x": ("robots.txt не открылся, поэтому хост не проверялся.",
             "Без robots.txt аудит не знает, что можно обходить, и пропускает хост.",
             "Проверить, что /robots.txt отвечает 200; посмотреть правила Cloudflare.",
             "Следующий аудит проверяет хост."),
    "R21": ("Bing сообщает об ошибках обхода.",
            "Страницы с ошибками Bing не показывает.",
            "Исправить по типу ошибки.",
            "Список ошибок в Bing Webmaster пуст."),
}


def details(f: dict, lang: str) -> tuple[str, str, str, str]:
    if lang == "ru" and f["rule"] in RU:
        return RU[f["rule"]]
    return (f.get("title", ""), f.get("why", ""), f.get("fix", ""), "Re-run the audit: the rule returns no URLs.")


STATES_RU = {
    "URL is unknown to Google": "Google не знает этот адрес",
    "Discovered - currently not indexed": "найден, но ещё не просканирован",
    "Crawled - currently not indexed": "просканирован, но не проиндексирован",
    "Excluded by ‘noindex’ tag": "исключён из-за noindex",
}
METRIC_RU = {"largest_contentful_paint": ("LCP, загрузка главного блока", "мс"),
             "interaction_to_next_paint": ("INP, отклик на действие", "мс"),
             "cumulative_layout_shift": ("CLS, сдвиг вёрстки", ""),
             "experimental_time_to_first_byte": ("TTFB, ответ сервера", "мс")}
RATING_RU = {"good": "хорошо", "needs improvement": "нужно улучшить", "poor": "плохо"}
FF_RU = {"ALL": "все устройства", "PHONE": "телефоны", "DESKTOP": "компьютеры"}


def plural(n, one, few, many):
    n = abs(int(n or 0))
    if n % 10 == 1 and n % 100 != 11:
        return one
    return few if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14 else many


def _host_path(u):
    s = urllib.parse.urlsplit(u or "")
    return s.netloc, [p for p in s.path.split("/") if p]


def _same_post_other_section(a: str, b: str) -> bool:
    """Same last path segment, same host, different first segment: one post under two sections/categories."""
    ha, pa = _host_path(a)
    hb, pb = _host_path(b)
    return ha == hb and len(pa) >= 2 and len(pb) >= 2 and pa[-1] == pb[-1] and pa[0] != pb[0]


def url_reasons(f: dict, pages: dict, insp: dict, exposure: dict, lang: str) -> list[list]:
    """[[url, reason, google clicks 28d], ...] for one finding (up to 200 URLs)."""
    ru = lang == "ru"
    ev = f.get("evidence") or {}
    out = []
    for u in f.get("urls", [])[:200]:
        p = pages.get(u) or pages.get(u.rstrip("/")) or pages.get(u.rstrip("/") + "/") or {}
        r, e = f["rule"], ev.get(u) if isinstance(ev, dict) else None
        reason = ""
        if r == "R01" and isinstance(e, dict):
            src = ", ".join(e.get("linked_from", [])[:3])
            reason = f"отдаёт {e.get('status')}; ссылки стоят на: {src}" if ru else f"returns {e.get('status')}; linked from: {src}"
        elif r == "R02":
            ch = json.loads(p.get("redirect_chain") or "[]")
            reason = " → ".join(f"{h.get('url')} ({h.get('status') or '—'})" for h in ch)
        elif r == "R02b" and isinstance(e, list):
            reason = (f"редирект на {p.get('final_url')}; ссылаются: " if ru else f"redirects to {p.get('final_url')}; linked from: ") + ", ".join(e[:3])
        elif r == "R03":
            can = p.get("canonical")
            if p.get("status") and p["status"] != 200:
                reason = f"в сайтмапе, но отдаёт {p['status']}" if ru else f"in the sitemap but returns {p['status']}"
            elif "noindex" in (p.get("meta_robots") or "").lower() or "none" in (p.get("meta_robots") or "").lower():
                reason = f"в сайтмапе, но на странице стоит robots «{p.get('meta_robots')}»" if ru else f"in the sitemap but robots is '{p.get('meta_robots')}'"
            elif can and can.rstrip("/") != u.rstrip("/"):
                reason = (f"в сайтмапе стоит этот адрес, но canonical страницы ведёт на {can}" if ru
                          else f"the sitemap lists this URL but the page's canonical is {can}")
                if _same_post_other_section(u, can):
                    reason += (": это та же статья в другой рубрике, сайтмап должен указывать на адрес из canonical"
                               if ru else ": the same post under another section; the sitemap should list the canonical URL")
            elif p.get("blocked_by_robots"):
                reason = "в сайтмапе, но закрыт в robots.txt" if ru else "in the sitemap but blocked by robots.txt"
        elif r == "R04":
            reason = "открывается и индексируется, но его нет в сайтмапе" if ru else "indexable but not in the sitemap"
        elif r == "R05" and isinstance(e, dict):
            reason = (f"robots «{e.get('robots')}»" + ("; при этом стоит в сайтмапе" if e.get("in_sitemap") else "")) if ru \
                else f"robots '{e.get('robots')}'" + ("; also in the sitemap" if e.get("in_sitemap") else "")
        elif r == "R06":
            reason = "в HTML нет <link rel=canonical>" if ru else "no <link rel=canonical> in the HTML"
        elif r == "R06c" and e:
            reason = f"canonical ведёт на {e}" if ru else f"canonical points to {e}"
        elif r == "R06d" and isinstance(e, dict):
            reason = (f"Google выбрал {e.get('google')}, на странице указан {e.get('declared')}" if ru
                      else f"Google chose {e.get('google')}, the page declares {e.get('declared')}")
        elif r == "R07":
            i = insp.get(u, {})
            last = i.get("lastCrawlTime")
            state = STATES_RU.get(i.get("coverageState"), i.get("coverageState")) if ru else i.get("coverageState")
            reason = (f"статус в Google: {state}; последний обход Google: {last[:10] if last else 'не было'}" if ru
                      else f"Google status: {i.get('coverageState')}; last Google crawl: {last[:10] if last else 'never'}")
        elif r == "R08" and isinstance(e, list):
            reason = ("ссылка с параметром стоит на страницах: " if ru else "the tagged link is on: ") + ", ".join(e[:3])
        elif r == "R09":
            g = (ev.get("google") or {}).get(u)
            if g:
                reason = (f"в Google за 28 дней: {g[0]} {plural(g[0], 'клик', 'клика', 'кликов')}, "
                          f"{g[1]} {plural(g[1], 'показ', 'показа', 'показов')}") if ru else \
                    f"Google, 28 days: {g[0]} clicks, {g[1]} impressions"
            elif u.rstrip("/") in exposure:
                c = exposure[u.rstrip("/")]
                reason = f"в Google за 28 дней: {c} {plural(c, 'клик', 'клика', 'кликов')}" if ru else f"Google, 28 days: {c} clicks"
            else:
                reason = "виден в Bing" if ru else "shown in Bing"
            if "userid=" in u.lower() or "user_id=" in u.lower():
                reason += "; в адресе идентификатор пользователя" if ru else "; the URL contains a user id"
        elif r == "R10" and e:
            reason = " → ".join(f"{x[0]} ({x[1]})" for x in e) if isinstance(e, list) else str(e)
        elif r == "R11":
            t = p.get("title")
            same = sum(1 for q in pages.values() if t and q.get("title") == t)
            reason = (f"нет title" if not t else f"title «{t}» стоит на {same} страницах") if ru else \
                ("no title" if not t else f"title '{t}' is on {same} pages")
        elif r == "R11b":
            t = p.get("title") or ""
            reason = f"{len(t)} символов: «{t}»" if ru else f"{len(t)} characters: '{t}'"
        elif r == "R12":
            d = p.get("meta_description") or ""
            reason = ("нет description" if not d else f"{len(d)} символов") if ru else ("no description" if not d else f"{len(d)} characters")
        elif r == "R13":
            n = len(json.loads(p.get("h1") or "[]"))
            reason = f"H1 на странице: {n}" if ru else f"H1 count: {n}"
        elif r == "R14":
            reason = f"{p.get('word_count')} слов" if ru else f"{p.get('word_count')} words"
        elif r == "R15":
            reason = (f"без alt {p.get('images_no_alt')} из {p.get('images')} картинок" if ru
                      else f"{p.get('images_no_alt')} of {p.get('images')} images without alt")
        elif r == "R16":
            reason = "JSON-LD не разбирается" if ru else "JSON-LD does not parse"
        elif r == "R18":
            reason = f"сервер ответил за {p.get('ttfb_ms')} мс" if ru else f"server responded in {p.get('ttfb_ms')} ms"
        elif r == "R18b" and isinstance(e, dict):
            parts = u.split()
            metric, ff = (parts[2], parts[1]) if len(parts) == 3 else ("", "")
            if ru and metric in METRIC_RU:
                name, unit = METRIC_RU[metric]
                reason = (f"{name} ({FF_RU.get(ff, ff)}): {e.get('p75')}{' ' + unit if unit else ''} у 75% визитов, "
                          f"{RATING_RU.get(e.get('rating'), e.get('rating'))}")
            else:
                reason = f"{metric} ({ff}): p75 {e.get('p75')}, {e.get('rating')}"
        elif r == "R17" and e is not None:
            reason = json.dumps(e, ensure_ascii=False)[:200]
        clicks = exposure.get(u.rstrip("/"), exposure.get(u))
        out.append([u, reason, "" if clicks is None else clicks])
    return out
