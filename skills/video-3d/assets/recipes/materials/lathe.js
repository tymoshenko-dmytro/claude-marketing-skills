// Turned objects from 2D profiles (capability 2.3, LatheGeometry).
// A vessel with real wall thickness: outer wall up, a round lip, the inner wall down, an inner floor.
// The profile is ordered so LatheGeometry's own normals face out of the material everywhere
// (outer wall out, inner wall into the cavity, lip and inner floor up, base down).
// Adds a second UV set (uv1) parameterised by ARC LENGTH along the profile - the bake target for
// aoMap/lightMap (4.7). The default uv (v = point index) crowds texels into the lip arc.
import * as THREE from "three";

const V2 = (x, y) => new THREE.Vector2(x, y);

// quarter/half arcs as point lists (centre, radius, from/to angle in radians, steps)
function arc(cx, cy, r, a0, a1, steps) {
  const out = [];
  for (let i = 0; i <= steps; i++) { const a = a0 + (a1 - a0) * (i / steps); out.push(V2(cx + r * Math.cos(a), cy + r * Math.sin(a))); }
  return out;
}

// outward 2D normal of a polyline at i (profile goes up the outer wall: normal = (dy, -dx))
function normalAt(pts, i) {
  const a = pts[Math.max(0, i - 1)], b = pts[Math.min(pts.length - 1, i + 1)];
  return V2(b.y - a.y, -(b.x - a.x)).normalize();
}

export function vaseProfile({ wall = 0.035, base = 0.1, samples = 140 } = {}) {
  // outer wall: a foot, a full belly, a waisted neck, a flared lip (units: the vase is 1.55 tall)
  const ctrl = [V2(0.335, 0.035), V2(0.40, 0.13), V2(0.50, 0.31), V2(0.555, 0.54), V2(0.53, 0.78),
    V2(0.43, 1.0), V2(0.29, 1.19), V2(0.215, 1.35), V2(0.222, 1.46), V2(0.268, 1.55)];
  const outer = new THREE.SplineCurve(ctrl).getSpacedPoints(samples);
  const inner = outer.map((p, i) => p.clone().addScaledVector(normalAt(outer, i), -wall));
  const top = outer[outer.length - 1], topIn = inner[inner.length - 1];
  const lc = top.clone().add(topIn).multiplyScalar(0.5), lr = top.distanceTo(topIn) / 2;
  const a0 = Math.atan2(top.y - lc.y, top.x - lc.x);
  // the inner wall stops above the inner floor (base thickness), then a fillet and the floor to the axis
  const fr = 0.05, floorY = base;
  const innerDown = inner.slice().reverse().filter((p) => p.y > floorY + fr + 0.005);
  // the base is slightly concave (the axis 0.012 up), so only the foot ring touches the plinth: no z-fight
  const pts = [V2(0, 0.012), V2(0.22, 0.004), V2(0.30, 0), ...arc(0.30, 0.035, 0.035, -Math.PI / 2, 0, 6).slice(1),
    ...outer.slice(1),
    ...arc(lc.x, lc.y, lr, a0, a0 + Math.PI, 12).slice(1, -1),            // the lip, over the top
    ...innerDown];
  const lx = innerDown[innerDown.length - 1].x;
  pts.push(...arc(lx - fr, floorY + fr, fr, 0, -Math.PI / 2, 6));
  pts.push(V2(0, floorY));
  return pts;
}

export function plinthProfile({ radius = 1.5, height = 0.28, fillet = 0.03 } = {}) {
  const r = radius, h = height, f = fillet;
  return [V2(0, 0), V2(r - f, 0), ...arc(r - f, f, f, -Math.PI / 2, 0, 6).slice(1),
    V2(r, h - f), ...arc(r - f, h - f, f, 0, Math.PI / 2, 6).slice(1), V2(0, h)];
}

// LatheGeometry + uv1 by arc length (u around, v along the profile) + the index count per segment
// (for a drawRange sweep: count = round(segments * k) * indicesPerSegment).
export function turned(points, segments = 160) {
  const geo = new THREE.LatheGeometry(points, segments);
  const len = [0];
  for (let i = 1; i < points.length; i++) len.push(len[i - 1] + points[i].distanceTo(points[i - 1]));
  const total = len[len.length - 1];
  const uv = geo.attributes.uv, uv1 = new Float32Array(uv.count * 2), n = points.length;
  for (let i = 0; i <= segments; i++) for (let j = 0; j < n; j++) {
    const k = i * n + j; uv1[2 * k] = i / segments; uv1[2 * k + 1] = len[j] / total;
  }
  geo.setAttribute("uv1", new THREE.BufferAttribute(uv1, 2));
  geo.userData.indicesPerSegment = (n - 1) * 6;
  geo.userData.segments = segments;
  geo.userData.profileLength = total;
  return geo;
}

// outer radius of the vase at height y (for probes and placing things)
export function radiusAt(points, y) {
  let best = 0;
  for (let i = 1; i < points.length; i++) {
    const a = points[i - 1], b = points[i];
    if ((a.y - y) * (b.y - y) <= 0 && a.y !== b.y) { const k = (y - a.y) / (b.y - a.y); best = Math.max(best, a.x + (b.x - a.x) * k); }
  }
  return best;
}
