// video-3d: time inside a HyperFrames sub-composition (from the camera-text reel's 3D layer).
// `hf-seek` carries ROOT time, also inside a sub-composition (a probe got t = 1.0 at its host's
// data-start 1). Local time = root time - the data-start of every host ([data-composition-src]) above
// the element. A standalone `-c` render gives the host data-start="0", so the same code works mounted
// and alone. Nested hosts are summed (tested one level deep).
export function hostStart(el) {
  let s = 0, h = el.closest("[data-composition-src]");
  while (h) {
    s += parseFloat(h.getAttribute("data-start") || "0") || 0;
    h = h.parentElement && h.parentElement.closest("[data-composition-src]");
  }
  return s;
}

// usage in the layer's module:
//   window.addEventListener("hf-seek", (e) => renderAt(Math.max(0, Math.min(DUR, e.detail.time - hostStart(canvas)))));
