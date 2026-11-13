/**
 * Bisco — 2D raster rig runtime (prototype).
 *
 * One <svg viewBox="0 0 1024 1024">: every image is placed in the SAME canvas
 * coordinates as the approved pack (crop boxes come from rig.json), so layers
 * can never drift apart. Whole-character motion (float / click / tilt) is
 * applied to shared HTML parents only.
 *
 * Face = five slots (brow_left, brow_right, eye_left, eye_right, mouth).
 * Each expression PNG was losslessly partitioned into those parts, so exactly
 * ONE expression part is visible per slot at rest (no neutral features are
 * ever stacked on an expression). During a transition the outgoing part is
 * carried onto the incoming one (translate / rotate / scale) and the two only
 * cross-fade while co-located: no doubled eyes or mouths in two places.
 */

export const STATES = [
  'neutral', 'happy', 'thinking', 'clarification', 'answering',
  'surprise', 'abstained', 'error', 'blink', 'looking',
];

export const STATE_LABELS = {
  neutral: 'Neutral', happy: 'Happy', thinking: 'Thinking', clarification: 'Clarification',
  answering: 'Answering', surprise: 'Surprise', abstained: 'Abstained', error: 'Error',
  blink: 'Blink', looking: 'Looking',
};

const SVGNS = 'http://www.w3.org/2000/svg';
const SLOTS = ['brow_left', 'brow_right', 'eye_left', 'eye_right', 'mouth'];
const GAZE_MAX = 8; // canvas px (spec: 6–8 px at 1024)

const PROFILES = {
  home: { float: true, boil: true, tracking: true, saccades: true, boilFactor: 1 },
  processing: { float: true, boil: true, tracking: false, saccades: true, boilFactor: 1 },
  avatar: { float: false, boil: true, tracking: false, saccades: true, boilFactor: 2.5 }, // 44 px: rare, calm
};

// Line-boil cadence per state, seconds [min, max] between episodes.
const BOIL_INTERVAL = {
  default: [10, 30],
  thinking: [3, 8],
  answering: [25, 45],
};
// v3 base: softer, rarer episodes (registered frames, cross-faded)
const BOIL_INTERVAL_V3 = {
  default: [12, 30],
  thinking: [6, 13],      // a bit more alive while thinking
  answering: [40, 70],    // discreet while the user reads
  abstained: [35, 60],    // minimal, no drama
  error: [35, 60],
};
// frames per v3 episode [min, max]
const BOIL_FRAMES_V3 = { default: [2, 3], thinking: [3, 3], abstained: [2, 2], error: [2, 2], answering: [2, 2] };

/**
 * Contextual eye movement per state (canvas px, before clamping to the real white).
 * every: seconds between gaze decisions · tau: gaze spring (ms) · pick(rand, i): next target.
 * Saccade-like (quick move, then hold) — never a continuous drift, so eyes don't "float".
 */
const R = (rand, a, b) => a + rand() * (b - a);
const OPEN_LID_FADE = 45; // ms: closed-lid curve fades before the white re-opens
const OVERLAP_START = 4.0; // gaze x (canvas px) where the left eye starts to advance
const OVERLAP_FULL = 7.6;  // full overlap (gaze max is 8 px)
const LEFT_PUPIL_MAX_X = 8; // safety bound; with the completed left white the pupil has ~40 px of room
function polar(rand, rmin, rmax, squashY = 0.8) {
  const a = rand() * Math.PI * 2; const r = rmin + rand() * (rmax - rmin);
  return [Math.cos(a) * r, Math.sin(a) * r * squashY];
}
export const GAZE_PROGRAM = {
  neutral: { every: [1.4, 3.6], tau: 50, pick: (r) => { const p = r();
    if (p < 0.5) return polar(r, 0.5, 1.4);            // fixational micro-movement around rest
    if (p < 0.8) return polar(r, 2.5, 5, 0.7);         // occasional glance
    return [0, 0]; } },
  happy: { every: [2.6, 5], tau: 70, pick: (r) => polar(r, 0.3, 0.9) },                   // warm, steady
  thinking: { every: [0.8, 1.6], tau: 60, pick: (r, i) => {                               // up/side oscillation
    const pts = [[-4, 0.5], [0, 0], [-6, 1.5], [-1.5, 0], [-3, 2.5], [-5, 0]];
    return pts[(i + Math.floor(r() * 2)) % pts.length]; } },
  clarification: { every: [0.6, 1.2], tau: 45, pick: (r, i) => [(i % 2 ? 1 : -1) * R(r, 2, 4), R(r, -1.2, 0.2)], brows: true }, // curious doubt
  answering: { every: [2.4, 4.4], tau: 70, pick: (r) => { const p = polar(r, 0, 0.7); return [p[0], 0.6 + p[1]]; } }, // stable, present
  surprise: { every: [2.8, 5], tau: 40, pick: (r) => polar(r, 0, 0.5) },                 // wide open, little motion
  abstained: { every: [3, 6], tau: 150, pick: (r) => [R(r, -1.5, 1.5), R(r, 1.2, 2.4)] }, // calm, a bit down
  error: { every: [0.35, 0.8], tau: 40, pick: (r) => polar(r, 0.7, 1.8) },               // alert micro-saccades
  looking: { every: [0.9, 1.6], tau: 55, pick: (r, i) => [(i % 2 ? 1 : -1) * R(r, 5, 8), R(r, -1, 1)] }, // lateral scan
  blink: { every: [3, 5], tau: 80, pick: () => [0, 0] },
};

let UID = 0;

const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const lerp = (a, b, u) => a + (b - a) * u;
const smoothstep = (a, b, x) => { const t = clamp((x - a) / (b - a), 0, 1); return t * t * (3 - 2 * t); };
const easeInOut = (u) => (u < 0.5 ? 4 * u * u * u : 1 - Math.pow(-2 * u + 2, 3) / 2);
const easeOut = (u) => 1 - Math.pow(1 - u, 3);
const easeIn = (u) => u * u * u;

function mulberry32(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function svg(tag, attrs = {}) {
  const el = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
  return el;
}

const f2 = (n) => (Math.abs(n) < 1e-4 ? 0 : Math.round(n * 1000) / 1000);

export class BiscoCharacter {
  /**
   * @param {HTMLElement} host  element that will contain the character (sized by CSS)
   * @param {object} rig        data from assets/rig.js
   * @param {object} options
   */
  constructor(host, rig, options = {}) {
    this.host = host;
    this.rig = rig;
    // the page this figure lives in (the UI runs the runtime from a component iframe, on its parent)
    this.win = options.win || host.ownerDocument.defaultView || window;
    this.doc = this.win.document;
    const profile = PROFILES[options.profile || 'home'];
    this.opts = {
      assetsBase: options.assetsBase || './assets',
      profile: options.profile || 'home',
      state: options.state || 'neutral',
      float: options.float ?? profile.float,
      lineBoil: options.lineBoil ?? profile.boil,
      tracking: options.tracking ?? profile.tracking,
      saccades: options.saccades ?? profile.saccades,
      autoBlink: options.autoBlink ?? true,
      boilFactor: options.boilFactor ?? profile.boilFactor,
      reducedMotion: options.reducedMotion || 'auto', // 'auto' | 'reduce' | 'no-preference'
      timeScale: options.timeScale ?? 1, // >1 = faster (tests only)
      seed: options.seed ?? (Math.random() * 2 ** 32) >>> 0,
      label: options.label || 'Bisco',
      tier: options.tier || 'auto',
      // 'full' = structurally complete base reconstructed under the eyes (derived asset);
      // 'original' = approved pack base with the eye cut-out (fallback)
      // 'v3' = normalised v3 base (default when present); 'full' / 'original' = previous bases (rollback)
      base: options.base || (rig.v3 ? 'v3' : rig.body.scribble_full_base ? 'full' : 'original'),
      boilSource: options.boilSource || 'derived', // v3 only: 'derived' (registered) | 'raw' (studies, for comparison)
      headFollow: options.headFollow ?? true,
      interactive: options.interactive ?? true, // false: the page owns click/keyboard and the ARIA role
      overlap: options.overlap ?? true, // left eye advances over the right one on far rightward glances
    };
    this.rand = mulberry32(this.opts.seed);
    this.uid = ++UID;

    this.state = this.opts.state;      // what the face shows
    this.requested = this.opts.state;  // what the app asked for (click reactions return here)

    this._timers = new Map();   // name -> timeout id
    this._tweens = [];
    this._raf = 0;
    this._listeners = [];
    this._observers = [];
    this._els = new Map();      // `${expr}__${part}` -> entry
    this._slots = {};           // slot -> visible entry
    this._gaze = { x: 0, y: 0, tx: 0, ty: 0 };
    this._brow = { y: 0, ty: 0, l: 0, tl: 0, r: 0, tr: 0 };
    this._lid = { l: 0, r: 0 };          // 0 = open, 1 = eye fully closed (white collapsed)
    this._head = { x: 0, y: 0 };         // lagged follower of the gaze ("living head")
    this._gazeTau = 55;
    this._gazeStep = 0;
    this._pointer = null;
    this._lastPointerT = 0;
    this._near = false;
    this._visible = true;
    this._docVisible = !this.doc.hidden;
    this._bodyIndex = 0;
    this._eyesClosedByBlink = false;
    this._destroyed = false;
    this.stats = { boilEpisodes: 0, boilFrames: 0, blinks: 0, transitions: 0, clicks: 0, saccades: 0 };

    this._build();
    this._applyReducedMotionSource();
    this._setFaceInstant(this.state);
    this._observe();
    this._scheduleAll();
  }

  /* ------------------------------------------------------------------ DOM */

  _svg(tag, attrs = {}) {
    const el = this.doc.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, String(v));
    return el;
  }

  _build() {
    const h = this.host;
    h.classList.add('bisco');
    if (this.opts.interactive) {
      h.setAttribute('role', 'button');
      h.setAttribute('tabindex', h.getAttribute('tabindex') ?? '0');
    }
    h.dataset.profile = this.opts.profile;

    this.elFloat = this.doc.createElement('div');
    this.elFloat.className = 'bisco-float';
    this.elSway = this.doc.createElement('div');
    this.elSway.className = 'bisco-sway';
    this.elReact = this.doc.createElement('div');
    this.elReact.className = 'bisco-react';
    this.elTilt = this.doc.createElement('div');
    this.elTilt.className = 'bisco-tilt';

    const s = this._svg('svg', { viewBox: '0 0 1024 1024', class: 'bisco-svg', 'aria-hidden': 'true', focusable: 'false' });
    const defs = this._svg('defs');
    // one alpha mask per eye = that eye's white (transformed together with it when the lid closes)
    const split = this.rig.v3 && this.rig.v3.eye_white_left && this.rig.v3.eye_white_right;
    // left eye = its own completed white (rounded contour) when available: it is the one that overlaps
    this._ewEntries = split ? { l: this.rig.v3.eye_white_left_full || this.rig.v3.eye_white_left, r: this.rig.v3.eye_white_right } : null;
    this._ewMaskImgs = {};
    const maskIds = {};
    // flat-colour helpers for luminance masks (the white PNG is ~250/255, not pure white)
    const flat = (id, color) => {
      const fl = this._svg('filter', { id, x: 0, y: 0, width: 1024, height: 1024, filterUnits: 'userSpaceOnUse', 'color-interpolation-filters': 'sRGB' });
      fl.append(this._svg('feFlood', { 'flood-color': color, result: 'c' }), this._svg('feComposite', { in: 'c', in2: 'SourceAlpha', operator: 'in' }));
      defs.appendChild(fl); return id;
    };
    for (const side of split ? ['l', 'r'] : ['both']) {
      const id = `bisco-ew-${side}-${this.uid}`;
      const mask = this._svg('mask', { id, maskUnits: 'userSpaceOnUse', x: 0, y: 0, width: 1024, height: 1024 });
      if (side === 'r') {
        // right eye: visible white = its own white MINUS the (possibly advanced) left white
        const whiten = flat(`bisco-white-${this.uid}`, '#fff'); const blacken = flat(`bisco-black-${this.uid}`, '#000');
        const gw = this._svg('g', { filter: `url(#${whiten})` }); const gb = this._svg('g', { filter: `url(#${blacken})` });
        const mi = this._img(this._ewEntries.r); gw.appendChild(mi);
        this._ovMaskL = this._img(this._ewEntries.l); gb.appendChild(this._ovMaskL);
        mask.append(gw, gb); this._ewMaskImgs.r = mi;
      } else {
        mask.style.maskType = 'alpha';
        const mi = this._img(side === 'both' ? this.rig.eye_white_mask : this._ewEntries[side]);
        this._ewMaskImgs[side] = mi; mask.appendChild(mi);
      }
      defs.appendChild(mask); maskIds[side] = id;
    }
    // soft contact shadow cast by the advancing left eye onto the right one
    this._ovShadowId = `bisco-ovsh-${this.uid}`;
    const osh = this._svg('filter', { id: this._ovShadowId, x: '-15%', y: '-15%', width: '130%', height: '130%', 'color-interpolation-filters': 'sRGB' });
    this._ovShadow = this._svg('feDropShadow', { dx: '2.5', dy: '0.6', stdDeviation: '2.2', 'flood-color': '#0c205d', 'flood-opacity': '0' });
    osh.appendChild(this._ovShadow); defs.appendChild(osh);
    if (split) {
      const L = this._ewEntries.l.box; const Rb = this._ewEntries.r.box;
      this._ovGeo = { lcx: L[0] + L[2] / 2, lcy: L[1] + L[3] / 2, rx: Rb[0] + Rb[2], rcy: Rb[1] + Rb[3] / 2 };
    }
    this._ovK = 0;
    // closed-lid pivots (centre of the approved blink lid curves)
    const bl = this.rig.expressions.blink.parts;
    this._lidPivot = { l: [bl.eye_left.stats.cx, bl.eye_left.stats.cy], r: [bl.eye_right.stats.cx, bl.eye_right.stats.cy] };
    // small-size legibility: thicken the navy face strokes (lids/brows/mouth) a little below 160 px
    this._legibId = `bisco-legib-${this.uid}`;
    // dilate ALPHA only, fill with the approved navy, original strokes on top (colours untouched)
    const lf = this._svg('filter', { id: this._legibId, x: '-10%', y: '-10%', width: '120%', height: '120%', 'color-interpolation-filters': 'sRGB' });
    this._legibMorph = this._svg('feMorphology', { in: 'SourceAlpha', operator: 'dilate', radius: '0', result: 'thick' });
    const flood = this._svg('feFlood', { 'flood-color': '#0c205d', result: 'navy' });
    const comp = this._svg('feComposite', { in: 'navy', in2: 'thick', operator: 'in', result: 'under' });
    const merge = this._svg('feMerge'); merge.append(this._svg('feMergeNode', { in: 'under' }), this._svg('feMergeNode', { in: 'SourceGraphic' }));
    lf.append(this._legibMorph, flood, comp, merge); defs.appendChild(lf);
    s.appendChild(defs);

    // 1) body: scribble base + 3 boil variants (exactly one visible), 2) outer strokes, 3) eye whites
    this.gBody = this._svg('g', { class: 'b-body' });
    this.gBase = this._svg('g', { class: 'b-base' });
    this._bodyImgs = this._bodySet().map((e) => this._img(e));
    this._bodyImgs.forEach((im, i) => { im.dataset.body = String(i); if (i) im.style.visibility = 'hidden'; this.gBase.appendChild(im); });
    this.gBody.appendChild(this.gBase);
    // reconstructed antialias bands ("fringes"): only drawn when the feature covering them moves.
    // They REPLACE the base pixels: a luminance mask cuts the base out under each active fringe.
    this._fringes = {};
    this._fringeMasks = {};
    this._fringeMaskId = `bisco-fr-${this.uid}`;
    const fmask = this._svg('mask', { id: this._fringeMaskId, maskUnits: 'userSpaceOnUse', x: 0, y: 0, width: 1024, height: 1024 });
    fmask.appendChild(this._svg('rect', { x: 0, y: 0, width: 1024, height: 1024, fill: '#fff' }));
    for (const [name, e] of Object.entries(this.rig.fringe || {})) {
      const im = this._img(e); im.dataset.fringe = name; im.setAttribute('opacity', '0'); im.style.display = 'none';
      this._fringes[name] = im; this.gBody.appendChild(im);
      const me = this.rig.fringe_mask?.[name];
      if (me) { const mi = this._img(me); mi.style.display = 'none'; this._fringeMasks[name] = mi; fmask.appendChild(mi); }
    }
    defs.appendChild(fmask);
    this._faceOffset = [0, 0];
    this._outerImg = this.rig.body.outer_strokes ? this._img(this.rig.body.outer_strokes) : null;
    if (this._outerImg) this.gBody.appendChild(this._outerImg);
    s.appendChild(this.gBody);
    this.gEyes = this._svg('g', { class: 'b-eyes' });
    this._ewImgs = {};
    // combined white at rest (exact antialias at every tier); the halves only while an eye is closing
    this._ewCombined = this._img(this.rig.body.eye_whites); this._ewCombined.dataset.eye = 'both';
    this.gEyes.appendChild(this._ewCombined);
    if (split) for (const side of ['r', 'l']) { const im = this._img(this._ewEntries[side]); im.dataset.eye = side; im.style.display = 'none'; this._ewImgs[side] = im; this.gEyes.appendChild(im); }
    else this._ewImgs.both = this._ewCombined;
    s.appendChild(this.gEyes);
    this._applyBaseVisibility();
    this.host.dataset.base = this.opts.base;

    // 4) face overlay
    this.gFace = this._svg('g', { class: 'b-face' });
    this.gPupils = this._svg('g', { class: 'b-pupils' });
    this._pupilGroups = {};
    for (const side of split ? ['l', 'r'] : ['both']) {
      const g = this._svg('g', { class: `b-pupils-${side}`, mask: `url(#${maskIds[side]})` });
      this._pupilGroups[side] = g; this.gPupils.appendChild(g);
    }
    this.gLids = this._svg('g', { class: 'b-lids' });
    this.gBrows = this._svg('g', { class: 'b-brows' });
    this.gMouth = this._svg('g', { class: 'b-mouth' });
    this.gFace.append(this.gPupils, this.gLids, this.gBrows, this.gMouth);
    s.appendChild(this.gFace);

    this.svg = s;
    this.elTilt.appendChild(s);
    this.elHead = this.doc.createElement('div');
    this.elHead.className = 'bisco-head';
    this.elHead.appendChild(this.elTilt);
    this.elReact.appendChild(this.elHead);
    this.elSway.appendChild(this.elReact);
    this.elFloat.appendChild(this.elSway);
    h.appendChild(this.elFloat);
    this._updateAria();
  }

  _bodySet() {
    if (this.opts.base === 'v3' && this.rig.v3) {
      return [this.rig.v3.base, ...(this.opts.boilSource === 'raw' ? this.rig.v3.boil_raw : this.rig.v3.boil)];
    }
    const full = this.opts.base === 'full' && this.rig.body.scribble_full_base;
    return full ? [this.rig.body.scribble_full_base, ...this.rig.boil_full] : [this.rig.body.scribble_base, ...this.rig.boil];
  }

  _applyBaseVisibility() {
    // the v3 base already contains the peripheral strokes: never stack the old outer_strokes on it
    if (this._outerImg) this._outerImg.style.display = this.opts.base === 'v3' ? 'none' : '';
  }

  /** 'v3' (default) | 'full' (previous reconstruction) | 'original' (approved pack, fallback). */
  setBase(mode) {
    this.opts.base = ['v3', 'full', 'original'].includes(mode) ? mode : 'v3';
    if (this.opts.base === 'v3' && !this.rig.v3) this.opts.base = 'full';
    this._finishTweens();
    this._bodySet().forEach((e, i) => { const im = this._bodyImgs[i]; im._entry = e; im.setAttribute('href', this._href(e)); });
    this.host.dataset.base = this.opts.base;
    this._applyBaseVisibility();
    this._lid.l = this._lid.r = this._lidTargetFor(this.state);
    this._render();
  }

  /** v3 only: boil frames from the registered (derived) set or the raw visual studies. */
  setBoilSource(src) { this.opts.boilSource = src === 'raw' ? 'raw' : 'derived'; this.setBase(this.opts.base); }

  /** Whole-eye closing (white collapses) needs a base that is complete under the eyes. */
  _fullBlinkOK() { return !!this._ewEntries && this.opts.base !== 'original'; }

  _lidTargetFor(state) { return state === 'blink' && this._fullBlinkOK() ? 1 : 0; }

  /** Lab/test only: 'normal' | 'base-only' (scribble without eyes/face) | 'no-outer'. */
  debugView(mode = 'normal') {
    const baseOnly = mode === 'base-only';
    this.gEyes.style.display = baseOnly ? 'none' : '';
    this.gFace.style.display = baseOnly ? 'none' : '';
    this.host.dataset.view = mode;
    this._viewBaseOnly = baseOnly;
    this._render();
  }

  /** Lab/test only: displace the whole eye region (whites + face) to check for exposed gaps. */
  debugFaceOffset(dx = 0, dy = 0) {
    const t = dx || dy ? `translate(${dx} ${dy})` : null;
    for (const g of [this.gEyes, this.gFace]) { if (t) g.setAttribute('transform', t); else g.removeAttribute('transform'); }
    this._faceOffset = [dx, dy];
    this._render();
  }

  /** Opacity of each reconstructed fringe: 0 while its neutral feature sits exactly at rest over it. */
  _fringeOpacity(name) {
    if (this.opts.base !== 'full') return 0;
    if (this._viewBaseOnly) return 1;
    // binary on/off: a partial opacity would attenuate the base twice (mask + source-over)
    if (name === 'eyes') return Math.hypot(...this._faceOffset) > 0.05 || this._lid.l > 0.001 || this._lid.r > 0.001 || this._ovK > 0.001 ? 1 : 0;
    const e = this._els.get(`neutral__${name}`);
    if (!e || !e.shown) return 1;
    let motion = 0;
    if (name.startsWith('brow')) {
      const side = name === 'brow_left' ? this._brow.l : this._brow.r;
      motion = Math.hypot(this._gaze.x * 0.15, this._brow.y + side + this._gaze.y * 0.2) / 1.2;
    }
    if (e.local) motion = 1; // morphing / blinking away from its rest pose
    return Math.max(1 - e.opacity, motion) > 0.02 ? 1 : 0;
  }

  _tierName() {
    if (this.opts.tier !== 'auto') return this.opts.tier;
    const size = this.host.getBoundingClientRect().width || 200;
    const px = size * (this.win.devicePixelRatio || 1);
    return px <= 256 ? 'sm' : px <= 512 ? 'md' : 'hi';
  }

  _href(entry) {
    return `${this.opts.assetsBase}/${entry.files[this._tier || this._tierName()]}`;
  }

  _img(entry) {
    const [x, y, w, h] = entry.box;
    const im = this._svg('image', { x, y, width: w, height: h, preserveAspectRatio: 'none' });
    im._entry = entry;
    im.setAttribute('href', this._href(entry));
    return im;
  }

  _applyLegibility() {
    const size = this.host.getBoundingClientRect().width || 200;
    // ≈ +0.7 screen px of stroke on each side at 44 px, +0.35 px at 100 px; off from 160 px up
    const r = size >= 160 ? 0 : Math.min(12, (0.55 * 1024) / size * (1 - size / 160) * 1.9);
    const want = r > 0.2 ? `url(#${this._legibId})` : null;
    if (want) this._legibMorph.setAttribute('radius', String(f2(r)));
    for (const g of [this.gLids, this.gBrows, this.gMouth]) {
      if (!g) continue;
      if (want) g.setAttribute('filter', want); else g.removeAttribute('filter');
    }
    this.host.dataset.legibility = want ? String(f2(r)) : '0';
  }

  _refreshTier() {
    this._applyLegibility();
    const t = this._tierName();
    if (t === this._tier) return;
    this._tier = t;
    this.host.dataset.tier = t;
    this.svg.querySelectorAll('image').forEach((im) => im.setAttribute('href', this._href(im._entry)));
  }

  /** Pre-decode every image of the current tier so boil frames / expression swaps never flash. */
  preload() {
    const urls = new Set();
    const add = (e) => urls.add(this._href(e));
    this._bodySet().forEach(add); if (this.rig.body.outer_strokes) add(this.rig.body.outer_strokes); add(this.rig.body.eye_whites);
    if (this._ewEntries) { add(this._ewEntries.l); add(this._ewEntries.r); }
    Object.values(this.rig.fringe || {}).forEach(add);
    for (const ex of Object.values(this.rig.expressions)) Object.values(ex.parts).forEach(add);
    return Promise.all([...urls].map((u) => { const i = new this.win.Image(); i.src = u; return i.decode().catch(() => null); }));
  }

  _entry(expr, partKey) {
    const key = `${expr}__${partKey}`;
    let e = this._els.get(key);
    if (e) return e;
    const part = this.rig.expressions[expr].parts[partKey];
    const isEye = partKey.startsWith('eye');
    const kind = isEye ? (part.open ? 'pupil' : 'lid') : partKey.startsWith('brow') ? 'brow' : 'mouth';
    const el = this._img(part);
    el.dataset.part = key;
    el.dataset.slot = partKey;
    el.dataset.kind = kind;
    el.style.display = 'none';
    const pupilGroup = this._pupilGroups.both || (partKey === 'eye_left' ? this._pupilGroups.l : this._pupilGroups.r);
    ({ pupil: pupilGroup, lid: this.gLids, brow: this.gBrows, mouth: this.gMouth })[kind].appendChild(el);
    e = { key, expr, partKey, kind, part, el, st: part.stats, local: '', opacity: 1, shown: false };
    this._els.set(key, e);
    return e;
  }

  _show(e, local = '', opacity = 1) {
    e.local = local; e.opacity = opacity;
    if (!e.shown) { e.el.style.display = ''; e.shown = true; }
  }

  _hide(e) {
    if (e.shown) { e.el.style.display = 'none'; e.shown = false; }
    e.local = ''; e.opacity = 1;
  }

  /* ----------------------------------------------------------- reduced motion */

  _applyReducedMotionSource() {
    this._mq = this.win.matchMedia ? this.win.matchMedia('(prefers-reduced-motion: reduce)') : null;
    if (this._mq) this._on(this._mq, 'change', () => this._onMotionPrefChange());
    this._onMotionPrefChange(true);
  }

  get reduced() {
    if (this.opts.reducedMotion === 'reduce') return true;
    if (this.opts.reducedMotion === 'no-preference') return false;
    return !!(this._mq && this._mq.matches);
  }

  setReducedMotion(mode) { this.opts.reducedMotion = mode; this._onMotionPrefChange(); }

  _onMotionPrefChange(initial = false) {
    const r = this.reduced;
    this.host.classList.toggle('bisco--reduced', r);
    if (initial) return;
    if (r) {
      for (const k of ['boilFrame', 'blink2', 'brow']) this._clearTimer(k);
      this._finishTweens();
      this._showBody(0);
      this._gaze.tx = this._gaze.ty = this._gaze.x = this._gaze.y = 0;
      this._brow.ty = this._brow.y = this._brow.tl = this._brow.l = this._brow.tr = this._brow.r = 0;
      this.elTilt.style.transform = '';
      this._head.x = this._head.y = 0; this.elHead.style.transform = '';
      if (this._clickAnim) { this._clickAnim.cancel(); this._clickAnim = null; }
      this._render();
    }
    this._updateClasses();
    this._scheduleAll();
  }

  /* ------------------------------------------------------------- public API */

  setState(name, { instant = false } = {}) {
    if (!STATES.includes(name)) throw new Error(`Unknown Bisco state: ${name}`);
    this.requested = name;
    this._clearTimer('clickReturn');
    this._goto(name, instant);
  }

  setLineBoil(on) { this.opts.lineBoil = !!on; if (!on) { this._clearTimer('boil'); this._clearTimer('boilFrame'); this._showBody(0); } this._scheduleBoil(); this._updateClasses(); }

  setTracking(on) {
    this.opts.tracking = !!on;
    if (!on) { this._pointer = null; this._setGazeTarget(0, 0); }
    this._updateClasses();
  }

  setFloat(on) { this.opts.float = !!on; this._updateClasses(); }

  setAutoBlink(on) { this.opts.autoBlink = !!on; this._scheduleBlink(); }

  /** Gaze in normalised units (-1..1); clamped to the real white of the current eyes. */
  lookAt(nx, ny) { this._setGazeTarget(nx * GAZE_MAX, ny * GAZE_MAX); }

  /** Click / tap reaction: small squash, controlled stretch, brief facial reaction, smooth return. */
  poke() {
    if (this._destroyed) return;
    this.stats.clicks++;
    const reaction = this.requested === 'happy' ? 'surprise' : 'happy';
    if (!this.reduced && this.elReact.animate) {
      if (this._clickAnim) this._clickAnim.cancel();
      this._clickAnim = this.elReact.animate([
        { transform: 'scale(1, 1)' },
        { transform: 'scale(1.045, 0.948)', offset: 0.22, easing: 'cubic-bezier(.2,.7,.3,1)' },
        { transform: 'scale(0.982, 1.024)', offset: 0.52, easing: 'cubic-bezier(.4,0,.3,1)' },
        { transform: 'scale(1.006, 0.995)', offset: 0.78 },
        { transform: 'scale(1, 1)' },
      ], { duration: 460 / this.opts.timeScale, easing: 'linear' });
      this._clickAnim.onfinish = () => { this._clickAnim = null; };
    }
    this._goto(reaction, false);
    this._later('clickReturn', 750, () => this._goto(this.requested, false));
    this.host.dispatchEvent(new this.win.CustomEvent('bisco:poke', { detail: { reaction } }));
  }

  blink() { this._blink(); }

  boilEpisode() { this._boilEpisode(); }

  destroy() {
    if (this._destroyed) return;
    this._destroyed = true;
    for (const id of this._timers.values()) this.win.clearTimeout(id);
    this._timers.clear();
    if (this._raf) this.win.cancelAnimationFrame(this._raf);
    if (this._pointerRaf) this.win.cancelAnimationFrame(this._pointerRaf);
    this._pointerRaf = 0; this._pointerPending = false;
    this._raf = 0;
    this._tweens.length = 0;
    if (this._clickAnim) { this._clickAnim.cancel(); this._clickAnim = null; }
    for (const [t, ev, fn, o] of this._listeners) t.removeEventListener(ev, fn, o);
    this._listeners.length = 0;
    for (const o of this._observers) o.disconnect();
    this._observers.length = 0;
    this._els.clear();
    this.elFloat.remove();
    this.host.classList.remove('bisco', 'bisco--reduced', 'bisco--float', 'bisco--paused');
    if (this.opts.interactive) {
      this.host.removeAttribute('role');
      this.host.removeAttribute('aria-label');
    }
  }

  debug() {
    const visible = [...this.svg.querySelectorAll('.b-face image')]
      .filter((im) => im.style.display !== 'none')
      .map((im) => ({ part: im.dataset.part, kind: im.dataset.kind, slot: im.dataset.slot, opacity: Number(im.getAttribute('opacity') ?? 1), transform: im.getAttribute('transform') || '' }));
    return {
      state: this.state, requested: this.requested, reduced: this.reduced, tier: this._tier, base: this.opts.base,
      bodyHref: this._bodyImgs[this._bodyIndex].getAttribute('href'),
      fringes: Object.fromEntries(Object.entries(this._fringes).map(([k, im]) => [k, im.style.display === 'none' ? 0 : Number(im.getAttribute('opacity'))])),
      body: this._bodyIndex,
      bodyVisible: this._bodyImgs.filter((i) => i.style.visibility !== 'hidden').length,
      visible, timers: [...this._timers.keys()], raf: !!this._raf, tweens: this._tweens.length,
      listeners: this._listeners.length, observers: this._observers.length,
      nextBoilMs: this._nextBoilMs ?? null, gaze: { x: this._gaze.x, y: this._gaze.y }, brow: { ...this._brow },
      lid: { ...this._lid }, head: { ...this._head }, headTransform: this.elHead.style.transform,
      overlap: this._ovK,
      eyeWhitesVisible: (this._ewCombined.style.display !== 'none' ? 2 : 0) + Object.entries(this._ewImgs).filter(([k, im]) => k !== 'both' && im.style.display !== 'none').length,
      bodyOpacity: this._bodyImgs.map((i) => (i.style.visibility === 'hidden' ? 0 : Number(i.getAttribute('opacity') ?? 1))),
      stats: { ...this.stats }, destroyed: this._destroyed, docVisible: this._docVisible, inView: this._visible,
    };
  }

  /* ------------------------------------------------------------ face states */

  _setFaceInstant(name) {
    for (const e of this._els.values()) this._hide(e);
    for (const slot of SLOTS) { const e = this._entry(name, slot); this._show(e); this._slots[slot] = e; }
    this.state = name;
    this._lid.l = this._lid.r = this._lidTargetFor(name);
    this._afterStateChange();
    this._render();
  }

  _goto(name, instant) {
    if (this._destroyed) return;
    this._finishTweens();
    if (name === this.state) { this._afterStateChange(); return; }
    const from = this.state;
    this.state = name;
    this.stats.transitions++;
    if (instant || this.reduced) {
      this._setFaceInstant(name);
    } else {
      const fromEx = this.rig.expressions[from];
      const toEx = this.rig.expressions[name];
      this._morph('brow_left', name, 230);
      this._morph('brow_right', name, 230, 25);
      this._morph('mouth', name, 260, 40);
      const full = this._fullBlinkOK();
      const lidFrom = this._lid.l; const lidTo = this._lidTargetFor(name);
      for (const side of ['eye_left', 'eye_right']) {
        const a = fromEx.parts[side].open; const b = toEx.parts[side].open;
        if (full && lidTo === 1 && a) this._closeEyeFull(side, name, 100);           // whole eye closes
        else if (full && lidFrom >= 0.999 && b) this._openEyeFull(side, name, 140); // whole eye opens
        else if (a && b) this._morph(side, name, 260, 0, { translateOnly: true });
        else if (a && !b) this._closeEye(side, name, 95, 120);
        else if (!a && b) this._openEye(side, name, 95, 130);
        else this._morph(side, name, 200);
      }
      if (lidTo !== lidFrom) this._animLid(lidTo, lidTo ? 100 : 140, lidTo ? 0 : OPEN_LID_FADE, lidTo ? easeIn : easeOut);
      this._kick();
    }
    // clarification: one small expressive reaction of the tangle when the state is entered
    if (name === 'clarification' && from !== 'clarification' && this.opts.base === 'v3') {
      this._later('boilEnter', 260, () => this._boilEpisode());
    }
    this._afterStateChange();
    this.host.dispatchEvent(new this.win.CustomEvent('bisco:state', { detail: { from, to: name } }));
  }

  _afterStateChange() {
    this._updateAria();
    this._updateClasses();
    this.host.dataset.state = this.state;
    // re-clamp gaze (target AND current position) to the white of the new eyes
    this._setGazeTarget(this._gaze.x, this._gaze.y);
    this._gaze.x = this._gaze.tx; this._gaze.y = this._gaze.ty;
    this._setGazeTarget(this._gaze.x, this._gaze.y);
    this._scheduleAll();
  }

  _updateAria() {
    if (!this.opts.interactive) return;
    this.host.setAttribute('aria-label', `${this.opts.label} — ${STATE_LABELS[this.state] || this.state}. Clique para interagir.`);
  }

  _updateClasses() {
    const h = this.host;
    h.classList.toggle('bisco--float', this.opts.float && !this.reduced);
    h.classList.toggle('bisco--paused', !this._visible || !this._docVisible);
    for (const s of STATES) h.classList.toggle(`bisco--${s}`, s === this.state);
  }

  /** Transform mapping shape A onto shape B (partial by u). */
  static _pose(A, B, u, mode) {
    const cx = lerp(A.cx, B.cx, u); const cy = lerp(A.cy, B.cy, u);
    let rot = 0; let sx = 1; let sy = 1;
    if (mode === 'brow') {
      let d = B.angle - A.angle; if (d > 90) d -= 180; if (d < -90) d += 180;
      rot = clamp(d, -45, 45) * u;
      const s = clamp(B.len / A.len, 0.6, 1.6); sx = sy = lerp(1, s, u);
    } else if (mode === 'mouth' || mode === 'lid') {
      sx = lerp(1, clamp(B.bbox[2] / A.bbox[2], 0.25, 4), u);
      sy = lerp(1, clamp(B.bbox[3] / A.bbox[3], 0.25, 4), u);
    }
    return { cx, cy, rot, sx, sy };
  }

  static _tf(p, ox, oy) {
    return `translate(${f2(p.cx)} ${f2(p.cy)}) rotate(${f2(p.rot)}) scale(${f2(p.sx)} ${f2(p.sy)}) translate(${f2(-ox)} ${f2(-oy)})`;
  }

  _morph(slot, toExpr, dur, delay = 0, { translateOnly = false } = {}) {
    const A = this._slots[slot];
    const B = this._entry(toExpr, slot);
    if (A === B) return;
    const mode = translateOnly ? 'pupil' : A.kind === 'brow' ? 'brow' : A.kind;
    const a = A.st; const b = B.st;
    // B expressed relative to A: inverse pose so that at u=0 B sits exactly on A.
    const inv = (u) => {
      const p = BiscoCharacter._pose(a, b, u, mode);
      const full = BiscoCharacter._pose(a, b, 1, mode);
      return { cx: p.cx, cy: p.cy, rot: p.rot - full.rot, sx: p.sx / full.sx, sy: p.sy / full.sy };
    };
    this._show(A, '', 1);
    this._show(B, BiscoCharacter._tf(inv(0), b.cx, b.cy), 0);
    this._slots[slot] = B;
    // pupils are the same sprite translated → swap at the very end; others fade while co-located
    // Brows/mouths/lids: the outgoing shape carries itself onto the incoming one and fades out
    // (u 0.34–0.54) BEFORE the incoming shape fades in (u 0.50–0.70) — nearly sequential, so two
    // different mouths/brows are never both clearly visible (max overlap ≈ 15 % / 6 % opacity).
    const outW = mode === 'pupil' ? [0.9, 1.0] : [0.34, 0.54];
    const inW = mode === 'pupil' ? [0.9, 1.0] : [0.5, 0.7];
    this._tween(dur, delay, easeInOut, (u) => {
      A.local = BiscoCharacter._tf(BiscoCharacter._pose(a, b, u, mode), a.cx, a.cy);
      B.local = BiscoCharacter._tf(inv(u), b.cx, b.cy);
      A.opacity = 1 - smoothstep(outW[0], outW[1], u); B.opacity = smoothstep(inW[0], inW[1], u);
    }, () => { this._hide(A); this._show(B, '', 1); });
  }

  _closeEye(slot, toExpr, tClose, tLid, holdThen) {
    const A = this._slots[slot];
    const B = this._entry(toExpr, slot);
    const a = A.st; const b = B.st;
    this._slots[slot] = B;
    this._show(A, '', 1);
    this._hide(B);
    // pupil squashes vertically about its centre (lid coming down), then the closed-lid arc appears
    this._tween(tClose, 0, easeIn, (u) => {
      A.local = BiscoCharacter._tf({ cx: a.cx, cy: a.cy + 6 * u, rot: 0, sx: 1 - 0.06 * u, sy: 1 - 0.9 * u }, a.cx, a.cy);
    }, () => {
      this._hide(A);
      this._show(B, BiscoCharacter._tf({ cx: b.cx, cy: b.cy, rot: 0, sx: 0.9, sy: 0.45 }, b.cx, b.cy), 0.4);
    });
    this._tween(tLid, tClose, easeOut, (u) => {
      B.local = BiscoCharacter._tf({ cx: b.cx, cy: b.cy, rot: 0, sx: lerp(0.9, 1, u), sy: lerp(0.45, 1, u) }, b.cx, b.cy);
      B.opacity = lerp(0.4, 1, Math.min(1, u * 2));
    }, () => { this._show(B, '', 1); if (holdThen) holdThen(); });
  }

  _openEye(slot, toExpr, tLid, tOpen) {
    const A = this._slots[slot];
    const B = this._entry(toExpr, slot);
    const a = A.st; const b = B.st;
    this._slots[slot] = B;
    this._show(A, '', 1);
    this._hide(B);
    this._tween(tLid, 0, easeIn, (u) => {
      A.local = BiscoCharacter._tf({ cx: a.cx, cy: a.cy, rot: 0, sx: lerp(1, 0.92, u), sy: lerp(1, 0.4, u) }, a.cx, a.cy);
      A.opacity = 1 - 0.6 * u;
    }, () => {
      this._hide(A);
      this._show(B, BiscoCharacter._tf({ cx: b.cx, cy: b.cy + 6, rot: 0, sx: 0.94, sy: 0.1 }, b.cx, b.cy), 1);
    });
    this._tween(tOpen, tLid, easeOut, (u) => {
      B.local = BiscoCharacter._tf({ cx: b.cx, cy: b.cy + 6 * (1 - u), rot: 0, sx: lerp(0.94, 1, u), sy: lerp(0.1, 1, u) }, b.cx, b.cy);
    }, () => this._show(B, '', 1));
  }

  _animLid(to, dur, delay = 0, ease = easeInOut) {
    const l0 = this._lid.l; const r0 = this._lid.r;
    this._tween(dur, delay, ease, (u) => { this._lid.l = lerp(l0, to, u); this._lid.r = lerp(r0, to, u); }, () => { this._lid.l = this._lid.r = to; });
  }

  /** Pupil stays (clipped by the collapsing white), then the closed-lid curve replaces it. */
  _closeEyeFull(slot, toExpr, dur) {
    const A = this._slots[slot];
    const B = this._entry(toExpr, slot);
    this._slots[slot] = B;
    this._show(A, '', 1);
    this._hide(B);
    this._tween(dur, 0, (u) => u, () => {}, () => { this._hide(A); this._show(B, '', 0); });
    this._tween(60, dur, easeOut, (u) => { if (B.shown) B.opacity = u; }, () => { if (this._slots[slot] === B) this._show(B, '', 1); });
  }

  /** Lid curve fades while the white re-opens with the new pupil already inside it. */
  _openEyeFull(slot, toExpr, dur) {
    const A = this._slots[slot];
    const B = this._entry(toExpr, slot);
    this._slots[slot] = B;
    this._show(A, '', 1);
    this._hide(B);
    // strictly sequential: lid curve fades out (white still collapsed), THEN the pupil comes back
    this._tween(OPEN_LID_FADE, 0, easeOut, (u) => { A.opacity = 1 - u; }, () => { this._hide(A); this._show(B, '', 1); });
  }

  /* ----------------------------------------------------------------- blink */

  _blink() {
    if (this._destroyed || this.reduced) return;
    const ex = this.rig.expressions[this.state];
    if (!ex.eyesOpen || this._tweens.length) return;
    this.stats.blinks++;
    const current = this.state;
    const tc = 70; const tl = 55; const hold = 45; const to = 120;
    this._brow.ty = 3; // brows dip slightly with the lids
    if (this._fullBlinkOK()) {
      // whole eye closes: white collapses onto the lid line, pupil clipped with it, lid curve shown
      const tClose = 80; const tHold = 55; const tOpen = 130;
      for (const slot of ['eye_left', 'eye_right']) this._closeEyeFull(slot, 'blink', tClose);
      this._animLid(1, tClose, 0, easeIn);
      this._tweenWait(tClose + 60 + tHold, () => {
        if (this.state !== current) return;
        for (const slot of ['eye_left', 'eye_right']) this._openEyeFull(slot, current, tOpen);
        this._animLid(0, tOpen, OPEN_LID_FADE, easeOut);
        this._brow.ty = 0;
      });
      this._kick();
      return;
    }
    for (const slot of ['eye_left', 'eye_right']) {
      // close onto the BLINK lids but keep the current brows and mouth
      this._closeEye(slot, 'blink', tc, tl, () => {
        this._tweenWait(hold, () => {
          if (this.state !== current) return;
          this._openEye(slot, current, 50, to);
          this._brow.ty = 0;
        });
      });
    }
    this._kick();
  }

  /* ------------------------------------------------------------- line boil */

  _showBody(i, fadeMs = 0) {
    if (this._bodyIndex === i) return;
    const prev = this._bodyImgs[this._bodyIndex]; const next = this._bodyImgs[i];
    this._bodyIndex = i;
    this.host.dataset.body = String(i);
    if (!fadeMs || this.reduced) {
      for (const im of this._bodyImgs) if (im !== next) { im.style.visibility = 'hidden'; im.removeAttribute('opacity'); }
      next.style.visibility = ''; next.removeAttribute('opacity');
      return;
    }
    // soft swap between REGISTERED frames: incoming fades in on top, then the previous one is hidden
    for (const im of this._bodyImgs) if (im !== next && im !== prev) { im.style.visibility = 'hidden'; im.removeAttribute('opacity'); }
    this.gBase.appendChild(next);
    next.setAttribute('opacity', '0'); next.style.visibility = '';
    this._tween(fadeMs, 0, easeInOut, (u) => next.setAttribute('opacity', String(f2(u))), () => {
      next.removeAttribute('opacity');
      if (this._bodyImgs[this._bodyIndex] === next) { prev.style.visibility = 'hidden'; prev.removeAttribute('opacity'); }
    });
    this._kick();
  }

  _boilEpisode() {
    if (this._destroyed || this.reduced || !this.opts.lineBoil) return;
    if (this._timers.has('boilFrame')) return; // never two episodes at once
    this.stats.boilEpisodes++;
    const v3 = this.opts.base === 'v3';
    const fr = BOIL_FRAMES_V3[this.state] || BOIL_FRAMES_V3.default;
    const frames = v3 ? fr[0] + Math.floor(this.rand() * (fr[1] - fr[0] + 1)) : 2 + Math.floor(this.rand() * 3); // v3 per state · old: 2–4
    let last = 0; const seq = [];
    for (let i = 0; i < frames; i++) {
      let v; do { v = 1 + Math.floor(this.rand() * 3); } while (v === last);
      seq.push(v); last = v;
    }
    this.host.dispatchEvent(new this.win.CustomEvent('bisco:boil', { detail: { frames: seq } }));
    const step = (k) => {
      // stop immediately if motion got reduced / boil disabled mid-episode
      const fade = v3 && this.opts.boilSource !== 'raw' ? 90 : 0;
      if (k >= seq.length || this.reduced || !this.opts.lineBoil) { this._showBody(0, this.reduced ? 0 : fade); this._scheduleBoil(); return; }
      this._showBody(seq[k], fade);
      this.stats.boilFrames++;
      this._later('boilFrame', v3 ? fade + 110 + this.rand() * 60 : 75 + this.rand() * 40, () => step(k + 1));
    };
    step(0);
  }

  _scheduleBoil() {
    const table = this.opts.base === 'v3' ? BOIL_INTERVAL_V3 : BOIL_INTERVAL;
    const key = `${this.opts.base}:${this.state}`;
    // Repeated scheduling (visibility changes, re-renders) must not keep postponing the episode:
    // a pending timer for the same cadence is kept; a new state (new cadence) reschedules.
    if (this._timers.has('boil') && this._boilKey === key && !this._destroyed && !this.reduced && this.opts.lineBoil && this._active()) return;
    this._clearTimer('boil');
    if (this._destroyed || this.reduced || !this.opts.lineBoil || !this._active()) return;
    if (this._timers.has('boilFrame')) return; // episode running; it reschedules itself
    this._boilKey = key;
    const [a, b] = table[this.state] || table.default;
    const s = (a + this.rand() * (b - a)) * this.opts.boilFactor;
    this._nextBoilMs = s * 1000;
    this._later('boil', s * 1000, () => this._boilEpisode());
  }

  /* ------------------------------------------------------- idle behaviours */

  _active() { return this._visible && this._docVisible && !this._destroyed; }

  _scheduleAll() {
    if (this._destroyed) return;
    if (!this._active()) {
      for (const k of ['boil', 'blink', 'blink2', 'saccade', 'tilt', 'brow']) this._clearTimer(k);
      // pending "return to rest" timers were cancelled: restore rest targets so nothing stays stuck
      this._brow.ty = 0; this._brow.tl = 0; this._brow.tr = 0;
      this._kick();
      this._updateClasses();
      return;
    }
    this._scheduleBoil();
    this._scheduleBlink();
    this._scheduleSaccade();
    this._scheduleTilt();
  }

  _scheduleBlink() {
    this._clearTimer('blink');
    if (this.reduced || !this.opts.autoBlink || !this._active()) return;
    const ms = 2400 + this.rand() * 3800;
    this._later('blink', ms, () => {
      this._blink();
      if (this.rand() < 0.14) this._later('blink2', 330, () => this._blink()); // occasional double blink
      this._scheduleBlink();
    });
  }

  _scheduleSaccade() {
    // keep a pending "attention shift" scheduled for this same state (repeated scheduling must not delay it)
    if (this._saccadeEnteringFor === this.state && this._timers.has('saccade')) return;
    this._clearTimer('saccade');
    if (this.reduced || !this.opts.saccades || !this._active()) return;
    const prog = GAZE_PROGRAM[this.state] || GAZE_PROGRAM.neutral;
    this._gazeTau = prog.tau;
    // a new expression shifts attention right away; afterwards the state's own rhythm
    const entering = this._progState !== this.state;
    this._progState = this.state;
    const ms = entering ? R(this.rand, 120, 240) : R(this.rand, prog.every[0], prog.every[1]) * 1000;
    this._saccadeEnteringFor = entering ? this.state : null;
    this._later('saccade', ms, () => {
      this._saccadeEnteringFor = null;
      const tracking = this.opts.tracking && this._pointer && this.win.performance.now() - this._lastPointerT < 2500;
      if (!tracking && this.rig.expressions[this.state].eyesOpen) {
        this.stats.saccades++;
        const [x, y] = prog.pick(this.rand, this._gazeStep++);
        this._setGazeTarget(x, y);
        if (prog.brows && this.rand() < 0.45) { // doubt: one brow lifts briefly with the glance
          if (this.rand() < 0.5) this._brow.tl = -3.5; else this._brow.tr = -3.5;
          this._later('brow', 420, () => { this._brow.tl = this._brow.tr = 0; this._kick(); });
        } else if (this.state === 'neutral' && Math.hypot(x, y) > 2.5 && this.rand() < 0.3) this._curious();
      }
      this._scheduleSaccade();
    });
  }

  _scheduleTilt() {
    this._clearTimer('tilt');
    if (this.reduced || !this._active()) { this.elTilt.style.transform = ''; return; }
    if (this.state !== 'thinking') { this.elTilt.style.transform = ''; if (this.state !== 'clarification') this._brow.tl = this._brow.tr = 0; return; }
    const ms = 1400 + this.rand() * 1800;
    const deg = -2.6 + this.rand() * 4.2; // lean slightly, mostly to one side
    this.elTilt.style.transform = `rotate(${deg.toFixed(2)}deg)`;
    // one brow up alternately while pondering (few px)
    if (this.rand() < 0.5) { this._brow.tl = -4; this._brow.tr = 0; } else { this._brow.tl = 0; this._brow.tr = -4; }
    this._kick();
    this._later('tilt', ms, () => this._scheduleTilt());
  }

  _curious() {
    if (this.reduced) return;
    this._brow.ty = -4.5;
    this._kick();
    this._later('brow', 650, () => { this._brow.ty = 0; this._kick(); });
  }

  /* ------------------------------------------------------------------ gaze */

  _clearance(expr, ang) {
    const c = this.rig.expressions[expr]?.gazeClearance;
    if (!c) return 0;
    const n = c.length; let t = ((ang / (2 * Math.PI)) * n) % n; if (t < 0) t += n;
    const i = Math.floor(t);
    // conservative: never exceed either neighbouring measured direction
    return Math.min(c[i], c[(i + 1) % n]);
  }

  _setGazeTarget(x, y) {
    const r = Math.hypot(x, y);
    if (r < 1e-6) { this._gaze.tx = 0; this._gaze.ty = 0; this._kick(); return; }
    const ang = Math.atan2(y, x);
    // clamp by the real white region of the eyes now visible (and the one we are leaving)
    let lim = Math.min(GAZE_MAX, this._clearance(this.state, ang));
    for (const e of Object.values(this._slots)) if (e.kind === 'pupil' && e.expr !== this.state) lim = Math.min(lim, this._clearance(e.expr, ang));
    const k = Math.min(r, lim) / r;
    this._gaze.tx = x * k; this._gaze.ty = y * k;
    this._kick();
  }

  _onPointer(ev) {
    if (!this.opts.tracking || this.reduced || this._destroyed) return;
    this._pointer = { x: ev.clientX, y: ev.clientY };
    this._lastPointerT = this.win.performance.now();
    if (this._pointerPending) return;
    this._pointerPending = true;
    this._pointerRaf = this.win.requestAnimationFrame(() => {
      this._pointerRaf = 0;
      this._pointerPending = false;
      if (this._destroyed || !this._pointer) return;
      const rc = this.host.getBoundingClientRect();
      const ex = rc.left + rc.width * (606 / 1024); const ey = rc.top + rc.height * (483 / 1024);
      const dx = this._pointer.x - ex; const dy = this._pointer.y - ey;
      const d = Math.hypot(dx, dy) || 1;
      const mag = GAZE_MAX * (1 - Math.exp(-d / (rc.width * 0.9)));
      this._setGazeTarget((dx / d) * mag, (dy / d) * mag);
      const near = d < rc.width * 0.9;
      if (near && !this._near) this._curious();
      this._near = near;
    });
  }

  /* --------------------------------------------------------------- engine */

  _tween(dur, delay, ease, update, done) {
    const ts = this.opts.timeScale;
    this._tweens.push({ t0: this.win.performance.now() + delay / ts, dur: Math.max(1, dur / ts), ease, update, done, started: false });
  }

  _tweenWait(ms, done) { this._tween(ms, 0, (u) => u, () => {}, done); this._kick(); }

  _finishTweens() {
    // complete chained tweens deterministically (done() may enqueue more)
    let guard = 0;
    while (this._tweens.length && guard++ < 200) {
      this._tweens.sort((p, q) => p.t0 - q.t0);
      const t = this._tweens.shift();
      t.update(1);
      if (t.done) t.done();
    }
    // an interrupted chain (e.g. a blink cut short) may leave a superseded part on screen:
    // normalise to exactly the slot's current part, at rest, and the lids to their target
    for (const e of this._els.values()) {
      if (!e.shown) continue;
      if (this._slots[e.partKey] !== e) this._hide(e);
      else { e.local = ''; e.opacity = 1; }
    }
    this._lid.l = this._lid.r = this._lidTargetFor(this.state);
    this._render();
  }

  _kick() {
    if (this._raf || this._destroyed) return;
    this._lastT = this.win.performance.now();
    this._raf = this.win.requestAnimationFrame((t) => this._frame(t));
  }

  _frame(now) {
    this._raf = 0;
    if (this._destroyed) return;
    const dt = Math.min(64, Math.max(0, now - (this._lastT || now))) * this.opts.timeScale;
    this._lastT = now;
    // tweens
    const keep = [];
    const finished = [];
    for (const t of this._tweens) {
      if (now < t.t0) { keep.push(t); continue; }
      const u = clamp((now - t.t0) / t.dur, 0, 1);
      t.update(t.ease(u));
      if (u >= 1) finished.push(t); else keep.push(t);
    }
    this._tweens = keep;
    for (const t of finished) if (t.done) t.done();
    // springs (exponential approach, frame-rate independent)
    let moving = false;
    const appr = (o, k, tk, tau) => {
      const d = o[tk] - o[k];
      if (Math.abs(d) < 0.02) { o[k] = o[tk]; return; }
      o[k] += d * (1 - Math.exp(-dt / tau)); moving = true;
    };
    if (this.reduced) { this._gaze.x = this._gaze.tx = 0; this._gaze.y = this._gaze.ty = 0; }
    appr(this._gaze, 'x', 'tx', this._gazeTau || 55); appr(this._gaze, 'y', 'ty', this._gazeTau || 55);
    // the head follows the eyes with a lag (attention shift), with a much smaller amplitude
    const hf = this.opts.headFollow && !this.reduced;
    const htx = hf ? this._gaze.x : 0; const hty = hf ? this._gaze.y : 0;
    for (const [k, t] of [['x', htx], ['y', hty]]) {
      const d = t - this._head[k];
      if (Math.abs(d) < 0.01) this._head[k] = t; else { this._head[k] += d * (1 - Math.exp(-dt / 260)); moving = true; }
    }
    appr(this._brow, 'y', 'ty', 110); appr(this._brow, 'l', 'tl', 160); appr(this._brow, 'r', 'tr', 160);
    this._render();
    if (this._tweens.length || moving) this._kick();
  }

  /** Overlap transforms for amount k (0..1): left eye advances/grows, right eye foreshortens. */
  _ovTransforms(k) {
    if (!this._ovGeo || k <= 0.001) return { l: '', r: '', rInv: '' };
    const { lcx, lcy, rx, rcy } = this._ovGeo;
    const ls = [1 + 0.05 * k, 1 + 0.03 * k]; const rs = [1 - 0.06 * k, 1 - 0.02 * k];
    return {
      l: `translate(${f2(lcx + 7 * k)} ${f2(lcy)}) scale(${f2(ls[0])} ${f2(ls[1])}) translate(${f2(-lcx)} ${f2(-lcy)})`,
      r: `translate(${f2(rx)} ${f2(rcy)}) scale(${f2(rs[0])} ${f2(rs[1])}) translate(${f2(-rx)} ${f2(-rcy)})`,
      rInv: `translate(${f2(rx)} ${f2(rcy)}) scale(${f2(1 / rs[0])} ${f2(1 / rs[1])}) translate(${f2(-rx)} ${f2(-rcy)})`,
    };
  }

  _render() {
    const g = this._gaze; const b = this._brow;
    // ---- eye overlap: looking far to the viewer's right, the LEFT eye advances over the right one ----
    // (2D perspective cue only; gentle onset, exact approved geometry for centre and small glances)
    const ovOK = this._ewEntries && this.opts.base !== 'original' && !this.reduced && this.opts.overlap !== false;
    const k = ovOK ? smoothstep(OVERLAP_START, OVERLAP_FULL, g.x) : 0;
    this._ovK = k;
    const ov = this._ovTransforms(k);
    // eye whites (+ their pupil masks) collapse vertically onto the lid line when the eye closes
    const closing = this._ewEntries && (this._lid.l > 0.001 || this._lid.r > 0.001 || k > 0.001);
    if (this._ewEntries) this._ewCombined.style.display = closing ? 'none' : '';
    const lidTf = (side) => {
      const lid = clamp(this._lid[side], 0, 1); const [px, py] = this._lidPivot[side];
      return lid > 0.001 ? `translate(${f2(px)} ${f2(py)}) scale(1 ${f2(1 - lid)}) translate(${f2(-px)} ${f2(-py)})` : '';
    };
    const setTf = (el, t) => { if (!el) return; t = (t || '').trim(); if (t) el.setAttribute('transform', t); else el.removeAttribute('transform'); };
    for (const side of ['l', 'r']) {
      const im = this._ewImgs[side]; if (!im) continue;
      const mi = this._ewMaskImgs[side];
      const grp = this._pupilGroups[side];
      if (!closing) {
        im.style.display = 'none'; im.removeAttribute('transform'); im.removeAttribute('filter');
        if (mi) { mi.style.display = ''; mi.removeAttribute('transform'); }
        setTf(grp, '');
        continue;
      }
      const lid = clamp(this._lid[side], 0, 1);
      setTf(grp, ov[side]); // pupils (and, through user space, their mask) travel with their eye
      if (lid >= 0.999) { im.style.display = 'none'; if (mi) mi.style.display = 'none'; continue; }
      im.style.display = ''; if (mi) mi.style.display = '';
      setTf(im, `${ov[side]} ${lidTf(side)}`);
      setTf(mi, lidTf(side)); // mask lives in the (already transformed) pupil-group space
      if (side === 'l') {
        if (k > 0.01) { im.setAttribute('filter', `url(#${this._ovShadowId})`); this._ovShadow.setAttribute('flood-opacity', String(f2(0.3 * k))); }
        else im.removeAttribute('filter');
      }
    }
    if (this._ovMaskL) {
      // the left white, expressed in the right pupil group's space: ovR⁻¹ · ovL · lidL
      const lOpen = clamp(this._lid.l, 0, 1) < 0.999;
      this._ovMaskL.style.display = lOpen ? '' : 'none';
      setTf(this._ovMaskL, `${ov.rInv} ${ov.l} ${lidTf('l')}`);
    }
    if (this.elHead) {
      const hx = this._head.x; const hy = this._head.y;
      const t = Math.abs(hx) + Math.abs(hy) > 0.02 ? `translate(${f2(hx * 0.06)}%, ${f2(hy * 0.05)}%) rotate(${f2(hx * 0.075)}deg)` : '';
      if (this.elHead.style.transform !== t) this.elHead.style.transform = t;
    }
    let anyFringe = false;
    for (const [name, im] of Object.entries(this._fringes || {})) {
      const o = this._fringeOpacity(name);
      const mi = this._fringeMasks[name];
      if (o <= 0.001) {
        if (im.style.display !== 'none') im.style.display = 'none';
        if (mi && mi.style.display !== 'none') mi.style.display = 'none';
        continue;
      }
      anyFringe = true;
      const ov = o >= 0.999 ? '1' : String(f2(o));
      im.style.display = ''; im.setAttribute('opacity', ov);
      if (mi) { mi.style.display = ''; mi.setAttribute('opacity', ov); }
    }
    // mask only attached while needed: at rest the base is drawn untouched (exact)
    if (this.gBase) {
      const want = anyFringe && Object.keys(this._fringeMasks).length ? `url(#${this._fringeMaskId})` : null;
      if (want !== this.gBase.getAttribute('mask')) { if (want) this.gBase.setAttribute('mask', want); else this.gBase.removeAttribute('mask'); }
    }
    for (const e of this._els.values()) {
      if (!e.shown) continue;
      let off = '';
      if (e.kind === 'pupil') {
        // in the approved art the left pupil sits ~4 px from the seam: once the eyes separate (overlap),
        // it may not cross into the right white — its rightward travel is eased down to ≈3 px with k
        const gx = e.partKey === 'eye_left' && g.x > LEFT_PUPIL_MAX_X ? g.x - k * (g.x - LEFT_PUPIL_MAX_X) : g.x;
        off = `translate(${f2(gx)} ${f2(g.y)}) `;
      }
      else if (e.kind === 'lid') off = `${e.partKey === 'eye_left' ? ov.l : ov.r} translate(${f2(g.x * 0.35)} ${f2(g.y * 0.35)}) `;
      else if (e.kind === 'brow') {
        const side = e.partKey === 'brow_left' ? b.l : b.r;
        const ovx = e.partKey === 'brow_left' ? 3 * k : -1 * k;
        off = `translate(${f2(g.x * 0.15 + ovx)} ${f2(b.y + side + g.y * 0.2)}) `;
      }
      const tf = (off + e.local).trim();
      if (tf) e.el.setAttribute('transform', tf); else e.el.removeAttribute('transform');
      if (e.opacity >= 0.999) e.el.removeAttribute('opacity'); else e.el.setAttribute('opacity', f2(e.opacity));
    }
  }

  /* ------------------------------------------------------- timers/observers */

  _later(name, ms, fn) {
    this._clearTimer(name);
    const id = this.win.setTimeout(() => { this._timers.delete(name); if (!this._destroyed) fn(); }, ms / this.opts.timeScale);
    this._timers.set(name, id);
  }

  _clearTimer(name) {
    const id = this._timers.get(name);
    if (id !== undefined) { this.win.clearTimeout(id); this._timers.delete(name); }
  }

  _on(target, ev, fn, opts) {
    target.addEventListener(ev, fn, opts);
    this._listeners.push([target, ev, fn, opts]);
  }

  _observe() {
    this._on(this.win, 'pointermove', (e) => this._onPointer(e), { passive: true });
    this._on(this.doc, 'pointerleave', () => { this._pointer = null; this._setGazeTarget(0, 0); });
    this._on(this.doc, 'visibilitychange', () => { this._docVisible = !this.doc.hidden; this._scheduleAll(); this._updateClasses(); });
    if (this.opts.interactive) {
      this._on(this.host, 'click', () => this.poke());
      this._on(this.host, 'keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.poke(); } });
    }
    if (this.win.ResizeObserver) {
      const ro = new this.win.ResizeObserver(() => this._refreshTier());
      ro.observe(this.host); this._observers.push(ro);
    }
    this._refreshTier();
    if (this.win.IntersectionObserver) {
      const io = new this.win.IntersectionObserver((entries) => {
        const v = entries[entries.length - 1].isIntersecting;
        if (v !== this._visible) { this._visible = v; this._scheduleAll(); this._updateClasses(); }
      });
      io.observe(this.host); this._observers.push(io);
    }
  }
}

/** Optional custom element: <bisco-character state="thinking" profile="avatar"></bisco-character> */
export function defineBiscoElement(rig, assetsBase) {
  if (customElements.get('bisco-character')) return;
  customElements.define('bisco-character', class extends HTMLElement {
    static get observedAttributes() { return ['state']; }
    connectedCallback() {
      this.bisco = new BiscoCharacter(this, rig, {
        assetsBase, profile: this.getAttribute('profile') || 'home', state: this.getAttribute('state') || 'neutral',
      });
    }
    disconnectedCallback() { this.bisco?.destroy(); this.bisco = null; }
    attributeChangedCallback(n, _o, v) { if (n === 'state' && this.bisco && v) this.bisco.setState(v); }
  });
}
