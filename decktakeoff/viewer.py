"""Three.js (r128) viewer for a Scene: one HTML file. Interactive (drag to orbit, wheel / pinch to zoom, view presets,
build steps, exploded view) and still mode for headless renders (?view=iso&phase=5&explode=1&still=1)."""
from __future__ import annotations

import json
from typing import Optional

from .scene import Scene

CDN_THREE = '<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>'

JS = r"""
(function(){
const D = __DATA__;
const q = new URLSearchParams(location.search);
const STILL = q.get('still') === '1';
const VIEW0 = q.get('view') || 'yard';
const PHASE0 = parseInt(q.get('phase') || '8', 10);
const EXPLODE0 = q.get('explode') === '1';
const TECH = EXPLODE0 || PHASE0 < 8 || q.get('notrees') === '1' || ['plan', 'under', 'underiso'].includes(VIEW0);   // technical stills: generic cameras, no trees
const root = document.getElementById('__UID__');
const W = root.clientWidth || window.innerWidth, H = root.clientHeight || window.innerHeight;
const renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
renderer.setPixelRatio(STILL ? 1 : Math.min(window.devicePixelRatio, 2));
renderer.setSize(W, H);
renderer.outputEncoding = THREE.sRGBEncoding;
renderer.toneMapping = THREE.ACESFilmicToneMapping; renderer.toneMappingExposure = 1.05;
renderer.shadowMap.enabled = true; renderer.shadowMap.type = THREE.PCFSoftShadowMap;
root.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.fog = new THREE.Fog(0xdbe7f1, 180, 520);
// sky
{ const c = document.createElement('canvas'); c.width = 16; c.height = 512; const g = c.getContext('2d');
  const gr = g.createLinearGradient(0, 0, 0, 512); gr.addColorStop(0, '#3a76b8'); gr.addColorStop(0.45, '#93bfe6'); gr.addColorStop(0.72, '#dbe7f1'); gr.addColorStop(1, '#eef2ee');
  g.fillStyle = gr; g.fillRect(0, 0, 16, 512);
  const t = new THREE.CanvasTexture(c); t.encoding = THREE.sRGBEncoding;
  const sky = new THREE.Mesh(new THREE.SphereGeometry(600, 24, 16), new THREE.MeshBasicMaterial({map: t, side: THREE.BackSide, fog: false}));
  scene.add(sky); }
// lights
scene.add(new THREE.HemisphereLight(0xd6e6f5, 0x66604f, 0.6));
const sun = new THREE.DirectionalLight(0xfff1dc, 1.35);
const X0 = D.x_min || 0;
const ext = Math.max(D.W, D.y_front - D.y_min, 30);
sun.position.set(X0 + D.W * 0.5 - ext * 0.9, ext * 1.15, D.y_front + ext * 1.0);
// the real sun when the site carries a position: plan (x, y-to-yard, z-up) -> three (x, up, z); ?sun=dx,dy,dz overrides
{ let sv = (D.meta && D.meta.sun) ? D.meta.sun : null;
  if (q.get('sun')) sv = q.get('sun').split(',').map(Number);
  if (sv) { const R_ = ext * 2.2, cx = X0 + D.W / 2, cz = (D.y_min + D.y_front) / 2;
    sun.position.set(cx + sv[0] * R_, D.deck_top + sv[2] * R_, cz + sv[1] * R_);
    const low = Math.max(0, Math.min(1, (0.35 - sv[2]) / 0.3));       // warmer, dimmer light near the horizon
    sun.color.setRGB(1.0, 0.95 - 0.12 * low, 0.86 - 0.25 * low); sun.intensity = 1.55 - 0.45 * low; } }
sun.castShadow = true; sun.shadow.mapSize.set(STILL ? 4096 : 2048, STILL ? 4096 : 2048); sun.shadow.radius = 3;
sun.shadow.camera.left = -ext * 1.4; sun.shadow.camera.right = ext * 1.4; sun.shadow.camera.top = ext * 1.4; sun.shadow.camera.bottom = -ext * 1.4;
sun.shadow.camera.near = 1; sun.shadow.camera.far = ext * 6; sun.shadow.bias = -0.0008;
sun.target.position.set(X0 + D.W / 2, D.deck_top, (D.y_min + D.y_front) / 2); scene.add(sun); scene.add(sun.target);

// textures
function grainTex(hexes, vertical, count, alpha, seed) {
  const c = document.createElement('canvas'); const Lp = 1024, Sp = 128;
  c.width = vertical ? Sp : Lp; c.height = vertical ? Lp : Sp;
  const g = c.getContext('2d'); let s = seed;
  const rnd = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  g.fillStyle = hexes[Math.floor(hexes.length / 2)]; g.fillRect(0, 0, c.width, c.height);
  for (let i = 0; i < count; i++) {
    const p = rnd() * Sp, a0 = rnd() * 0.4 * Lp, a1 = Lp * (0.6 + rnd() * 0.4);
    g.strokeStyle = hexes[Math.floor(rnd() * hexes.length)]; g.globalAlpha = alpha * (0.4 + rnd() * 0.6); g.lineWidth = 0.6 + rnd() * 2.2;
    g.beginPath(); if (vertical) { g.moveTo(p, a0); g.lineTo(p + (rnd() - 0.5) * 3, a1); } else { g.moveTo(a0, p); g.lineTo(a1, p + (rnd() - 0.5) * 3); } g.stroke();
  }
  g.globalAlpha = 1;
  const t = new THREE.CanvasTexture(c); t.encoding = THREE.sRGBEncoding; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 4; return t;
}
function patternTex(kind, hex, seed, md) {
  const c = document.createElement('canvas'); c.width = 512; c.height = 512; const g = c.getContext('2d'); let s = seed;
  const rnd = () => { s = (s * 1103515245 + 12345) % 2147483648; return s / 2147483648; };
  g.fillStyle = hex; g.fillRect(0, 0, 512, 512);
  if (kind === 'stone') {          // ledgestone: courses of long thin stones in a few greys and tans
    const cols = [shade(hex, -0.28), shade(hex, -0.14), hex, shade(hex, 0.1), shade(hex, 0.2), '#a3907a', '#6f6a63'];
    let y = 0; while (y < 512) { const h = 22 + rnd() * 30; let x = -rnd() * 60; while (x < 512) { const w = 50 + rnd() * 120;
      g.fillStyle = cols[Math.floor(rnd() * cols.length)]; g.fillRect(x + 2, y + 2, w - 4, h - 4); x += w; } y += h; }
    g.globalAlpha = 0.35; g.fillStyle = '#3a3632'; for (let i = 0; i < 400; i++) g.fillRect(rnd() * 512, rnd() * 512, 2, 2); g.globalAlpha = 1;
  } else if (kind === 'lap') {     // horizontal lap siding, 6" exposure at 512px = 8'
    for (let y = 0; y < 512; y += 32) { g.fillStyle = shade(hex, -0.22); g.fillRect(0, y, 512, 3); g.fillStyle = shade(hex, 0.06); g.fillRect(0, y + 3, 512, 2); }
  } else if (kind === 'batten') {  // board & batten, 12" battens
    for (let x = 0; x < 512; x += 64) { g.fillStyle = shade(hex, -0.25); g.fillRect(x, 0, 6, 512); g.fillStyle = shade(hex, 0.08); g.fillRect(x + 6, 0, 2, 512); }
    g.globalAlpha = 0.18; for (let i = 0; i < 120; i++) { g.fillStyle = rnd() > 0.5 ? '#000' : '#fff'; g.fillRect(rnd() * 512, rnd() * 512, 1, 40 + rnd() * 120); } g.globalAlpha = 1;
  } else if (kind === 'brick') {   // running bond: 8" x 2-2/3" modular brick, 512px = 8'
    const bh = 512 / 36, bw = 512 / 12;
    for (let r = 0; r < 36; r++) { const off = (r % 2) * bw / 2; for (let c = -1; c < 13; c++) {
      g.fillStyle = [shade(hex, -0.12), hex, shade(hex, 0.1), shade(hex, -0.05), shade(hex, 0.18)][Math.floor(rnd() * 5)];
      g.fillRect(c * bw + off + 1.5, r * bh + 1.5, bw - 3, bh - 3); } }
    g.globalAlpha = 0.5; g.fillStyle = '#b9b0a4'; for (let r = 0; r <= 36; r++) g.fillRect(0, r * bh - 0.5, 512, 1.5); g.globalAlpha = 1;
  } else if (kind === 'seam') {    // standing seam: 1-1/2" ribs at 16" OC (512px = 8'), a highlight and a shadow on each rib
    for (let x = 0; x < 512; x += 85.33) { g.fillStyle = shade(hex, 0.35); g.fillRect(x, 0, 5, 512); g.fillStyle = shade(hex, -0.45); g.fillRect(x + 5, 0, 4, 512); }
    g.globalAlpha = 0.08; for (let i = 0; i < 300; i++) { g.fillStyle = i % 2 ? '#000' : '#fff'; g.fillRect(rnd() * 512, rnd() * 512, 1, 20 + rnd() * 80); } g.globalAlpha = 1;
  } else if (kind === 'grass') {
    for (let i = 0; i < 26000; i++) { g.fillStyle = [shade(hex, -0.16), shade(hex, -0.08), shade(hex, 0.08), shade(hex, 0.16), '#93a267', '#6f8c48'][Math.floor(rnd() * 6)]; g.globalAlpha = 0.6 + rnd() * 0.4; g.fillRect(rnd() * 512, rnd() * 512, 1, 1 + rnd() * 2); } g.globalAlpha = 1;
  } else if (kind === 'louver') {  // plantation shutters: 3-1/2" louvers, a shadow under each blade
    for (let y = 0; y < 512; y += 18) { g.fillStyle = shade(hex, -0.28); g.fillRect(0, y + 13, 512, 4); g.fillStyle = shade(hex, 0.04); g.fillRect(0, y, 512, 3); }
  } else if (kind === 'shingle') { // asphalt shingles: 5" courses, staggered tabs, granule speckle
    for (let y = 0; y < 512; y += 21) { const off = (y / 21) % 2 ? 0 : 32; g.fillStyle = shade(hex, -0.3); g.fillRect(0, y + 18, 512, 3);
      for (let x = -off; x < 512; x += 64) { g.fillStyle = [shade(hex, -0.1), hex, shade(hex, 0.08), shade(hex, -0.04)][Math.floor(rnd() * 4)]; g.fillRect(x + 1, y, 62, 18); } }
    g.globalAlpha = 0.25; for (let i = 0; i < 9000; i++) { g.fillStyle = rnd() > 0.5 ? '#000' : '#fff'; g.fillRect(rnd() * 512, rnd() * 512, 1, 1); } g.globalAlpha = 1;
  } else if (kind === 'paver') {  // 4x8 clay pavers, basketweave (8" squares of two bricks, alternating), 512px = 8'
    const u = 512 / 24;
    for (let i = 0; i < 12; i++) for (let j = 0; j < 12; j++) { for (let k = 0; k < 2; k++) {
      g.fillStyle = [shade(hex, -0.12), hex, shade(hex, 0.1), shade(hex, -0.05), shade(hex, 0.16)][Math.floor(rnd() * 5)];
      if ((i + j) % 2) g.fillRect(i * 2 * u + 1.5, j * 2 * u + k * u + 1.5, 2 * u - 3, u - 3); else g.fillRect(i * 2 * u + k * u + 1.5, j * 2 * u + 1.5, u - 3, 2 * u - 3); } }
  } else if (kind === 'hbrick') {  // the house's face brick: running bond, 12 bricks across the 8' tile, courses at the material's course_in (8'/tile), mottled buff tones, light mortar
    const nc = Math.round(96 / ((md && md.course_in) || 2.6667)), bh = 512 / nc, bw = 512 / 12, jt = 1.6;
    g.fillStyle = shade(hex, 0.18); g.fillRect(0, 0, 512, 512);
    for (let r = 0; r < nc; r++) { const off = (r % 2) * bw / 2; for (let c = -1; c < 13; c++) {
      const tones = [shade(hex, -0.14), shade(hex, -0.06), hex, hex, shade(hex, 0.07), shade(hex, 0.14), shade(hex, 0.04), shade(hex, -0.22)];
      g.fillStyle = tones[Math.floor(rnd() * tones.length)];
      g.fillRect(c * bw + off + jt / 2, r * bh + jt / 2, bw - jt, bh - jt);
      g.globalAlpha = 0.25; g.fillStyle = shade(hex, 0.25); g.fillRect(c * bw + off + jt / 2 + rnd() * bw * 0.5, r * bh + jt / 2, bw * (0.2 + rnd() * 0.3), bh - jt); g.globalAlpha = 1; } }
    g.globalAlpha = 0.18; for (let i = 0; i < 6000; i++) { g.fillStyle = rnd() > 0.5 ? '#000' : '#fff'; g.fillRect(rnd() * 512, rnd() * 512, 1, 1); } g.globalAlpha = 1;
  } else if (kind === 'rsawn') {   // stained rough-sawn plywood / cedar: faint vertical fibre streaks (the grooves are geometry)
    for (let i = 0; i < 900; i++) { g.fillStyle = rnd() > 0.5 ? shade(hex, -0.09) : shade(hex, 0.07); g.globalAlpha = 0.25 + rnd() * 0.35;
      g.fillRect(rnd() * 512, rnd() * 512, 0.6 + rnd() * 1.6, 30 + rnd() * 160); } g.globalAlpha = 1;
  } else if (kind === 'gravel') {
    for (let i = 0; i < 5000; i++) { g.fillStyle = [shade(hex, -0.25), shade(hex, -0.1), shade(hex, 0.12), shade(hex, 0.25)][Math.floor(rnd() * 4)]; g.beginPath(); g.arc(rnd() * 512, rnd() * 512, 1.5 + rnd() * 3, 0, 6.3); g.fill(); }
  }
  const t = new THREE.CanvasTexture(c); t.encoding = THREE.sRGBEncoding; t.wrapS = t.wrapT = THREE.RepeatWrapping; t.anisotropy = 4; return t;
}
const TEX = {};
function texFor(mat, vertical, variant) {
  const k = mat + (vertical ? 'V' : 'H') + variant; if (TEX[k]) return TEX[k];
  const m = D.materials[mat];
  if (m.pattern) { TEX[k] = patternTex(m.pattern, m.color, 5 + mat.length * 3, m); return TEX[k]; }
  let pal = m.palette || [shade(m.color, -0.18), shade(m.color, -0.08), m.color, shade(m.color, 0.08), shade(m.color, 0.16)];
  if (m.palette && variant !== 1) pal = pal.map(h => shade(h, variant === 0 ? -0.07 : 0.07));
  TEX[k] = grainTex(pal, vertical, m.palette ? 110 : 80, m.palette ? 0.6 : 0.55, 11 + mat.length * 7 + variant * 13); return TEX[k];
}
function shade(hex, k) { const n = parseInt(hex.slice(1), 16); let r = (n >> 16) & 255, g = (n >> 8) & 255, b = n & 255;
  r = Math.max(0, Math.min(255, Math.round(r * (1 + k)))); g = Math.max(0, Math.min(255, Math.round(g * (1 + k)))); b = Math.max(0, Math.min(255, Math.round(b * (1 + k))));
  return '#' + ((r << 16) | (g << 8) | b).toString(16).padStart(6, '0'); }
const MATC = {};
function material(b) {
  const m = D.materials[b.mat] || {color: '#999999'};
  const variant = m.palette ? (b.tone < -0.33 ? 0 : (b.tone > 0.33 ? 2 : 1)) : 1;
  const vertical = (b.y1 - b.y0) > (b.x1 - b.x0);
  const long = Math.max(b.x1 - b.x0, b.y1 - b.y0);
  const rep = Math.max(1, Math.round(long / 8));
  const key = b.mat + '|' + ((m.grain || m.pattern) ? (vertical ? 'V' : 'H') : '') + '|' + variant + '|' + rep + '|' + (m.pattern ? (b.shape === 'mesh' ? 'mesh' : Math.round(long) + 'x' + Math.round(b.z1 - b.z0)) : '');
  if (MATC[key]) return MATC[key];
  const opts = {roughness: m.rough == null ? 0.8 : m.rough, metalness: m.metal || 0};
  if (m.grain) { const t = texFor(b.mat, vertical, variant).clone(); t.needsUpdate = true; t.repeat.set(vertical ? 1 : rep, vertical ? rep : 1); opts.map = t; opts.color = new THREE.Color(0xffffff); }
  else if (m.pattern) { const t = texFor(b.mat, false, 1).clone(); t.needsUpdate = true;
    const per = m.pattern === 'grass' ? 5 : (m.pattern === 'gravel' ? 6 : 8);   // feet per tile
    if (b.shape === 'mesh') t.repeat.set(8 / per, 8 / per); else
    t.repeat.set(Math.max(1, long / per), Math.max(1, Math.max(b.z1 - b.z0, Math.min(b.x1 - b.x0, b.y1 - b.y0)) / per)); opts.map = t; opts.color = new THREE.Color(0xffffff); }
  else { opts.color = new THREE.Color(m.color).convertSRGBToLinear(); }
  if (b.mat === 'glass') { opts.envMapIntensity = 1; }
  if (m.glass) { opts.transparent = true; opts.opacity = 0.2; opts.depthWrite = false; }
  if (m.opacity != null && m.opacity < 1) { opts.transparent = true; opts.opacity = m.opacity; opts.side = THREE.DoubleSide; }
  const mm = new THREE.MeshStandardMaterial(opts); MATC[key] = mm; return mm;
}
const EDGE_KINDS = new Set(['beam', 'joist', 'post', 'rim', 'ledger', 'board', 'border', 'fascia', 'stone', 'stonecap', 'footing', 'base', 'block', 'drink', 'tub', 'tubrim', 'privacy', 'stringer', 'tread', 'riser', 'wblock']);
const edgeMat = new THREE.LineBasicMaterial({color: 0x1a1612, transparent: true, opacity: 0.22});
// meshes
const phased = [], ctx = [];
for (const b of D.boxes) {
  const w = b.x1 - b.x0, d = b.y1 - b.y0, h = b.z1 - b.z0;
  let geo;
  if (b.shape === 'cyl') geo = new THREE.CylinderGeometry(w / 2, w / 2, h, 24);
  else if (b.shape === 'sphere') { geo = new THREE.IcosahedronGeometry(0.5, 2); geo.scale(w, h, d); }
  else if (b.shape === 'cone') geo = new THREE.ConeGeometry(w / 2, h, 14);
  else if (b.shape === 'mesh' && b.pts) {                       // a shade sail: triangles in world coordinates
    geo = new THREE.BufferGeometry();
    const arr = new Float32Array(b.pts.length * 3);
    b.pts.forEach((q, i) => { arr[i * 3] = q[0]; arr[i * 3 + 1] = q[2]; arr[i * 3 + 2] = q[1]; });
    geo.setAttribute('position', new THREE.BufferAttribute(arr, 3)); geo.computeVertexNormals();
    const uv = new Float32Array(b.pts.length * 2);
    for (let t = 0; t + 2 < b.pts.length; t += 3) {
      const A = new THREE.Vector3(arr[t * 3], arr[t * 3 + 1], arr[t * 3 + 2]), B_ = new THREE.Vector3(arr[t * 3 + 3], arr[t * 3 + 4], arr[t * 3 + 5]), C = new THREE.Vector3(arr[t * 3 + 6], arr[t * 3 + 7], arr[t * 3 + 8]);
      const n = B_.clone().sub(A).cross(C.clone().sub(A)).normalize();
      let t1 = new THREE.Vector3(0, 1, 0).cross(n); if (t1.length() < 1e-3) t1.set(1, 0, 0); t1.normalize();
      const t2 = n.clone().cross(t1).normalize(); if (t2.y < 0) t2.multiplyScalar(-1);
      for (let k = 0; k < 3; k++) { const P = new THREE.Vector3(arr[(t + k) * 3], arr[(t + k) * 3 + 1], arr[(t + k) * 3 + 2]); uv[(t + k) * 2] = P.dot(t1) / 8; uv[(t + k) * 2 + 1] = P.dot(t2) / 8; }
    }
    geo.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  }
  else geo = new THREE.BoxGeometry(w, h, d);
  const mat_ = material(b);
  if (b.shape === 'mesh') { mat_.side = THREE.DoubleSide; }
  const mesh = new THREE.Mesh(geo, mat_);
  if (b.shape === 'mesh') mesh.position.set(0, 0, 0); else
  mesh.position.set((b.x0 + b.x1) / 2, (b.z0 + b.z1) / 2, (b.y0 + b.y1) / 2);
  if (b.rot) { if (b.rot_axis === 'x') mesh.rotation.x = b.rot; else if (b.rot_axis === 'z') mesh.rotation.y = -b.rot; else mesh.rotation.z = b.rot; }
  mesh.castShadow = b.kind !== 'ground' && b.kind !== 'gravel' && b.kind !== 'roof'; mesh.receiveShadow = true;
  mesh.userData = {phase: b.phase, y0: mesh.position.y, kind: b.kind, tag: b.tag, xg: b.xg || 0, tr0: !!mat_.transparent, op0: mat_.opacity};
  if (EDGE_KINDS.has(b.kind) && b.shape !== 'cyl' && w > 0.05 && d > 0.05) { const e = new THREE.LineSegments(new THREE.EdgesGeometry(geo), edgeMat); mesh.add(e); }
  scene.add(mesh); if (b.phase > 0) phased.push(mesh);
  if (b.kind === 'house' || b.kind === 'wall' || b.kind === 'roof' || b.kind === 'trim' || b.kind === 'glass' || b.kind === 'tree' || b.kind === 'fence') ctx.push(mesh);
}
const HIDE_TECH = new Set(['tree', 'fence']);          // trees and lot fences never stand in front of a technical still
function ctxShown(o, on) { const k = o.userData.kind; if (HIDE_TECH.has(k)) return !on && !TECH; return k === 'roof' ? !on : true; }
if (TECH) for (const o of ctx) if (HIDE_TECH.has(o.userData.kind)) o.visible = false;
const GAP = {1: 0, 2: 0, 3: 0, 4: 5, 5: 9, 6: 14, 7: 19, 8: 23};
function applyPhase(n) { for (const o of phased) o.visible = o.userData.phase <= n; }
function explode(on) {
  for (const o of phased) o.position.y = o.userData.y0 + (on ? (GAP[o.userData.phase] || 0) + o.userData.xg : 0);
  explodeCtx(on);
}
function explodeCtx(on) { for (const o of ctx) { if (o.userData.kind === 'roof' || HIDE_TECH.has(o.userData.kind)) o.visible = ctxShown(o, on); else { const u = o.userData; o.material = o.material.clone(); o.material.transparent = on || u.tr0; o.material.opacity = on ? Math.min(0.3, u.op0) : u.op0; o.material.depthWrite = !(on || u.tr0); } } }
function explodedTop() { let t = 0; for (const o of phased) if (o.visible) { o.geometry.computeBoundingBox(); t = Math.max(t, o.position.y + o.geometry.boundingBox.max.y); } return t; }
// camera + orbit
const persp = new THREE.PerspectiveCamera(40, W / H, 0.5, 2000);
if (q.get('fov')) { persp.fov = parseFloat(q.get('fov')); persp.updateProjectionMatrix(); }
const cx = X0 + D.W / 2, cy = (D.y_min + D.y_front) / 2, zt = D.deck_top, span = Math.max(D.W, D.y_front - D.y_min, 24);
const planW = D.W + 16, planD = (D.y_front - D.y_min) + 22;
const planHalf = Math.max(planW / 2, planD / 2 * (W / H));
const ortho = new THREE.OrthographicCamera(-planHalf, planHalf, planHalf * H / W, -planHalf * H / W, 0.5, 2000);
let cam = persp;
const VIEWS = {
  yard:   {pos: [cx + span * 0.1, zt + 6.0, D.y_front + span * 1.0], at: [cx, zt - 0.6, cy]},
  facade: {pos: [cx + span * 0.05, zt + 9.0, D.y_front + span * 1.75], at: [cx, zt + 9.0, cy - 2]},
  facade2: {pos: [cx - span * 0.75, zt + 12.0, D.y_front + span * 1.35], at: [cx, zt + 8.5, cy - 2]},
  corner: {pos: [X0 + D.W + span * 0.5, zt + 6.5, D.y_front + span * 0.5], at: [cx, zt - 1.0, cy]},
  ondeck: {pos: [X0 + Math.min(D.W - 2, 2.5), zt + 5.6, D.y_front - 2.2], at: [X0 + D.W * 0.92, zt + 0.4, D.y_front - Math.min(6, span * 0.3)]},
  iso:    {pos: [cx + span * 0.95, zt + span * 0.7, D.y_front + span * 0.8], at: [cx, zt - 2, cy]},
  plan:   {pos: [cx, zt + 120, cy - 4 + 0.001], at: [cx, 0, cy - 4], up: [0, 0, -1], ortho: true},
  under:  {pos: [cx + span * 0.22, Math.min(zt * 0.45 + 0.4, 3.2), D.y_front + Math.max(7, span * 0.42)], at: [cx, zt - 1.3, cy - 2]},
  iso2:   {pos: [cx - span * 0.95, zt + span * 0.7, D.y_front + span * 0.8], at: [cx, zt - 2, cy]},
  isolow: {pos: [cx + span * 0.85, zt + 2.2, D.y_front + span * 0.95], at: [cx, zt - 1.2, cy]},
  underiso: {pos: [cx - span * 0.55, Math.max(1.2, zt * 0.25), D.y_front + span * 0.7], at: [cx, zt - 2.2, cy - 2]},
};
// technical stills (build steps, explosions, structure, plan, under) frame the deck with the generic cameras and no trees
const GVIEWS = Object.assign({}, VIEWS);
// a measured site's own camera stations (plan feet: x along the wall, y into the yard, z up) replace the generic ones
if (D.meta && D.meta.cameras) for (const [k, c] of Object.entries(D.meta.cameras)) VIEWS[k] = {pos: [c.pos[0], c.pos[2], c.pos[1]], at: [c.at[0], c.at[2], c.at[1]], fov: c.fov};
// ?cam=x,y,z&at=x,y,z in plan feet (x along the wall, y into the yard, z up): a free camera for close checks
if (q.get('cam') && q.get('at')) { const c_ = q.get('cam').split(',').map(Number), a_ = q.get('at').split(',').map(Number);
  VIEWS.custom = {pos: [c_[0], c_[2], c_[1]], at: [a_[0], a_[2], a_[1]]}; }
// a shade sail above the deck: pull the outside views back and up so the whole sail and its posts are in frame
(function () {
  const sails = D.boxes.filter(b => b.kind === 'sail');
  if (!sails.length) return;
  const top = Math.max(...sails.map(b => b.z1)), lift = (top - zt) * 0.5;
  for (const k of ['yard', 'corner', 'iso', 'iso2', 'isolow']) {
    const v = VIEWS[k]; const at = [v.at[0], v.at[1] + lift, v.at[2]];
    const dv = [v.pos[0] - v.at[0], v.pos[1] - v.at[1], v.pos[2] - v.at[2]];
    v.at = at; v.pos = [at[0] + dv[0] * 1.35, at[1] + dv[1] * 1.35 + 1.5, at[2] + dv[2] * 1.35];
  }
})();
function planMode(on) {
  if (renderer.shadowMap.enabled === on) { renderer.shadowMap.enabled = !on; scene.traverse(o => { if (o.material) o.material.needsUpdate = true; }); }   // a plan has no cast shadows
  for (const o of ctx) { o.castShadow = !on && o.userData.kind !== 'glass'; if (o.userData.kind === 'roof' || HIDE_TECH.has(o.userData.kind)) o.visible = ctxShown(o, on); else { const u = o.userData; o.material = o.material.clone(); o.material.transparent = on || u.tr0; o.material.opacity = on ? Math.min(0.28, u.op0) : u.op0; o.material.depthWrite = !(on || u.tr0); } }
}
let target = new THREE.Vector3(), sph = new THREE.Spherical();
let curView = VIEW0;
function setView(name) {
  curView = name;
  const v = (TECH && GVIEWS[name]) ? GVIEWS[name] : (VIEWS[name] || VIEWS.yard); cam = v.ortho ? ortho : persp; planMode(!!v.ortho);
  if (!v.ortho) { const f_ = q.get('fov') ? parseFloat(q.get('fov')) : (v.fov || 40); if (persp.fov !== f_) { persp.fov = f_; persp.updateProjectionMatrix(); } }
  cam.up.set(...(v.up || [0, 1, 0]));
  cam.position.set(...v.pos); target.set(...v.at); sph.setFromVector3(cam.position.clone().sub(target));
  if (typeof exploded !== 'undefined' && exploded && !v.ortho) {      // frame the whole lifted stack, the roof covers included; the house goes see-through
    explodeCtx(true);
    const lift = Math.max(0, explodedTop() - zt);
    target.y += lift * 0.45; sph.radius *= 1 + lift / (span * 1.7);
  }
  update();
  root.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === name));
}
function update() { cam.position.setFromSpherical(sph).add(target); cam.lookAt(target); }
let drag = null, pinch = null;
const el = renderer.domElement;
el.addEventListener('pointerdown', e => { drag = {x: e.clientX, y: e.clientY}; el.setPointerCapture(e.pointerId); });
el.addEventListener('pointermove', e => { if (!drag) return; const dx = e.clientX - drag.x, dy = e.clientY - drag.y; drag = {x: e.clientX, y: e.clientY};
  sph.theta -= dx * 0.005; sph.phi = Math.max(0.05, Math.min(Math.PI / 2 - 0.02, sph.phi - dy * 0.005)); update(); });
el.addEventListener('pointerup', () => drag = null); el.addEventListener('pointercancel', () => drag = null);
el.addEventListener('wheel', e => { e.preventDefault(); sph.radius = Math.max(4, Math.min(600, sph.radius * (1 + e.deltaY * 0.001))); update(); }, {passive: false});
el.addEventListener('touchstart', e => { if (e.touches.length === 2) pinch = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); }, {passive: true});
el.addEventListener('touchmove', e => { if (e.touches.length === 2 && pinch) { const d = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY); sph.radius = Math.max(4, Math.min(600, sph.radius * pinch / d)); pinch = d; update(); } }, {passive: true});
// ui
const cap = root.querySelector('.v3d-cap');
let phase = PHASE0, exploded = EXPLODE0;
function setPhase(n) { phase = n; applyPhase(n); if (cap) cap.textContent = (D.meta.step_text[n] || '') + (exploded ? ' · exploded' : '');
  root.querySelectorAll('[data-step]').forEach(b => b.classList.toggle('on', parseInt(b.dataset.step, 10) === n)); }
root.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
root.querySelectorAll('[data-step]').forEach(b => b.addEventListener('click', () => setPhase(parseInt(b.dataset.step, 10))));
const ex = root.querySelector('.v3d-explode'); if (ex) ex.addEventListener('click', () => { exploded = !exploded; explode(exploded); ex.classList.toggle('on', exploded); setPhase(phase); setView(curView); });
if (STILL) { root.querySelectorAll('.v3d-ui').forEach(u => u.style.display = 'none'); }
explode(exploded); if (ex) ex.classList.toggle('on', exploded);
setPhase(phase); setView(VIEW0);
function frame() { renderer.render(scene, cam); }
frame(); window.__ready = true;
if (!STILL) { (function loop() { requestAnimationFrame(loop); frame(); })(); }
window.addEventListener('resize', () => { const w = root.clientWidth, h = root.clientHeight; renderer.setSize(w, h); persp.aspect = w / h; persp.updateProjectionMatrix(); ortho.top = planHalf * h / w; ortho.bottom = -ortho.top; ortho.updateProjectionMatrix(); });
})();
"""


def viewer_html(scene: Scene, three_src: Optional[str] = None, title: str = "3D model", standalone: bool = True, uid: str = "v3d") -> str:
    """three_src: None -> cdnjs script tag; a string -> inlined three.js source (for headless renders)."""
    data = json.dumps(scene.to_dict())
    three = CDN_THREE if three_src is None else f"<script>{three_src}</script>"
    steps = "".join(f'<button type="button" data-step="{n}">{n}</button>' for n in range(1, 9))
    ui = f'''<div class="v3d-ui v3d-top"><span class="v3d-title">{title}</span><span class="v3d-cap"></span></div>
<div class="v3d-ui v3d-bar">
  <span class="grp"><button type="button" data-view="yard" class="on">Yard</button><button type="button" data-view="corner">Corner</button><button type="button" data-view="ondeck">On deck</button><button type="button" data-view="iso">Iso</button><button type="button" data-view="plan">Plan</button><button type="button" data-view="under">Under</button><button type="button" data-view="iso2">Iso 2</button><button type="button" data-view="isolow">Low</button><button type="button" data-view="underiso">Under iso</button></span>
  <span class="grp"><span class="lbl">Step</span>{steps}<button type="button" class="v3d-explode">Exploded</button></span>
</div>'''
    css = '''<style>
.v3d-root{position:relative;width:100%;height:100%;min-height:360px;background:#dbe7f1;overflow:hidden;touch-action:none;}
.v3d-root canvas{display:block;width:100%!important;height:100%!important;}
.v3d-ui{position:absolute;left:0;right:0;font-family:"Nunito Sans",system-ui,sans-serif;pointer-events:none;}
.v3d-top{top:0;padding:8px 12px;display:flex;justify-content:space-between;gap:10px;color:#fff;text-shadow:0 1px 3px rgba(0,0,0,.6);font-size:13px;flex-wrap:wrap;}
.v3d-title{font-weight:800;letter-spacing:.08em;text-transform:uppercase;font-size:11px;}
.v3d-bar{bottom:0;padding:8px 10px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap;background:linear-gradient(transparent,rgba(0,0,0,.55));}
.v3d-bar .grp{display:flex;gap:4px;flex-wrap:wrap;pointer-events:auto;align-items:center;}
.v3d-bar .lbl{color:#fff;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;margin-right:4px;}
.v3d-bar button{background:rgba(0,0,0,.55);color:#fff;border:1px solid rgba(255,255,255,.35);border-radius:4px;padding:6px 9px;font:inherit;font-size:12px;font-weight:700;cursor:pointer;min-width:30px;}
.v3d-bar button.on{background:#d49e1b;color:#111;border-color:#d49e1b;}
.v3d-bar button:focus-visible{outline:2px solid #fff;}
</style>'''
    body = f'{css}<div id="{uid}" class="v3d-root">{ui}</div>{three}<script>{JS.replace("__DATA__", data).replace("__UID__", uid)}</script>'
    if standalone:
        return f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>html,body{{margin:0;height:100%;}}</style></head><body>{body}</body></html>'
    return body
