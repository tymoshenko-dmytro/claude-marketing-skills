// video-3d: GPUComputationRenderer made seek-safe (from the data reel's GPGPU section, WebGL2).
// Define the state at film frame f as "f * stepsPerFrame steps from the seeded initial texture". Two
// proven ways to honour that, bit-identical to each other on one GPU:
//   (a) replay: reset to the initial texture and step from frame 0 inside EVERY seek -
//       ~0.039 ms per step on an M1 Max for 64^2..512^2 (three's per-pass CPU overhead, not GPU work);
//       total cost ~0.039 ms x stepsPerFrame x frames^2 / 2 - start the sim at the shot, not at frame 0.
//   (b) bake: in the build, step once through the frames you show and copy each into a layer of a
//       WebGLArrayRenderTarget; a seek reads layer (frame - firstFrame). Memory per WORKER =
//       frames x particles x 16 B (36,864 particles x 210 frames = 118 MB; keep it under ~0.5 GB).
// Neither is portable between GPU and SwiftShader for a chaotic sim - pin the backend, or bake on the CPU.
import * as THREE from "three";
import { GPUComputationRenderer } from "three/addons/misc/GPUComputationRenderer.js";
import { FullScreenQuad } from "three/addons/postprocessing/Pass.js";

// stepShader: a fragment shader that reads `texturePosition` and writes the next state (gl_FragColor).
// init(data, rng): fill the RGBA Float32 initial state from the seeded rng (mulberry32).
export function makeSim(renderer, { size, seed, stepShader, init, uniforms = {}, name = "texturePosition" }) {
  const g = new GPUComputationRenderer(size, size, renderer);
  const tex = g.createTexture();
  init(tex.image.data, mulberry32(seed));
  const v = g.addVariable(name, stepShader, tex);
  g.setVariableDependencies(v, [v]);
  Object.assign(v.material.uniforms, uniforms);
  const err = g.init(); if (err) throw new Error("GPUComputationRenderer: " + err);
  // the class has no reset: re-render the initial texture into BOTH ping-pong targets
  const reset = () => { g.renderTexture(tex, v.renderTargets[0]); g.renderTexture(tex, v.renderTargets[1]); g.currentTextureIndex = 0; };
  const steps = (n) => { for (let i = 0; i < n; i++) g.compute(); };
  const texture = () => g.getCurrentRenderTarget(v).texture;
  const read = () => { const b = new Float32Array(size * size * 4); renderer.readRenderTargetPixels(g.getCurrentRenderTarget(v), 0, 0, size, size, b); return b; };
  return { g, v, size, reset, steps, texture, read };
}

// (a) state for a film frame, recomputed from frame 0 inside the seek
export function replayAt(sim, frame, stepsPerFrame) { sim.reset(); sim.steps(frame * stepsPerFrame); return sim.texture(); }

// (b) bake frames [firstFrame, lastFrame) into array layers, in the build (before the hold resolves).
// Read in a shader with: uniform highp sampler2DArray uBaked; texelFetch(uBaked, ivec3(xy, layer), 0)
export function bakeLayers(renderer, sim, { firstFrame, lastFrame, stepsPerFrame }) {
  const n = lastFrame - firstFrame, S = sim.size;
  const rt = new THREE.WebGLArrayRenderTarget(S, S, n, { type: THREE.FloatType, format: THREE.RGBAFormat,
    minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: false });
  const copy = new FullScreenQuad(new THREE.ShaderMaterial({ uniforms: { src: { value: null } },
    vertexShader: "void main() { gl_Position = vec4(position, 1.0); }",
    fragmentShader: "uniform sampler2D src; void main() { gl_FragColor = texelFetch(src, ivec2(gl_FragCoord.xy), 0); }" }));
  sim.reset();
  for (let f = 0; f < lastFrame; f++) {
    if (f >= firstFrame) {
      copy.material.uniforms.src.value = sim.texture();
      renderer.setRenderTarget(rt, f - firstFrame); copy.render(renderer); renderer.setRenderTarget(null);
    }
    sim.steps(stepsPerFrame);
  }
  copy.dispose();
  return { rt, layerAt: (frame) => Math.max(0, Math.min(n - 1, frame - firstFrame)) };
}

// Build-time check worth keeping: replay vs bake at a few frames, 0 differing floats expected.
export function readLayer(renderer, rt, layer) {
  const S = rt.width, out = new THREE.WebGLRenderTarget(S, S, { type: THREE.FloatType, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter, depthBuffer: false });
  const q = new FullScreenQuad(new THREE.ShaderMaterial({ uniforms: { src: { value: rt.texture }, uLayer: { value: layer } },
    vertexShader: "void main() { gl_Position = vec4(position, 1.0); }",
    fragmentShader: "uniform highp sampler2DArray src; uniform int uLayer; void main() { gl_FragColor = texelFetch(src, ivec3(ivec2(gl_FragCoord.xy), uLayer), 0); }" }));
  renderer.setRenderTarget(out); q.render(renderer); renderer.setRenderTarget(null);
  const b = new Float32Array(S * S * 4); renderer.readRenderTargetPixels(out, 0, 0, S, S, b);
  out.dispose(); q.dispose(); return b;
}
export const differingFloats = (a, b) => { const x = new Uint32Array(a.buffer), y = new Uint32Array(b.buffer); let n = 0; for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) n++; return n; };

function mulberry32(seed) { let a = seed >>> 0; return () => { a = (a + 0x6d2b79f5) >>> 0; let t = a;
  t = Math.imul(t ^ (t >>> 15), t | 1); t ^= t + Math.imul(t ^ (t >>> 7), t | 61); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }; }
