-- Example [digest].sources_sql for gsc-insights weekly_digest.py: organic visits, sign-ups and trials per search
-- source and ISO week, from the standard GA4 BigQuery export (events_YYYYMMDD tables).
-- Copy it next to your site config (e.g. ~/.config/marketing-agent-kit/seo/<site>.sources.sql), point
-- [digest].sources_sql at the copy, and change the lines marked CHANGE.
--
-- Params {{start}} {{end}}: inclusive dates in the GA4 property's time zone; {{start}} is the Monday of the first
--   trend week. The script replaces them; leave them as they are.
-- Columns: week (YYYY-Www), channel, sessions, registrations, trials.
-- channel: Google / Bing / Other search (medium = organic) and AI assistants (referrals from ChatGPT, Perplexity,
--   Gemini, Copilot, Claude and similar; ads on those platforms, medium = cpc, are excluded).
-- sessions: GA4 sessions that started in the window, by the session's last-click source / medium.
-- registrations / trials: the first registration event and the first trial event per person in the loaded range,
--   credited to the channel of the person's LAST organic or AI session in the 30 days before the event (same browser,
--   or any browser that signed in with the same user_id). Association, not query-level attribution. Conversions
--   without such a session are not counted here.
-- One extra row per week with channel = '_days': sessions = the number of GA4 daily tables present (7 = complete).
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
  SELECT user_pseudo_id, sid, MIN(d) AS d, MIN(ts) AS t, MAX(src) AS src, MAX(med) AS med
  FROM ev WHERE sid IS NOT NULL GROUP BY 1, 2
),
cls AS (
  SELECT s.d, s.t, COALESCE(i.user_id, s.user_pseudo_id) AS person, CASE
    WHEN s.med != 'cpc' AND REGEXP_CONTAINS(s.src, r'chatgpt|openai|perplexity|gemini\.google|bard\.google|copilot|claude\.ai|deepseek|grok|meta\.ai|you\.com|phind|mistral') THEN 'AI assistants'
    WHEN s.med = 'organic' AND s.src = 'google' THEN 'Google'
    WHEN s.med = 'organic' AND s.src = 'bing' THEN 'Bing'
    WHEN s.med = 'organic' THEN 'Other search'
  END AS ch
  FROM sess s LEFT JOIN ids i ON i.user_pseudo_id = s.user_pseudo_id
),
conv AS (  -- first registration and first trial per person. Conversions in a backend table instead: replace this
           -- CTE with a query on that table returning kind ('registration' / 'trial'), person, t (timestamp), d (date).
  SELECT IF(e.event_name = n.registration_event, 'registration', 'trial') AS kind,
    COALESCE(i.user_id, e.user_pseudo_id) AS person, MIN(e.ts) AS t, MIN(e.d) AS d
  FROM ev e CROSS JOIN names n LEFT JOIN ids i ON i.user_pseudo_id = e.user_pseudo_id
  WHERE e.event_name IN (n.registration_event, n.trial_event)
  GROUP BY 1, 2
  HAVING MIN(e.d) BETWEEN DATE '{{start}}' AND DATE '{{end}}'
),
cred AS (
  SELECT c.kind, c.d, ARRAY_AGG(s.ch ORDER BY s.t DESC LIMIT 1)[OFFSET(0)] AS ch
  FROM conv c
  JOIN cls s ON s.person = c.person AND s.ch IS NOT NULL
    AND s.t <= c.t AND s.t >= TIMESTAMP_SUB(c.t, INTERVAL 30 DAY)
  GROUP BY c.kind, c.person, c.d
)
SELECT week, channel, SUM(s) AS sessions, SUM(r) AS registrations, SUM(tr) AS trials FROM (
  SELECT FORMAT_DATE('%G-W%V', d) AS week, ch AS channel, COUNT(*) AS s, 0 AS r, 0 AS tr
  FROM cls WHERE ch IS NOT NULL AND d BETWEEN DATE '{{start}}' AND DATE '{{end}}' GROUP BY 1, 2
  UNION ALL
  SELECT FORMAT_DATE('%G-W%V', d), ch, 0, COUNTIF(kind = 'registration'), COUNTIF(kind = 'trial')
  FROM cred GROUP BY 1, 2
  UNION ALL
  SELECT FORMAT_DATE('%G-W%V', d), '_days', COUNT(DISTINCT d), 0, 0
  FROM ev WHERE d BETWEEN DATE '{{start}}' AND DATE '{{end}}' GROUP BY 1
)
GROUP BY 1, 2
ORDER BY 1, 2
