// video-3d: a seek-safe AnimationMixer rig (from the models reel's scene module: makeRig, pose,
// setMorphs, aimBone, lookAt). three 0.181.2. Every frame sets each clip's time and weight ABSOLUTELY
// and evaluates with mixer.update(0); nothing depends on the previous seek.
//
// Two mixer traps this file works around (both reproduced by a Node test while making the models reel):
// 1. PropertyMixer writes a property to the scene graph only when the blended value DIFFERS from the
//    mixer's previous update. A foreign write in between (a rest-pose reset, a procedural look-at)
//    then survives the next update - but only when frames come in order, so every worker render
//    agrees and only a shuffled seek test catches it. Fix: never reset to the rest pose; record every
//    procedural write (rig.undo) and put the mixer's value back before the next update.
// 2. LoopOnce + mixer.setTime(t): a seek past the end disables (or with clampWhenFinished pauses) the
//    action; later seeks back show the rest pose. Fix: set action.time yourself (clamped for one-shots,
//    modulo for loops), enabled = true, paused = false, then mixer.update(0).
import * as THREE from "three";

// One glTF character: mixer with every clip playing at weight 0, bones by name, morph meshes.
// GLTFLoader sanitises node names ("UpperArm.R" -> "UpperArmR") - look bones up by the sanitised name.
export function makeRig(sceneRoot, clips, { scale = 1, shadows = true, material = null } = {}) {
  const root = new THREE.Group(); root.add(sceneRoot); sceneRoot.scale.setScalar(scale);
  sceneRoot.traverse((o) => {
    if (o.isMesh) { if (material) o.material = material(o.material) || o.material; o.castShadow = o.receiveShadow = shadows; }
    // SkinnedMesh.boundingSphere is computed lazily from the pose of the FIRST frame a worker renders,
    // then used for culling: pose-dependent state that differs per worker. Never cull skinned meshes.
    if (o.isSkinnedMesh) o.frustumCulled = false;
  });
  const mixer = new THREE.AnimationMixer(sceneRoot), actions = {};
  for (const c of clips) { const a = mixer.clipAction(c); a.play(); a.setEffectiveWeight(0); actions[c.name] = a; }
  const bones = {}, morphs = [];
  sceneRoot.traverse((o) => { if (o.isBone) bones[o.name] = o; if (o.isMesh && o.morphTargetInfluences) morphs.push(o); });
  return { root, sceneRoot, mixer, actions, bones, morphs, undo: [] };
}

// layers: [{ clip: "Walking", time: t - 2.0, weight: w(t), once: false }, ...] - all from t.
// Blends are weights you compute from t (no crossFadeTo: it schedules fades against mixer time).
export function pose(rig, layers) {
  for (let i = rig.undo.length - 1; i >= 0; i--) rig.undo[i][0].quaternion.copy(rig.undo[i][1]);
  rig.undo.length = 0;
  for (const a of Object.values(rig.actions)) { a.enabled = true; a.paused = false; a.setEffectiveWeight(0); }
  for (const L of layers) {
    const a = rig.actions[L.clip]; if (!a) throw new Error(`no clip ${L.clip}`);
    const d = a.getClip().duration;
    a.time = L.once ? Math.max(0, Math.min(d, L.time)) : ((L.time % d) + d) % d;
    a.setEffectiveWeight(L.weight);
  }
  rig.mixer.update(0);
}

// After pose(): clips may carry morph-weight tracks, so set every influence you use, every frame.
export function setMorphs(rig, vals) {
  for (const m of rig.morphs) for (const [k, v] of Object.entries(vals)) {
    const i = m.morphTargetDictionary[k]; if (i !== undefined) m.morphTargetInfluences[i] = v;
  }
}

// Aim a bone at a world point on top of the animated pose: a world-space pre-rotation, clamped to
// maxAngle, scaled by weight, recorded in rig.undo. Returns the applied angle (rad).
const _qa = new THREE.Quaternion(), _qb = new THREE.Quaternion(), _qc = new THREE.Quaternion();
const _pa = new THREE.Vector3(), _da = new THREE.Vector3();
export function aimBone(rig, bone, fromDirWorld, target, weight, maxAngle) {
  rig.undo.push([bone, bone.quaternion.clone()]);
  bone.getWorldPosition(_pa);
  _da.subVectors(target, _pa).normalize();
  _qa.setFromUnitVectors(fromDirWorld.clone().normalize(), _da);
  const ang = 2 * Math.acos(Math.min(1, Math.abs(_qa.w)));
  const k = (ang > maxAngle ? maxAngle / ang : 1) * weight;
  _qa.slerpQuaternions(_qb.identity(), _qa.clone(), k);
  bone.getWorldQuaternion(_qc);
  _qc.premultiply(_qa);
  bone.parent.getWorldQuaternion(_qb);
  bone.quaternion.copy(_qb.invert().multiply(_qc));
  bone.updateMatrixWorld(true);
  return ang * k;
}

// The head bone's local axis that points where the character faces (+Z of rig.root) in the current pose.
export function headAxis(rig, head = "Head") {
  rig.root.updateMatrixWorld(true);
  const qh = rig.bones[head].getWorldQuaternion(new THREE.Quaternion());
  const fwd = new THREE.Vector3(0, 0, 1).applyQuaternion(rig.root.getWorldQuaternion(new THREE.Quaternion()));
  return fwd.applyQuaternion(qh.invert());
}

// Neck takes 40% of the turn, the head the rest; axis from headAxis() (computed once, in the rest pose).
export function lookAt(rig, axis, target, weight, max = (55 * Math.PI) / 180, { neck = "Neck", head = "Head" } = {}) {
  const dir = () => axis.clone().applyQuaternion(rig.bones[head].getWorldQuaternion(new THREE.Quaternion()));
  const a1 = aimBone(rig, rig.bones[neck], dir(), target, 0.4 * weight, max * 0.4);
  const a2 = aimBone(rig, rig.bones[head], dir(), target, weight, max * 0.75);
  return a1 + a2;
}
