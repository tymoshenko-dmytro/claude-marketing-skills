# Ahrefs API units: what actually costs money

Measured on real keyword pulls through the Ahrefs MCP server (tens of thousands of candidate keywords). Prices can change — re-measure on a small batch before a big run, using `subscription-info-limits-and-usage` (free) before and after.

## The cost model

Ahrefs' documented formula: **cost of a call = max(50, per-row cost × rows)**, where a row costs the sum of its selected fields (1 unit by default; some fields 5 or 10). Cached responses and a few endpoint groups (Rank Tracker, management, public) are free, as are test queries on `ahrefs.com`. What that means in practice:

1. **You pay per row and per field, not per keyword sent.** Volume-type fields — `volume`, `global_volume`, `difficulty`, `parent_volume`, `traffic_potential` — cost about **10 units per row each** (11–12 all-in). Selecting two of them doubles the price. Cheap fields (`keyword`, `word_count`, `volume_mobile_pct`) cost about 1.
2. **Keywords with zero volume come back as rows with `volume: 0`** and cost little. In one pull, most of a 57,000-keyword candidate list cost almost nothing because only real demand was billed at full price.
3. **`where` filters on the server and bills only kept rows.** `{"field":"global_volume","is":["gte",30]}` turned a 6-row / 66-unit call into 4 rows / 50 units.
4. **Batching beats the 50-unit floor.** A single keyword pays the 50-unit minimum; in a batch of 2–5 keywords `keywords-explorer-overview` came to ~23–25 units per row.

Plan pulls by *expected rows with data*, not by keywords sent. Select only the volume field you need. Push the floor into `where`. Cache every batch so a re-run never pays twice.

## Where the cost of a call is reported

- **API v3:** response headers. `x-api-units-cost-total-actual` = units consumed; `x-api-units-cost-total` = units the request should consume; `x-api-units-cost-row` = per-row cost; `x-api-rows` = rows returned; `x-api-cache` = `hit` / `miss` / `no_cache` (a cached response costs nothing). `curl -v` shows them. `ahrefs_api.py` and `kw.py` log the first one.
- **MCP:** a second text block in the tool result, `{"apiUsageCosts": {"units-cost-total-actual": N}}`. `kw.py import` reads it when the saved output contains it.
- **Either:** `subscription-info-limits-and-usage` before and after a batch (free).

## MCP transport quirks

All three look the same from outside: `{"error": "internal server error"}`.

1. **A keyword Ahrefs has never indexed fails the WHOLE request.** Zero-volume keywords are fine; a phrase with no index entry at all kills every other keyword in the same call. So do not price invented variants. Price only terms that came back from a discovery pass, and batch in 2–5 so one bad keyword costs one cheap retry.
2. **`keywords-explorer-matching-terms` rejects `where` and `order_by`.** Both fail every time, in any syntax. The workaround is cheaper anyway: discover with `select=keyword` only (~1 unit per row), then price the shortlist through `keywords-explorer-overview`. 100 ideas for ~100 units.
3. **Parallel calls fail.** Five `overview` calls in one message: one succeeded, four failed. Send pricing calls sequentially. `matching-terms` tolerated two at a time.

## The pattern that works

```
discovery   keywords-explorer-matching-terms   select=keyword            ~1 unit/row
   ↓ shortlist by relevance (agent or you)
pricing     keywords-explorer-overview         select=keyword,volume     batches of 2–5, sequential
            where: volume >= <floor>
   ↓ cache every batch to raw/seo/
```

## Other notes

- `keywords` is a **comma-separated string**, not a list.
- MCP keys and API v3 keys are not interchangeable: an MCP key returns 401 on `api.ahrefs.com/v3/...`. Use the MCP server with an MCP key, `scripts/ahrefs_api.py` with an API v3 key.
- Admins can cap monthly units per key — do it for any key an agent uses.
- Keys get rotated. A dead key fails silently with 401 on every path; if everything suddenly returns 401, issue a new key first.
