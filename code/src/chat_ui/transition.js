// Shared-element transition for Bisco's "lead" figure: home, loading, and the newest answer.
// Streamlit replaces these with different DOM nodes, so one node cannot simply move. When the lead
// changes, a ghost copy takes the old figure's exact place before the next paint; the new lead
// stays hidden while the ghost flies to it, measured live every frame, and hands over on arrival.
// Only one Bisco is visible throughout. Nothing here reads or writes message content.
// The ghost is fixed to the viewport; the destination is measured live, so it follows scrolling.
const LEAD = "[data-ufpinho-lead]";
const VARIANTS = ["home", "loading", "chat"];
const FLIGHT_MS = { "home>loading": 560, "home>chat": 560, "loading>chat": 400, "chat>home": 560, "loading>home": 560 };
const WAIT_FOR_TARGET_MS = 1500;
const leadDoc = window.parent.document;
const leadWin = window.parent;
const calm = leadWin.matchMedia("(prefers-reduced-motion: reduce)");

let lead = null;
let leadBox = null;
let flight = null;

const variantOf = (el) => VARIANTS.find((name) => el.classList.contains(`ufpinho-${name}`));
const allowed = (from, to) => `${from}>${to}` in FLIGHT_MS;

function local(rect) {
  return { left: rect.left, top: rect.top, width: rect.width };
}

function visible(el) {
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.bottom > 0 && r.top < leadWin.innerHeight;
}

// cubic-bezier(0.22, 1, 0.36, 1), solved by bisection on x.
function ease(t) {
  let lo = 0, hi = 1, u = t;
  for (let i = 0; i < 24; i++) {
    u = (lo + hi) / 2;
    const x = 3 * (1 - u) ** 2 * u * 0.22 + 3 * (1 - u) * u * u * 0.36 + u ** 3;
    if (x < t) lo = u; else hi = u;
  }
  return 3 * (1 - u) ** 2 * u + 3 * (1 - u) * u * u + u ** 3;
}

function remember() {
  if (lead && lead.isConnected && !flight) {
    leadBox = visible(lead) ? local(lead.getBoundingClientRect()) : null;
  }
}

function place(ghost, box, size) {
  ghost.style.left = `${box.left}px`;
  ghost.style.top = `${box.top}px`;
  ghost.style.setProperty("--ufpinho-size", `${size}px`);
  ghost.style.transform = `scale(${box.width / size})`;
}

function spawnGhost(source, box) {
  const ghost = source.cloneNode(true);
  ghost.removeAttribute("data-ufpinho-lead");
  ghost.removeAttribute("role");
  ghost.removeAttribute("aria-label");
  ghost.removeAttribute("tabindex");
  ghost.setAttribute("aria-hidden", "true");
  // The copy carries only the figure, never the home's interaction or curiosity state.
  ghost.classList.remove("ufpinho-interactive", "is-greeting", "is-tracking", "is-curious");
  ghost.style.removeProperty("--ufpinho-eye-x");
  ghost.style.removeProperty("--ufpinho-eye-y");
  ghost.querySelectorAll("[id]").forEach((node) => {
    const id = node.id;
    node.id = `${id}-ghost`;
    ghost.querySelectorAll(`[clip-path="url(#${id})"], [filter="url(#${id})"], [mask="url(#${id})"]`).forEach((user) => {
      for (const name of ["clip-path", "filter", "mask"]) {
        if (user.getAttribute(name) === `url(#${id})`) user.setAttribute(name, `url(#${id}-ghost)`);
      }
    });
  });
  ghost.classList.add("ufpinho-ghost");
  ghost.classList.remove("ufpinho-landed");
  if (variantOf(source) !== "home") ghost.classList.add("is-dim");
  ghost.style.visibility = "visible";
  place(ghost, box, box.width);
  leadDoc.body.appendChild(ghost);
  // The figure's own page script gives the copy a quiet character of its own (character.js).
  if (window.biscoGhost) window.biscoGhost.adopt(ghost, source);
  return ghost;
}

const hidden = new Set();
let fading = null;

function hide(el) {
  el.style.visibility = "hidden";
  hidden.add(el);
}

function reveal(el) {
  if (!el) return;
  el.style.removeProperty("visibility");
  hidden.delete(el);
}

// The only figures allowed to stay hidden: the flight's destination, and figures still marked as
// lead that have been superseded by a newer one (Streamlit removes them a moment later). Anything
// else this script hid is shown again, so no avatar can stay invisible.
function enforce(next) {
  for (const el of [...hidden]) {
    const destination = flight && flight.target === el;
    const superseded = el.isConnected && el.matches(LEAD) && el !== next;
    if (!destination && !superseded) reveal(el);
    if (!el.isConnected) hidden.delete(el);
  }
  for (const el of leadDoc.querySelectorAll(LEAD)) {
    if (el !== next && !el.style.visibility) hide(el);
  }
}

// Streamlit may insert the next lead before it removes the previous one, in separate mutation
// batches. The handover is therefore decided when the lead changes, not when a node disappears.
function takeOff(source) {
  flight = { ghost: spawnGhost(source, leadBox), origin: variantOf(source), via: variantOf(source), target: null };
  if (source.isConnected) {
    hide(source);
    flight.source = source;
  }
  flight.expiry = setTimeout(fadeOut, WAIT_FOR_TARGET_MS);
}

function land() {
  const { ghost, target } = flight;
  // The source stays hidden: if it is still connected it is a replaced figure about to be removed.
  reveal(target);
  target.classList.add("ufpinho-landed");
  ghost.remove();
  flight = null;
  lead = target;
  remember();
}

function abandon() {
  if (!flight) return;
  clearTimeout(flight.expiry);
  leadWin.cancelAnimationFrame(flight.raf); // No callback of this flight may drive the next one.
  reveal(flight.target);
  flight.ghost.remove();
  flight = null;
}

function current(ghost) {
  return local(ghost.getBoundingClientRect());
}

function frame(now) {
  if (!flight || !flight.target) return;
  if (!flight.target.isConnected) return freeze();
  if (calm.matches) return land(); // Reduced motion chosen mid-flight: arrive at once.
  const f = flight;
  const p = Math.min(1, (now - f.start) / f.duration);
  const e = ease(p);
  const to = local(f.target.getBoundingClientRect());
  const left = f.from.left + (to.left - f.from.left) * e;
  const top = f.from.top + (to.top - f.from.top) * e;
  const width = f.from.width + (to.width - f.from.width) * e;
  f.ghost.style.transform = `translate(${left - f.from.left}px, ${top - f.from.top}px) scale(${width / f.size})`;
  if (p < 1) f.raf = leadWin.requestAnimationFrame(frame);
  else land();
}

// The target vanished mid-flight: hold the ghost where it is and wait for the next lead.
function freeze() {
  const box = current(flight.ghost);
  flight.ghost.style.transform = "none";
  flight.size = box.width;
  place(flight.ghost, box, box.width);
  flight.target = null;
  flight.from = box;
  clearTimeout(flight.expiry);
  flight.expiry = setTimeout(fadeOut, WAIT_FOR_TARGET_MS);
}

function fadeOut() {
  if (!flight || flight.target) return;
  const { ghost, source } = flight;
  // No destination came: a source that is still the page's lead takes its place back.
  if (source && source.isConnected && source.matches(LEAD)) reveal(source);
  leadWin.cancelAnimationFrame(flight.raf);
  flight = null;
  fading = { ghost, source };
  ghost.classList.add("is-leaving");
  setTimeout(() => ghost.remove(), 260);
}

function fly(target) {
  // A head that would enter from outside the screen is not a recognisable journey: the new figure
  // simply makes its own quiet entrance instead.
  // The journey is judged by where it started, or by the figure the ghost shows now: going back to
  // the home after an early answer is a real chat>home journey.
  const to = variantOf(target);
  const resumed = flight.figure && flight.figure === target.dataset.ufpinhoLead && flight.pairFrom;
  const fromKey = resumed ? flight.pairFrom : allowed(flight.origin, to) ? flight.origin : flight.via;
  if (!allowed(fromKey, to) || !visible(flight.ghost)) {
    abandon();
    lead = target;
    return;
  }
  clearTimeout(flight.expiry);
  const key = `${fromKey}>${to}`;
  const from = current(flight.ghost);
  const size = Math.max(from.width, target.getBoundingClientRect().width);
  hide(target);
  flight.ghost.style.transform = "none";
  place(flight.ghost, from, size);
  flight.from = from;
  flight.size = size;
  flight.target = target;
  flight.start = leadWin.performance.now();
  flight.duration = FLIGHT_MS[key];
  flight.via = to;
  flight.pairFrom = fromKey;
  flight.figure = target.dataset.ufpinhoLead;
  // Face, stroke weight and halo follow the destination; their CSS transitions do the morphing.
  const ghost = flight.ghost;
  for (const name of VARIANTS) ghost.classList.toggle(`ufpinho-${name}`, name === variantOf(target));
  ghost.style.setProperty("--ufpinho-flight", `${flight.duration}ms`);
  ghost.dataset.state = target.dataset.state;
  if (window.biscoGhost) window.biscoGhost.state(ghost, target.dataset.state);
  ghost.classList.toggle("is-dim", variantOf(target) !== "home");
  // One animation loop per flight, however many redirects happen.
  leadWin.cancelAnimationFrame(flight.raf);
  flight.raf = leadWin.requestAnimationFrame(frame);
}

const sameFigure = (a, b) => a && b && a.dataset.ufpinhoLead === b.dataset.ufpinhoLead;
const leadsIn = (node) => (node.matches(LEAD) ? [node] : [...node.querySelectorAll(LEAD)]);
let newest = null;

function onMutations(records) {
  let lostTarget = null;
  for (const record of records) {
    for (const node of record.addedNodes) {
      if (node.nodeType === 1) for (const found of leadsIn(node)) newest = found;
    }
    if (record.type === "attributes" && record.target.matches(LEAD)) newest = record.target;
    for (const node of record.removedNodes) {
      if (node.nodeType !== 1) continue;
      for (const gone of leadsIn(node)) {
        if (flight && flight.target === gone) lostTarget = gone;
        if (gone !== lead) continue;
        lead = null;
        if (!flight && !calm.matches && leadBox) takeOff(gone);
      }
    }
  }
  // The newest arrival is the lead, not the last node in document order: Streamlit may insert the
  // next figure before the one it replaces.
  const all = leadDoc.querySelectorAll(LEAD);
  const next = newest && newest.isConnected && newest.matches(LEAD) ? newest : all[all.length - 1] || null;

  if (lostTarget) {
    if (next && next !== lostTarget && sameFigure(next, lostTarget)) {
      // The destination was re-created by a rerun: keep flying, to the new node.
      hide(next);
      flight.target = next;
    } else {
      freeze();
    }
  }
  if (!flight && next && lead && next !== lead && sameFigure(next, lead)) {
    lead = next; // The same figure re-created by a rerun: nothing travels.
  } else if (!flight && next && lead && next !== lead && lead.isConnected) {
    if (!calm.matches && leadBox && allowed(variantOf(lead), variantOf(next))) takeOff(lead);
    else lead = next;
  }
  if (flight && next && flight.target !== next) {
    // A newer lead while flying: redirect from where the ghost is now. The previous destination
    // stays hidden, since it is being replaced.
    if (flight.target) freeze();
    fly(next);
  } else if (!flight && next !== lead) {
    lead = next;
  }
  if (fading && !fading.ghost.isConnected) fading = null;
  if (fading && next && !flight && next !== fading.source) {
    fading.ghost.remove(); // A late destination appeared: the fading ghost must not stand beside it.
    fading = null;
  }
  enforce(next);
  remember();
}

const leadObserver = new MutationObserver(onMutations);
leadObserver.observe(leadDoc.body, {
  childList: true,
  subtree: true,
  attributes: true,
  attributeFilter: ["data-ufpinho-lead"],
});
leadDoc.addEventListener("scroll", remember, { capture: true, passive: true });
leadWin.addEventListener("resize", remember);
window.addEventListener("pagehide", () => {
  leadObserver.disconnect();
  leadDoc.removeEventListener("scroll", remember, { capture: true });
  leadWin.removeEventListener("resize", remember);
  abandon();
  // Nothing of this script may outlive it: ghosts still fading, and figures it hid.
  leadDoc.querySelectorAll(".ufpinho-ghost").forEach((ghost) => ghost.remove());
  [...hidden].forEach(reveal);
});
onMutations([]);
