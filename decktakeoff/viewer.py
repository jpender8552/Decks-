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
const root = document.getElementById('v3d');
const W = root.clientWidth || window.innerWidth, H = root.clientHeight || window.innerHeight;
const renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
renderer.setPixelRatio(STILL ? 1 : Math.min(window.devicePixelRatio, 2));
renderer.setSize(W, H);
renderer.outputEncoding = THREE.sRGBEncoding;
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
scene.add(new THREE.HemisphereLight(0xcfe3f7, 0x6f6a55, 0.55));
const sun = new THREE.DirectionalLight(0xfff3df, 0.95);
const ext = Math.max(D.W, D.y_front - D.y_min, 30);
sun.position.set(D.W * 0.5 - ext * 0.8, ext * 1.6, D.y_front + ext * 0.9);
sun.castShadow = true; sun.shadow.mapSize.set(2048, 2048);
sun.shadow.camera.left = -ext * 1.4; sun.shadow.camera.right = ext * 1.4; sun.shadow.camera.top = ext * 1.4; sun.shadow.camera.bottom = -ext * 1.4;
sun.shadow.camera.near = 1; sun.shadow.camera.far = ext * 6; sun.shadow.bias = -0.0008;
sun.target.position.set(D.W / 2, D.deck_top, (D.y_min + D.y_front) / 2); scene.add(sun); scene.add(sun.target);
scene.add(new THREE.AmbientLight(0xffffff, 0.08));
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
const TEX = {};
function texFor(mat, vertical, variant) {
  const k = mat + (vertical ? 'V' : 'H') + variant; if (TEX[k]) return TEX[k];
  const m = D.materials[mat];
  let pal = m.palette || [shade(m.color, -0.18), shade(m.color, -0.08), m.color, shade(m.color, 0.08), shade(m.color, 0.16)];
  // board-to-board variation: each variant is the palette shifted a step darker / lighter
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
  const key = b.mat + '|' + (m.grain ? (vertical ? 'V' : 'H') : '') + '|' + variant + '|' + rep;
  if (MATC[key]) return MATC[key];
  const opts = {roughness: m.rough == null ? 0.8 : m.rough, metalness: m.metal || 0};
  if (m.grain) { const t = texFor(b.mat, vertical, variant).clone(); t.needsUpdate = true; t.repeat.set(vertical ? 1 : rep, vertical ? rep : 1); opts.map = t; opts.color = new THREE.Color(0xffffff); }
  else { opts.color = new THREE.Color(m.color).convertSRGBToLinear(); }
  const mm = new THREE.MeshStandardMaterial(opts); MATC[key] = mm; return mm;
}
// meshes
const phased = [];
for (const b of D.boxes) {
  const w = b.x1 - b.x0, d = b.y1 - b.y0, h = b.z1 - b.z0;
  let geo;
  if (b.shape === 'cyl') geo = new THREE.CylinderGeometry(w / 2, w / 2, h, 24);
  else geo = new THREE.BoxGeometry(w, h, d);
  const mesh = new THREE.Mesh(geo, material(b));
  mesh.position.set((b.x0 + b.x1) / 2, (b.z0 + b.z1) / 2, (b.y0 + b.y1) / 2);
  mesh.castShadow = b.kind !== 'ground' && b.kind !== 'gravel' && b.kind !== 'roof'; mesh.receiveShadow = true;
  mesh.userData = {phase: b.phase, y0: mesh.position.y, kind: b.kind, tag: b.tag};
  scene.add(mesh); if (b.phase > 0) phased.push(mesh);
}
const GAP = {1: 0, 2: 0, 3: 0, 4: 5, 5: 9, 6: 14, 7: 19, 8: 23};
function applyPhase(n) { for (const o of phased) o.visible = o.userData.phase <= n; }
function explode(on) { for (const o of phased) o.position.y = o.userData.y0 + (on ? (GAP[o.userData.phase] || 0) : 0); }
// camera + orbit
const cam = new THREE.PerspectiveCamera(42, W / H, 0.5, 2000);
const cx = D.W / 2, cy = (D.y_min + D.y_front) / 2, zt = D.deck_top, span = Math.max(D.W, D.y_front - D.y_min, 24);
const VIEWS = {
  yard:   {pos: [cx + span * 0.12, zt + 5.8, D.y_front + span * 1.05], at: [cx, zt - 0.5, cy]},
  corner: {pos: [D.W + span * 0.55, zt + 7.0, D.y_front + span * 0.55], at: [cx, zt - 1.0, cy]},
  ondeck: {pos: [Math.min(D.W - 2, 2.5), zt + 5.6, D.y_front - 2.2], at: [D.W * 0.92, zt + 0.4, D.y_front - Math.min(6, span * 0.3)]},
  iso:    {pos: [cx + span * 0.95, zt + span * 0.75, D.y_front + span * 0.8], at: [cx, zt - 2, cy]},
  plan:   {pos: [cx, zt + span * 1.55, cy + 0.02], at: [cx, 0, cy], up: [0, 0, -1]},
  under:  {pos: [cx + span * 0.3, Math.max(2.2, zt * 0.35), D.y_front + span * 0.7], at: [cx, Math.max(2.5, zt * 0.5), cy]},
};
let target = new THREE.Vector3(), sph = new THREE.Spherical();
function setView(name) {
  const v = VIEWS[name] || VIEWS.yard; cam.up.set(...(v.up || [0, 1, 0]));
  cam.position.set(...v.pos); target.set(...v.at); sph.setFromVector3(cam.position.clone().sub(target)); update();
  document.querySelectorAll('[data-view]').forEach(b => b.classList.toggle('on', b.dataset.view === name));
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
const cap = document.getElementById('v3d-cap');
let phase = PHASE0, exploded = EXPLODE0;
function setPhase(n) { phase = n; applyPhase(n); if (cap) cap.textContent = (D.meta.step_text[n] || '') + (exploded ? ' · exploded' : '');
  document.querySelectorAll('[data-step]').forEach(b => b.classList.toggle('on', parseInt(b.dataset.step, 10) === n)); }
document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => setView(b.dataset.view)));
document.querySelectorAll('[data-step]').forEach(b => b.addEventListener('click', () => setPhase(parseInt(b.dataset.step, 10))));
const ex = document.getElementById('v3d-explode'); if (ex) ex.addEventListener('click', () => { exploded = !exploded; explode(exploded); ex.classList.toggle('on', exploded); setPhase(phase); });
if (STILL) { document.querySelectorAll('.v3d-ui').forEach(u => u.style.display = 'none'); }
explode(exploded); if (ex) ex.classList.toggle('on', exploded);
setPhase(phase); setView(VIEW0);
function frame() { renderer.render(scene, cam); }
frame(); window.__ready = true;
if (!STILL) { (function loop() { requestAnimationFrame(loop); frame(); })(); }
window.addEventListener('resize', () => { const w = root.clientWidth, h = root.clientHeight; renderer.setSize(w, h); cam.aspect = w / h; cam.updateProjectionMatrix(); });
})();
"""


def viewer_html(scene: Scene, three_src: Optional[str] = None, title: str = "3D model", standalone: bool = True) -> str:
    """three_src: None -> cdnjs script tag; a string -> inlined three.js source (for headless renders)."""
    data = json.dumps(scene.to_dict())
    three = CDN_THREE if three_src is None else f"<script>{three_src}</script>"
    steps = "".join(f'<button type="button" data-step="{n}">{n}</button>' for n in range(1, 9))
    ui = f'''<div class="v3d-ui v3d-top"><span class="v3d-title">{title}</span><span id="v3d-cap" class="v3d-cap"></span></div>
<div class="v3d-ui v3d-bar">
  <span class="grp"><button type="button" data-view="yard" class="on">Yard</button><button type="button" data-view="corner">Corner</button><button type="button" data-view="ondeck">On deck</button><button type="button" data-view="iso">Iso</button><button type="button" data-view="plan">Plan</button><button type="button" data-view="under">Under</button></span>
  <span class="grp"><span class="lbl">Step</span>{steps}<button type="button" id="v3d-explode">Exploded</button></span>
</div>'''
    css = '''<style>
#v3d{position:relative;width:100%;height:100%;min-height:360px;background:#dbe7f1;overflow:hidden;touch-action:none;}
#v3d canvas{display:block;width:100%!important;height:100%!important;}
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
    body = f'{css}<div id="v3d">{ui}</div>{three}<script>{JS.replace("__DATA__", data)}</script>'
    if standalone:
        return f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title><style>html,body{{margin:0;height:100%;}}</style></head><body>{body}</body></html>'
    return body
