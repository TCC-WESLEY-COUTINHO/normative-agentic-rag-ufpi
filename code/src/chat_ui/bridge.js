// Small browser-side complements Streamlit has no API for. If any selector stops matching,
// the page keeps working and only loses these accessibility and mobile conveniences.
const doc = window.parent.document;
const MOBILE_WIDTH = 768;

function describeControls() {
  doc.querySelectorAll('.st-key-ufpi_scripts iframe').forEach((frame) => {
    frame.setAttribute("tabindex", "-1");
    frame.setAttribute("aria-hidden", "true");
  });
  doc.querySelectorAll('[class*="st-key-conv_open_"] button').forEach((button) => {
    const active = button.closest('[class*="st-key-conv_open_active_"]') !== null;
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  doc.querySelectorAll('[class*="st-key-theme_to_"] button').forEach((button) => {
    const name = button.closest(".st-key-theme_to_dark") ? "Usar tema escuro" : "Usar tema claro";
    button.setAttribute("aria-label", name);
    button.title = name;
  });
  doc.querySelectorAll('[class*="st-key-conv_menu_"] button').forEach((button) => {
    button.setAttribute("aria-label", "Opções da conversa");
  });
}

const mobile = () => window.parent.innerWidth <= MOBILE_WIDTH;
const openSidebar = () => doc.querySelector('[data-testid="stSidebar"][aria-expanded="true"]');
// Menus opened from the drawer (conversation options) are rendered outside it, in a layer.
const LAYER = '[data-baseweb="popover"], [data-baseweb="modal"], [role="dialog"]';
const OUTSIDE_DRAWER =
  'section.stMain, [data-testid="stHeader"], [data-testid="stSidebarCollapsedControl"]';

function closeSidebar(delay = 0) {
  const close = doc.querySelector('[data-testid="stSidebarCollapseButton"] button');
  if (openSidebar() && close) window.setTimeout(() => close.click(), delay);
}

// Up to this width the sidebar is a drawer over the page (styles.css). It closes on a tap outside
// it (the backdrop), after a conversation is chosen or started, and with Escape. Captured before
// Streamlit handles the click, so the tap that opens the drawer is never mistaken for one outside.
function closeSidebarOnMobile(event) {
  if (!mobile() || !openSidebar()) return;
  const target = event.target;
  if (!target.closest('[data-testid="stSidebar"]') && !target.closest(LAYER)) {
    event.preventDefault();
    event.stopPropagation();
    closeSidebar();
    return;
  }
  if (target.closest('[class*="st-key-conv_open_"], .st-key-new_conversation')) closeSidebar(60);
}

function closeSidebarOnEscape(event) {
  if (event.key !== "Escape" || !mobile() || !openSidebar() || doc.querySelector(LAYER)) return;
  event.preventDefault();
  closeSidebar();
}

// While the drawer is open the page behind is inert, so focus and assistive technology stay in
// the drawer; focus moves into it when it opens and back to its opener when it closes. The state
// found at load is the starting point, and the automatic close below is not the reader's action:
// neither moves focus.
let drawerOpen = mobile() && openSidebar() !== null;
let quietClose = false;
function syncDrawer() {
  const open = mobile() && openSidebar() !== null;
  // Everything outside the drawer: the page, the header and the (covered) button that opens it.
  doc.querySelectorAll(OUTSIDE_DRAWER).forEach((el) => el.toggleAttribute("inert", open));
  if (!open && drawerOpen && quietClose) {
    quietClose = false;
  } else if (open && !drawerOpen) {
    const close = doc.querySelector('[data-testid="stSidebarCollapseButton"] button');
    if (close) close.focus({ preventScroll: true });
  } else if (!open && drawerOpen) {
    const active = doc.activeElement;
    if (!active || active === doc.body || active.closest('[data-testid="stSidebar"]')) {
      const opener = doc.querySelector('[data-testid="stSidebarCollapsedControl"] button');
      if (opener) opener.focus({ preventScroll: true });
    }
  }
  drawerOpen = open;
}

// Streamlit collapses below 768px but already overlays at 768px, which would block the page.
if (mobile() && openSidebar()) {
  quietClose = true;
  closeSidebar();
}

// Clipboard access needs a secure context; plain http on a network address uses the older path.
async function writeToClipboard(text) {
  const clipboard = window.parent.navigator.clipboard;
  if (clipboard && window.parent.isSecureContext) return clipboard.writeText(text);
  const area = doc.createElement("textarea");
  area.value = text;
  area.style.position = "fixed";
  area.style.opacity = "0";
  doc.body.appendChild(area);
  area.select();
  const copied = doc.execCommand("copy");
  area.remove();
  if (!copied) throw new Error("copy refused");
}

function copyAnswer(event) {
  const button = event.target.closest(".ufpi-copy");
  if (!button) return;
  const label = button.querySelector(".ufpi-copy-label");
  const original = "Copiar resposta";
  const show = (text) => {
    label.textContent = text;
    window.setTimeout(() => { label.textContent = original; }, 2000);
  };
  writeToClipboard(button.dataset.copy).then(
    () => show("Copiada"),
    () => show("Não foi possível copiar"),
  );
}

// "Go to the latest message": appears when a conversation is scrolled away from its end. Taking
// the reader to the end is enough to resume following, since Streamlit sticks to the bottom again
// once it is reached. Built from static nodes; it carries no content.
const JUMP_DISTANCE = 240;
const SVG = "http://www.w3.org/2000/svg";
const jump = doc.createElement("button");
jump.type = "button";
jump.className = "ufpi-jump";
jump.setAttribute("aria-label", "Ir para a mensagem mais recente");
jump.title = "Ir para a mensagem mais recente";
const arrow = doc.createElementNS(SVG, "svg");
arrow.setAttribute("viewBox", "0 0 24 24");
arrow.setAttribute("aria-hidden", "true");
const arrowPath = doc.createElementNS(SVG, "path");
arrowPath.setAttribute("d", "M12 5v14M6 13l6 6 6-6");
arrow.appendChild(arrowPath);
jump.appendChild(arrow);
doc.body.appendChild(jump);
const stillMotion = window.parent.matchMedia("(prefers-reduced-motion: reduce)");
let jumpFrame = 0;

function updateJump() {
  jumpFrame = 0;
  const scroller = doc.querySelector("section.stMain");
  const chatting = doc.querySelector('[class*="st-key-msg_"]') !== null;
  const away = scroller && chatting && scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight > JUMP_DISTANCE;
  const show = Boolean(away) && !(mobile() && openSidebar());
  jump.classList.toggle("is-visible", show);
  if (!show) return;
  const panel = scroller.getBoundingClientRect();
  const composer = doc.querySelector('[data-testid="stBottom"] [data-testid="stChatInput"]');
  const floor = composer ? composer.getBoundingClientRect().top : panel.bottom;
  jump.style.left = `${panel.left + panel.width / 2}px`;
  jump.style.top = `${floor - 52}px`;
}

function scheduleJump() {
  if (!jumpFrame) jumpFrame = window.parent.requestAnimationFrame(updateJump);
}

// While a turn is in progress the button also resumes following its end: one smooth scroll, during
// which growth is not chased; on arrival the end is kept again, at once, as the content grows.
let jumping = false;
let jumpTimer = 0;
function endJump() {
  if (!jumping) return;
  jumping = false;
  window.clearTimeout(jumpTimer);
  keepTurnEnd();
}

function goToLatest() {
  const scroller = doc.querySelector("section.stMain");
  if (!scroller) return;
  if (turnInProgress()) following = true;
  const smooth = !stillMotion.matches;
  jumping = smooth;
  scroller.scrollTo({ top: scroller.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  if (smooth) {
    scroller.addEventListener("scrollend", endJump, { once: true });
    jumpTimer = window.setTimeout(endJump, 900);
  } else {
    keepTurnEnd();
  }
  // The button is about to disappear: keyboard focus continues in the composer.
  const box = doc.querySelector('[data-testid="stChatInputTextArea"]');
  if (box && !box.disabled) box.focus({ preventScroll: true });
}
jump.addEventListener("click", goToLatest);

// The home opens at its top. On a short screen it is taller than the panel, and Streamlit, which
// follows the end of its scroll area, would carry it down while the page is still being built.
// Until the reader's first gesture (or for 3 s), growth on the home puts it back at the top; once
// it is moved up, Streamlit stops following, so this ends by itself.
const HOME_SETTLE_MS = 3000;
let homeSince = 0;
let homeTouched = false;
const resized = new window.parent.ResizeObserver(() => {
  keepHomeTop();
  keepTurnEnd();
  scheduleJump(); // The composer grows and shrinks: the button stays above it.
});

// A question was just sent: its turn (the question and the thinking figure) appears at the end of
// the conversation, above the composer, wherever the reader was. From then on the end is followed:
// while the figure thinks and while the answer is presented (presentation.js), every change of the
// content's size keeps the end in view, in the same frame, with no smooth scrolling of its own.
// The reader moving up (wheel, touch, keys, scroll bar) stops following and keeps their place; the
// jump button, or reaching the end again, resumes it.
let turnPinned = null;
let following = false;
const UP_KEYS = new Set(["ArrowUp", "PageUp", "Home"]);

// A new turn is noted as soon as its figure is inserted: mutation callbacks run before any event of
// the reader, so a gesture made right after the send is never mistaken for one made before it.
function noteTurn() {
  const progress = doc.querySelector(".ufpi-progress");
  if (progress !== turnPinned) {
    const started = progress && !turnPinned;
    const ended = !progress && turnPinned;
    // Noted before reacting: what follows (ending a presentation) keeps the end, which notes again.
    turnPinned = progress;
    if (started) {
      following = true;
      guardScroller();
      armPresentation();
    }
    if (ended) closePresentationWindow();
  }
}

const turnInProgress = () => Boolean(turnPinned) || presentationActive();

function keepTurnEnd() {
  const scroller = doc.querySelector("section.stMain");
  noteTurn();
  if (turnInProgress() && following && !jumping && scroller) {
    const end = scroller.scrollHeight - scroller.clientHeight;
    if (scroller.scrollTop < end - 1) scroller.scrollTop = end;
  }
}

let upIntentAt = -Infinity;
function stopFollowing() {
  upIntentAt = window.parent.performance.now();
  if (turnInProgress()) following = false;
}

// Streamlit's own stick-to-bottom animates the same scroll position towards an end it measured a
// moment earlier: on every growth it would pull the page back a few pixels behind the end kept here,
// and after the reader moves up it would carry them elsewhere again. During a turn, scripted moves
// against the reader's choice are dropped: backward while the end is followed, any once the reader
// has moved up. The reader's own scrolling is native and never passes through this setter;
// the jump button uses scrollTo. Outside a turn nothing is changed.
const nativeScrollTop = Object.getOwnPropertyDescriptor(window.parent.Element.prototype, "scrollTop");
let guardedScroller = null;
function guardScroller() {
  const scroller = doc.querySelector("section.stMain");
  if (!scroller || scroller === guardedScroller || !nativeScrollTop) return;
  releaseScroller();
  Object.defineProperty(scroller, "scrollTop", {
    configurable: true,
    get() {
      return nativeScrollTop.get.call(this);
    },
    set(value) {
      if (turnInProgress()) {
        // Following: only forward. The reader moved up: no scripted move at all.
        if (!following || value < nativeScrollTop.get.call(this)) return;
      }
      nativeScrollTop.set.call(this, value);
    },
  });
  guardedScroller = scroller;
}
function releaseScroller() {
  if (guardedScroller) delete guardedScroller.scrollTop;
  guardedScroller = null;
}

// Intent, not position alone: these mean "up" even before the page has moved.
function readUpGesture(event) {
  if (event.type === "wheel" && event.deltaY < 0) stopFollowing();
  if (event.type === "keydown" && UP_KEYS.has(event.key) && !event.target.closest("textarea, input")) {
    stopFollowing();
  }
}
let touchY = null;
function readTouch(event) {
  const y = event.touches.length ? event.touches[0].clientY : null;
  if (event.type === "touchmove" && touchY !== null && y !== null && y > touchY + 4) stopFollowing();
  touchY = y;
}

// The scroll bar, or any other way of moving: away from the end stops following; back at the end
// (as after the jump button) resumes it.
// Only a position that went up counts: the content or the composer growing also takes the end away,
// and that is followed, not a request to stop.
let lastScrollTop = 0;
function readScroll(event) {
  const scroller = doc.querySelector("section.stMain");
  if (!scroller || event.target !== scroller) return;
  const top = scroller.scrollTop;
  const wentUp = top < lastScrollTop - 1;
  lastScrollTop = top;
  if (jumping) {
    // The button's movement only goes down: a move up during it is the reader, and wins.
    if (!wentUp) return;
    jumping = false;
    window.clearTimeout(jumpTimer);
    scroller.removeEventListener("scrollend", endJump);
  }
  const away = scroller.scrollHeight - top - scroller.clientHeight;
  // A movement up made by the reader, however small. Only with the reader's input: the browser also
  // lowers the position by itself when Streamlit briefly shrinks the page while it renders again.
  const byReader = pointerHeld || window.parent.performance.now() - lastInputAt < 1000;
  if (wentUp && away > 2 && byReader) {
    stopFollowing();
  } else if (away <= 2 && turnInProgress()) {
    // Reaching the end resumes, unless it is the tail of a movement that had just been undone by
    // the reader moving up (Streamlit's animation can still arrive there a moment later).
    if (window.parent.performance.now() - upIntentAt > 600) following = true;
  }
}
let watchedBlock = null;

function keepHomeTop() {
  const scroller = doc.querySelector("section.stMain");
  const home = doc.querySelector(".st-key-empty_state");
  if (!home) {
    homeSince = 0;
    return;
  }
  const now = window.parent.performance.now();
  if (!homeSince) {
    homeSince = now;
    homeTouched = false;
  }
  if (!homeTouched && now - homeSince < HOME_SETTLE_MS && scroller && scroller.scrollTop > 0) {
    scroller.scrollTop = 0;
  }
}

// The content (home growth) and the pinned composer (its height places the jump button).
let watchedBottom = null;
function watchHomeBlock() {
  const block = doc.querySelector('[data-testid="stMainBlockContainer"]');
  const bottom = doc.querySelector('[data-testid="stBottom"]');
  if (block !== watchedBlock) {
    if (watchedBlock) resized.unobserve(watchedBlock);
    watchedBlock = block;
    if (block) resized.observe(block);
  }
  if (bottom !== watchedBottom) {
    if (watchedBottom) resized.unobserve(watchedBottom);
    watchedBottom = bottom;
    if (bottom) resized.observe(bottom);
  }
}

// The reader's input, for telling their scrolling (wheel, touch, keys, the scroll bar) from the
// browser's and Streamlit's.
let lastInputAt = -Infinity;
let pointerHeld = false;
function touchHome(event) {
  homeTouched = true;
  lastInputAt = window.parent.performance.now();
  if (event && event.type === "pointerdown") pointerHeld = true;
}
function releasePointer() {
  pointerHeld = false;
  lastInputAt = window.parent.performance.now();
}
const GESTURES = ["wheel", "touchstart", "keydown", "pointerdown"];
const POINTER_ENDS = ["pointerup", "pointercancel"];

let scheduled = false;
const controlsObserver = new MutationObserver(() => {
  noteTurn();
  // In the mutation callback itself, before the browser paints the newly inserted answer.
  presentFreshAnswer();
  if (scheduled) return;
  scheduled = true;
  // A timer, because animation frames do not fire in this zero-height frame.
  window.setTimeout(() => {
    scheduled = false;
    describeControls();
    syncDrawer();
    updateJump();
    watchHomeBlock();
    keepHomeTop();
    keepTurnEnd();
  }, 50);
});
controlsObserver.observe(doc.body, {
  childList: true,
  subtree: true,
  attributes: true,
  attributeFilter: ["aria-expanded"],
});

doc.addEventListener("click", closeSidebarOnMobile, true);
doc.addEventListener("keydown", closeSidebarOnEscape);
window.parent.addEventListener("resize", syncDrawer);
doc.addEventListener("scroll", scheduleJump, { capture: true, passive: true });
window.parent.addEventListener("resize", scheduleJump);
doc.addEventListener("click", copyAnswer);
GESTURES.forEach((name) => doc.addEventListener(name, touchHome, { capture: true, passive: true }));
POINTER_ENDS.forEach((name) => doc.addEventListener(name, releasePointer, { capture: true, passive: true }));
doc.addEventListener("wheel", readUpGesture, { capture: true, passive: true });
doc.addEventListener("keydown", readUpGesture, { capture: true, passive: true });
doc.addEventListener("touchstart", readTouch, { capture: true, passive: true });
doc.addEventListener("touchmove", readTouch, { capture: true, passive: true });
doc.addEventListener("scroll", readScroll, { capture: true, passive: true });
doc.body.classList.add("ufpi-enhanced");
window.addEventListener("pagehide", () => {
  controlsObserver.disconnect();
  resized.disconnect();
  GESTURES.forEach((name) => doc.removeEventListener(name, touchHome, { capture: true }));
  POINTER_ENDS.forEach((name) => doc.removeEventListener(name, releasePointer, { capture: true }));
  doc.removeEventListener("wheel", readUpGesture, { capture: true });
  doc.removeEventListener("keydown", readUpGesture, { capture: true });
  doc.removeEventListener("touchstart", readTouch, { capture: true });
  doc.removeEventListener("touchmove", readTouch, { capture: true });
  doc.removeEventListener("scroll", readScroll, { capture: true });
  window.clearTimeout(jumpTimer);
  jumping = false;
  const jumpScroller = doc.querySelector("section.stMain");
  if (jumpScroller) jumpScroller.removeEventListener("scrollend", endJump);
  releaseScroller();
  doc.removeEventListener("scroll", scheduleJump, { capture: true });
  window.parent.removeEventListener("resize", scheduleJump);
  window.parent.cancelAnimationFrame(jumpFrame);
  jump.remove();
  doc.removeEventListener("click", closeSidebarOnMobile, true);
  doc.removeEventListener("keydown", closeSidebarOnEscape);
  window.parent.removeEventListener("resize", syncDrawer);
  doc.querySelectorAll(OUTSIDE_DRAWER).forEach((el) => el.removeAttribute("inert"));
  doc.removeEventListener("click", copyAnswer);
  doc.body.classList.remove("ufpi-enhanced");
});
describeControls();
syncDrawer();
updateJump();
watchHomeBlock();
keepHomeTop();
