// Bisco on the page. The live figures (home, loading and the newest answer) get the full rig from
// bisco.js: float, blinks, contextual gaze, line boil, and on the home a short reaction when
// activated. Every other figure keeps its still picture. Instances follow Streamlit's DOM: a figure
// that is replaced or removed loses its instance, its replacement gets a fresh one, so nothing
// accumulates across reruns. Only the figure's own subtree, classes and attributes are touched; no
// message content is read or written. Motion preferences are honoured by bisco.js itself
// (prefers-reduced-motion: reduce), so this script only needs to wire things up.
// Helpers are block-scoped const functions: a function declaration inside a block would leak to the
// global scope of the shared page script and could replace another page script's function.
{
  const pageDoc = window.parent.document;
  const pageWin = window.parent;
  const ASSETS = "app/static/bisco";
  const LIVE = ".ufpinho-home, .ufpinho-loading, .ufpinho-chat[data-ufpinho-lead]";
  const HOME = ".ufpinho-home.ufpinho-interactive";
  const PROFILE = { home: "home", loading: "processing", chat: "avatar" };
  // The home welcomes with the approved smile (closed, happy eyes), then settles on open eyes, so
  // Bisco can look around, follow the pointer and blink. Click reactions return to that face.
  const WELCOME_MS = 2400;
  const QUIET = { float: false, lineBoil: false, autoBlink: false, saccades: false, tracking: false, headFollow: false };
  const stillMotion = pageWin.matchMedia("(prefers-reduced-motion: reduce)");
  const live = new Map(); // figure -> { bisco, host, state, welcome }
  const ghosts = new Map(); // flying copy -> { bisco, host, state }
  let pending = 0;

  const variantOf = (el) => ["home", "loading", "chat"].find((name) => el.classList.contains(`ufpinho-${name}`));
  const isGhost = (el) => el.classList.contains("ufpinho-ghost");

  const create = (figure, options, state = figure.dataset.state) => {
    const host = figure.querySelector(".bisco-host");
    if (!host) return null;
    const bisco = new BiscoRuntime.BiscoCharacter(host, BISCO_RIG, {
      win: pageWin, assetsBase: ASSETS, interactive: false, state, ...options,
    });
    // The still picture stays until every live layer is decoded, then the two swap in one step
    // (character.css keeps the live layers invisible until then): nothing flashes or doubles.
    const ready = bisco.preload().then(() => {
      if (!bisco._destroyed) host.classList.add("bisco-live");
      return !bisco._destroyed;
    });
    return { bisco, host, state, welcome: 0, ready };
  };

  const release = (map, figure) => {
    const entry = map.get(figure);
    if (!entry) return;
    if (entry.welcome) pageWin.clearTimeout(entry.welcome);
    entry.bisco.destroy();
    entry.host.classList.remove("bisco-live");
    map.delete(figure);
  };

  const intact = (figure, entry) =>
    figure.isConnected && entry.host.isConnected && entry.host.contains(entry.bisco.elFloat);

  const welcome = (figure, entry) => {
    entry.welcome = pageWin.setTimeout(() => {
      entry.welcome = 0;
      if (live.get(figure) === entry && figure.dataset.state === "happy") entry.bisco.setState("neutral");
    }, WELCOME_MS);
  };

  const sync = () => {
    pending = 0;
    for (const [figure, entry] of live) {
      if (!intact(figure, entry) || !figure.matches(LIVE) || isGhost(figure)) release(live, figure);
      else if (figure.dataset.state !== entry.state) {
        entry.state = figure.dataset.state;
        entry.bisco.setState(entry.state); // same node, new expression: a transition, not a rebuild
      }
    }
    for (const [ghost, entry] of ghosts) if (!intact(ghost, entry)) release(ghosts, ghost);
    for (const figure of pageDoc.querySelectorAll(LIVE)) {
      if (isGhost(figure) || live.has(figure)) continue;
      const variant = variantOf(figure);
      const entry = create(figure, { profile: PROFILE[variant], tracking: variant === "home" });
      if (!entry) continue;
      live.set(figure, entry);
      // The welcome only starts once the live figure is on screen.
      if (variant === "home" && entry.state === "happy") entry.ready.then((ok) => { if (ok) welcome(figure, entry); });
    }
  };

  const schedule = () => {
    if (!pending) pending = pageWin.requestAnimationFrame(sync);
  };

  // The flying copy made by transition.js carries a frozen clone of the source's live layers. It is
  // replaced by a quiet instance whose expression follows the destination, so the face changes by
  // the rig's own transition (never two faces at once) while the copy flies.
  window.biscoGhost = {
    adopt: (ghost, source) => {
      const host = ghost.querySelector(".bisco-host");
      if (!host) return;
      for (const child of [...host.children]) if (!child.classList.contains("bisco-still")) child.remove();
      host.setAttribute("class", "bisco-host");
      // Start from the face the source shows right now (the home may have settled from its
      // welcome smile to open eyes), not from its markup.
      const origin = source && live.get(source);
      const state = origin ? origin.bisco.state : ghost.dataset.state;
      const entry = create(ghost, { profile: "processing", ...QUIET, reducedMotion: stillMotion.matches ? "reduce" : "auto" }, state);
      if (!entry) return;
      host.classList.add("bisco-live"); // its layers were already decoded for the source figure
      ghosts.set(ghost, entry);
    },
    state: (ghost, state) => {
      const entry = ghosts.get(ghost);
      if (entry && state && entry.state !== state) {
        entry.state = state;
        entry.bisco.setState(state);
      }
    },
  };

  const react = (figure) => {
    if (pageDoc.querySelector(".ufpinho-ghost") || figure.style.visibility === "hidden") return;
    const entry = live.get(figure);
    if (entry) entry.bisco.poke();
  };

  const onClick = (event) => {
    const figure = event.target.closest && event.target.closest(HOME);
    if (figure) react(figure);
  };

  const onKey = (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const figure = event.target.closest && event.target.closest(HOME);
    if (!figure) return;
    event.preventDefault(); // Space would otherwise scroll the page.
    if (!event.repeat) react(figure);
  };

  const observer = new MutationObserver(schedule);
  observer.observe(pageDoc.body, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["data-state", "data-ufpinho-lead"],
  });
  pageDoc.addEventListener("click", onClick);
  pageDoc.addEventListener("keydown", onKey);
  window.addEventListener("pagehide", () => {
    observer.disconnect();
    pageDoc.removeEventListener("click", onClick);
    pageDoc.removeEventListener("keydown", onKey);
    if (pending) pageWin.cancelAnimationFrame(pending);
    for (const figure of [...live.keys()]) release(live, figure);
    for (const ghost of [...ghosts.keys()]) release(ghosts, ghost);
    delete window.biscoGhost;
  });
  sync();
}
