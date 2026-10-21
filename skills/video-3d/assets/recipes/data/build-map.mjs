#!/usr/bin/env node
// video-3d: bake a flat / extruded country map at build time (generalised from the data reel's map tool).
// Node, no dependencies. Same input + same flags = the same bytes out.
//
//   node build-map.mjs --src countries-50m.json --crop -26,60,-38,40 [--center 17,1] [--phi0 15]
//        [--regions 012,024,Somaliland | --regions regions.json] [--values values.json] [--seed 1]
//        [--tol 0.05] [--min-area 0.25] [--var MAP_DATA] --out assets/data/map-data.js
//
// --src     a world-atlas TopoJSON with a `countries` object (cdn.jsdelivr.net/npm/world-atlas@2.0.2/countries-50m.json)
// --crop    lon0,lon1,lat0,lat1 in degrees (no antimeridian crossing - for that, unwrap ring longitudes as in references/recipes.md, Data in space)
// --regions countries to extrude: ISO 3166-1 numeric ids and/or names (comma list or a JSON array file);
//           default = every country whose largest polygon's centroid is inside the crop
// --values  JSON { "<id or name>": number } - the film's data; without it values are SEEDED SAMPLE DATA (label them so)
//
// What it does (the traps the data reel hit are the reasons):
// 1. Decodes the TopoJSON arcs and simplifies every ARC once (Douglas-Peucker, endpoints kept), then builds the
//    rings from the simplified arcs - neighbours share the same border vertices. Simplifying ring by ring leaves
//    slivers and overlaps along every border.
// 2. Projects equirectangular (centre, standard parallel) into map units (1 unit = 1 degree of latitude).
// 3. An extruded country keeps only its polygons whose centroid is inside the crop: outlying islands (South
//    Africa's Prince Edward Islands, France, Norway, the US ...) otherwise extrude as lone sticks off the base map.
//    Dropped polygons are logged. Countries under --min-area stay flat context.
// 4. Borders = every arc touching the crop, once (coasts and land borders) - draw them into the ground texture
//    AND into a border mask the extruded tops sample (see README).
import { readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const argv = process.argv.slice(2), opt = {};
for (let i = 0; i < argv.length; i++) if (argv[i].startsWith("--")) opt[argv[i].slice(2)] = argv[i + 1] && !argv[i + 1].startsWith("--") ? argv[++i] : true;
if (!opt.src || !opt.crop || !opt.out) { console.error("usage: node build-map.mjs --src countries.json --crop lon0,lon1,lat0,lat1 --out map-data.js [options]"); process.exit(2); }
const nums = (s) => String(s).split(",").map(Number);
const [lon0, lon1, lat0, lat1] = nums(opt.crop);
const [LON_C, LAT_C] = opt.center ? nums(opt.center) : [(lon0 + lon1) / 2, (lat0 + lat1) / 2];
const PHI0 = opt.phi0 !== undefined ? Number(opt.phi0) : Math.abs(LAT_C);
const TOL = Number(opt.tol ?? 0.05), MIN_AREA = Number(opt["min-area"] ?? 0.25), SEED = Number(opt.seed ?? 1);
const VAR = opt.var || "MAP_DATA";
const listArg = (v) => (String(v).trim().startsWith("[") || String(v).endsWith(".json") ? JSON.parse(String(v).endsWith(".json") ? readFileSync(resolve(v), "utf8") : v) : String(v).split(","));
const REGION_KEYS = opt.regions ? new Set(listArg(opt.regions).map(String)) : null;
const VALUES = opt.values ? JSON.parse(readFileSync(resolve(opt.values), "utf8")) : null;

function rng(seed) { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a;
  t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }

// ---------- TopoJSON decode + per-arc simplification ----------
const topo = JSON.parse(readFileSync(resolve(opt.src), "utf8"));
const [sx, sy] = topo.transform.scale, [tx, ty] = topo.transform.translate;
const raw = topo.arcs.map((arc) => { let x = 0, y = 0; return arc.map(([dx, dy]) => { x += dx; y += dy; return [x * sx + tx, y * sy + ty]; }); });
function simplify(pts, tol) {
  if (pts.length < 3) return pts;
  const keep = new Uint8Array(pts.length); keep[0] = keep[pts.length - 1] = 1;
  const stack = [[0, pts.length - 1]];
  while (stack.length) {
    const [a, b] = stack.pop(); let dmax = 0, idx = -1;
    const [ax, ay] = pts[a], [bx, by] = pts[b], dx = bx - ax, dy = by - ay, L = Math.hypot(dx, dy);
    for (let i = a + 1; i < b; i++) {
      const d = L > 1e-9 ? Math.abs(dy * pts[i][0] - dx * pts[i][1] + bx * ay - by * ax) / L : Math.hypot(pts[i][0] - ax, pts[i][1] - ay);
      if (d > dmax) { dmax = d; idx = i; }
    }
    if (dmax > tol && idx > 0) { keep[idx] = 1; stack.push([a, idx], [idx, b]); }
  }
  return pts.filter((_, i) => keep[i]);
}
const K = Math.cos((PHI0 * Math.PI) / 180);
const project = ([lon, lat]) => [+((lon - LON_C) * K).toFixed(3), +(lat - LAT_C).toFixed(3)];
const arcs = raw.map((a) => simplify(a, TOL).map(project));
const arcPts = (i) => (i >= 0 ? arcs[i] : arcs[~i].slice().reverse());
const ringOf = (idx) => { const out = []; idx.forEach((a, k) => { const p = arcPts(a); out.push(...(k ? p.slice(1) : p)); }); return out; };

// ---------- helpers (projected units) ----------
const area = (r) => { let s = 0; for (let i = 0; i < r.length; i++) { const [x0, y0] = r[i], [x1, y1] = r[(i + 1) % r.length]; s += x0 * y1 - x1 * y0; } return s / 2; };
const centroid = (r) => { let cx = 0, cy = 0, a = 0; for (let i = 0; i < r.length; i++) { const [x0, y0] = r[i], [x1, y1] = r[(i + 1) % r.length], c = x0 * y1 - x1 * y0; a += c; cx += (x0 + x1) * c; cy += (y0 + y1) * c; } return [cx / (3 * a), cy / (3 * a)]; };
const [cx0, cy0] = project([lon0, lat0]), [cx1, cy1] = project([lon1, lat1]);
const touches = (pts) => pts.some(([x, y]) => x > cx0 - 2 && x < cx1 + 2 && y > cy0 - 2 && y < cy1 + 2);
const inCrop = (p) => { const [x, y] = centroid(p[0]); return x > cx0 && x < cx1 && y > cy0 && y < cy1; };
const keyOf = (g) => [g.id, g.properties?.name].filter(Boolean).map(String);

// ---------- select ----------
const regions = [], context = [];
for (const g of topo.objects.countries.geometries) {
  const polys = (g.type === "Polygon" ? [g.arcs] : g.type === "MultiPolygon" ? g.arcs : []).map((p) => p.map(ringOf).filter((r) => r.length >= 4)).filter((p) => p.length);
  if (!polys.length || !polys.some((p) => touches(p[0]))) continue;
  if (polys.some((p) => p[0].some(([x]) => Math.abs(x) > 170))) continue;          // antimeridian-wide: not handled here
  const A = polys.reduce((s, p) => s + Math.abs(area(p[0])), 0);
  const biggest = polys.reduce((m, p) => (Math.abs(area(p[0])) > Math.abs(area(m[0])) ? p : m));
  const wanted = REGION_KEYS ? keyOf(g).some((k) => REGION_KEYS.has(k)) : inCrop(biggest);
  if (wanted && A >= MIN_AREA) {
    const dropped = polys.filter((p) => !inCrop(p));
    if (dropped.length) console.log(`dropped ${dropped.length} outlying polygon(s) of ${g.properties?.name ?? g.id}`);
    const kept = polys.filter(inCrop);
    if (!kept.length) { context.push(...polys); continue; }
    const big = kept.reduce((m, p) => (Math.abs(area(p[0])) > Math.abs(area(m[0])) ? p : m));
    regions.push({ id: g.id || null, name: g.properties?.name ?? String(g.id), polys: kept, area: A, c: centroid(big[0]) });
  } else context.push(...polys);
}
regions.sort((a, b) => (a.name < b.name ? -1 : 1));
const r = rng(SEED);
regions.forEach((g) => {
  const v = VALUES && keyOf(g).map((k) => VALUES[k]).find((x) => x !== undefined);
  g.value = v !== undefined && v !== null ? Number(v) : +(0.1 + 0.9 * Math.pow(r(), 1.2)).toFixed(3);
});
const sample = !VALUES;
const borders = arcs.filter((a) => a.length >= 2 && touches(a));
const grat = [], step = 10;
for (let lon = Math.ceil(lon0 / step) * step; lon <= lon1; lon += step) grat.push([project([lon, lat0]), project([lon, lat1])]);
for (let lat = Math.ceil(lat0 / step) * step; lat <= lat1; lat += step) grat.push([project([lon0, lat]), project([lon1, lat])]);

const out = {
  source: String(opt.src).split("/").pop(),
  projection: { type: "equirectangular", lonC: LON_C, latC: LAT_C, phi0: PHI0, unit: "1 = 1 deg latitude" },
  crop: { min: [cx0, cy0], max: [cx1, cy1] }, sampleData: sample,
  regions: regions.map((g) => ({ name: g.name, id: g.id, v: g.value, a: +g.area.toFixed(2), c: g.c.map((v) => +v.toFixed(2)), polys: g.polys })),
  context, borders, graticule: grat,
};
writeFileSync(resolve(opt.out), `// generated by build-map.mjs - do not edit.${sample ? ` Values are SAMPLE DATA (seeded, seed ${SEED}).` : ""}\nwindow.${VAR} = ${JSON.stringify(out)};\n`);
const n = (p) => p.reduce((s, x) => s + x.length, 0);
console.log(`countries ${topo.objects.countries.geometries.length}; regions ${regions.length}; context polygons ${context.length}; border arcs ${borders.length}; region points ${regions.reduce((s, g) => s + g.polys.reduce((t, p) => t + n(p), 0), 0)}`);
if (REGION_KEYS) { const got = new Set(regions.flatMap((g) => [g.id, g.name].filter(Boolean).map(String))); const miss = [...REGION_KEYS].filter((k) => !got.has(k)); if (miss.length) console.log("not extruded (missing, too small or outside):", miss.join(" ")); }
