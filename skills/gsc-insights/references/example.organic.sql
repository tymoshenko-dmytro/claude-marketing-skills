-- Example [conversions].sql for gsc-insights (gsc_report.py, weekly_digest.py): Google organic landing pages joined
-- to sign-ups and trials, from the standard GA4 BigQuery export (events_YYYYMMDD tables).
-- Copy it next to your site config (e.g. ~/.config/marketing-agent-kit/seo/<site>.organic.sql), point
-- [conversions].sql at the copy, and change the lines marked CHANGE.
--
-- Params {{start}} {{end}}: inclusive dates in the GA4 property's time zone (Search Console days are US Pacific, so
--   the edges differ by hours). The script replaces them; leave them as they are.
-- Columns: landing_page, organic_sessions, registrations, trials.
-- organic_sessions: GA4 sessions whose last-click source / medium is google / organic, by landing page (the first
--   page_location of the session, without query string, fragment and trailing slash).
-- registrations / trials: the first registration event and the first trial event per person in the loaded range,
--   by people who had a google / organic session in the 30 days before the event, credited to the landing page of
--   the LAST such session (same browser, or any browser that signed in with the same user_id). Association, not
--   query-level attribution; the person may also have had paid or direct sessions.
-- Needs session_traffic_source_last_click, which the GA4 export has carried since July 2024.
WITH names AS (
  SELECT 'sign_up'          AS registration_event,  -- GA4 recommended event; CHANGE if yours has another name
         'YOUR_TRIAL_EVENT' AS trial_event          -- CHANGE: your trial or second conversion event name
),
ev AS (
  SELECT
    PARSE_DATE('%Y%m%d', _TABLE_SUFFIX) AS d,
    event_name, user_pseudo_id, user_id,
    (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS sid,
    TIMESTAMP_MICROS(event_timestamp) AS ts,
    (SELECT value.string_value FROM UNNEST(event_params) WHERE key = 'page_location') AS loc,
    LOWER(IFNULL(session_traffic_source_last_click.cross_channel_campaign.source, '')) AS src,
    LOWER(IFNULL(session_traffic_source_last_click.cross_channel_campaign.medium, '')) AS med
  FROM `your-gcp-project.analytics_123456789.events_*`  -- CHANGE: your project and GA4 export dataset
  WHERE REGEXP_CONTAINS(_TABLE_SUFFIX, r'^\d{8}$')       -- daily tables only, not events_intraday_*
    AND _TABLE_SUFFIX BETWEEN FORMAT_DATE('%Y%m%d', DATE_SUB(DATE '{{start}}', INTERVAL 30 DAY))
                          AND FORMAT_DATE('%Y%m%d', DATE '{{end}}')
),
ids AS (  -- browsers that signed in, linked to their user_id
  SELECT user_pseudo_id, ANY_VALUE(user_id) AS user_id FROM ev WHERE user_id IS NOT NULL GROUP BY 1
),
sess AS (
  SELECT user_pseudo_id, sid, MIN(d) AS d, MIN(ts) AS t,
    ARRAY_AGG(loc IGNORE NULLS ORDER BY ts LIMIT 1)[SAFE_OFFSET(0)] AS landing,
    LOGICAL_OR(src = 'google' AND med = 'organic') AS organic
  FROM ev WHERE sid IS NOT NULL GROUP BY 1, 2
),
org AS (
  SELECT COALESCE(i.user_id, s.user_pseudo_id) AS person, s.d, s.t,
    REGEXP_REPLACE(REGEXP_REPLACE(s.landing, r'[?#].*$', ''), r'/$', '') AS landing_page
  FROM sess s LEFT JOIN ids i ON i.user_pseudo_id = s.user_pseudo_id
  WHERE s.organic AND s.landing IS NOT NULL
    -- AND NET.HOST(s.landing) IN ('www.example.com', 'blog.example.com')  -- optional CHANGE: only your public hosts
                                                                            -- (drops preview and staging hosts)
),
conv AS (  -- first registration and first trial per person. Conversions in a backend table instead: replace this
           -- CTE with a query on that table returning kind ('registration' / 'trial'), person, t (timestamp).
  SELECT IF(e.event_name = n.registration_event, 'registration', 'trial') AS kind,
    COALESCE(i.user_id, e.user_pseudo_id) AS person, MIN(e.ts) AS t
  FROM ev e CROSS JOIN names n LEFT JOIN ids i ON i.user_pseudo_id = e.user_pseudo_id
  WHERE e.event_name IN (n.registration_event, n.trial_event)
  GROUP BY 1, 2
  HAVING MIN(e.d) BETWEEN DATE '{{start}}' AND DATE '{{end}}'
),
cred AS (
  SELECT c.kind, ARRAY_AGG(o.landing_page ORDER BY o.t DESC LIMIT 1)[SAFE_OFFSET(0)] AS landing_page
  FROM conv c
  JOIN org o ON o.person = c.person AND o.t <= c.t AND o.t >= TIMESTAMP_SUB(c.t, INTERVAL 30 DAY)
  GROUP BY c.kind, c.person
)
SELECT landing_page, SUM(s) AS organic_sessions, SUM(r) AS registrations, SUM(tr) AS trials
FROM (
  SELECT landing_page, COUNT(*) AS s, 0 AS r, 0 AS tr FROM org
  WHERE d BETWEEN DATE '{{start}}' AND DATE '{{end}}' GROUP BY 1
  UNION ALL
  SELECT landing_page, 0, COUNTIF(kind = 'registration'), COUNTIF(kind = 'trial')
  FROM cred GROUP BY 1
)
GROUP BY 1
ORDER BY organic_sessions DESC
