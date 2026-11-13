// UFpinho's small reactions on the home screen: a short greeting when the figure is activated,
// and, after a random 10-30 s of rest, a few seconds of curiosity in which the eyes follow the
// pointer. Only classes and two CSS variables on the figure change; no content is read or written.
// Priorities: a flight (transition.js) beats everything; then the greeting; then curiosity.
{
  const pageDoc = window.parent.document;
  const pageWin = window.parent;
  const HOME = ".ufpinho-home.ufpinho-interactive";
  const GREETING_MS = 800;
  const LOOK_MS = 3800;
  const REST_MIN_MS = 10000;
  const REST_SPAN_MS = 20000;
  const CHECK_MS = 500;
  // In SVG units on the 512 grid: 12 is about 4 px at the home's 180 px. The eyes may not rise,
  // since the specular highlight sits right above them; the visor's clip bounds everything else.
  const EYE_X = 12;
  const EYE_UP = 0;
  const EYE_DOWN = 5;
  // Visor centre, as a fraction of the figure (x 265.5, y 319 on the 512 grid).
  const VISOR_X = 0.519;
  const VISOR_Y = 0.623;
  const finePointer = pageWin.matchMedia("(hover: hover) and (pointer: fine)");
  const stillMotion = pageWin.matchMedia("(prefers-reduced-motion: reduce)");

  let pointer = null;
  let watched = null;
  let restSince = 0;
  let restNeeded = 0;
  let looking = null;
  let greeting = null;
  let settling = 0;

  const flying = () => pageDoc.querySelector(".ufpinho-ghost") !== null;

  function rest() {
    restSince = pageWin.performance.now();
    restNeeded = REST_MIN_MS + Math.random() * REST_SPAN_MS;
  }

  function greet(figure) {
    if (greeting || stillMotion.matches || flying() || figure.style.visibility === "hidden") return;
    stopLooking();
    figure.classList.remove("is-curious");
    figure.classList.add("is-greeting");
    greeting = {
      figure,
      timer: window.setTimeout(() => {
        figure.classList.remove("is-greeting");
        greeting = null;
        rest();
      }, GREETING_MS),
    };
  }

  function onClick(event) {
    const figure = event.target.closest && event.target.closest(HOME);
    if (figure) greet(figure);
  }

  function onKey(event) {
    if (event.key !== "Enter" && event.key !== " ") return;
    const figure = event.target.closest && event.target.closest(HOME);
    if (!figure) return;
    event.preventDefault(); // Space would otherwise scroll the page.
    if (!event.repeat) greet(figure);
  }

  function onPointer(event) {
    if (event.pointerType === "mouse" || event.pointerType === "pen") {
      pointer = { x: event.clientX, y: event.clientY };
    }
  }

  // The figure that may become curious now, or null.
  function idleFigure() {
    const figure = pageDoc.querySelector(HOME);
    if (!figure || figure.style.visibility === "hidden" || greeting || flying()) return null;
    if (pageDoc.visibilityState !== "visible" || !finePointer.matches || stillMotion.matches) return null;
    const box = figure.getBoundingClientRect();
    if (box.width === 0 || box.bottom < 0 || box.top > pageWin.innerHeight) return null;
    return figure;
  }

  function startLooking(figure) {
    looking = { figure, start: pageWin.performance.now(), x: 0, y: 0, frame: 0 };
    figure.classList.add("is-curious", "is-tracking");
    looking.frame = pageWin.requestAnimationFrame(follow);
  }

  function follow(now) {
    if (!looking) return;
    const { figure } = looking;
    if (now - looking.start > LOOK_MS) return stopLooking();
    if (pointer) {
      const box = figure.getBoundingClientRect();
      const dx = pointer.x - (box.left + box.width * VISOR_X);
      const dy = pointer.y - (box.top + box.height * VISOR_Y);
      const distance = Math.hypot(dx, dy) || 1;
      // Full deflection from about one and a half head widths away; closer, proportionally less.
      const reach = Math.min(1, distance / (box.width * 1.5));
      const tx = (dx / distance) * reach * EYE_X;
      const ty = Math.max(-EYE_UP, Math.min(EYE_DOWN, (dy / distance) * reach * EYE_X * 0.5));
      const x = looking.x + (tx - looking.x) * 0.12;
      const y = looking.y + (ty - looking.y) * 0.12;
      if (Math.abs(x - looking.x) > 0.02 || Math.abs(y - looking.y) > 0.02) {
        looking.x = x;
        looking.y = y;
        figure.style.setProperty("--ufpinho-eye-x", x.toFixed(2));
        figure.style.setProperty("--ufpinho-eye-y", y.toFixed(2));
      }
    }
    looking.frame = pageWin.requestAnimationFrame(follow);
  }

  // The eyes go back to the centre through the CSS transition, then the usual face returns.
  function stopLooking() {
    if (!looking) return;
    const { figure, frame } = looking;
    pageWin.cancelAnimationFrame(frame);
    looking = null;
    figure.classList.remove("is-tracking");
    figure.style.removeProperty("--ufpinho-eye-x");
    figure.style.removeProperty("--ufpinho-eye-y");
    window.clearTimeout(settling);
    settling = window.setTimeout(() => {
      if (!looking || looking.figure !== figure) figure.classList.remove("is-curious");
    }, 650);
    rest();
  }

  function check() {
    const figure = idleFigure();
    if (looking) {
      if (figure !== looking.figure) stopLooking();
      return;
    }
    if (figure !== watched) {
      watched = figure;
      rest();
      return;
    }
    if (figure && pointer && pageWin.performance.now() - restSince >= restNeeded) startLooking(figure);
  }

  rest();
  const checker = window.setInterval(check, CHECK_MS);
  pageDoc.addEventListener("click", onClick);
  pageDoc.addEventListener("keydown", onKey);
  pageDoc.addEventListener("pointermove", onPointer, { passive: true });
  window.addEventListener("pagehide", () => {
    window.clearInterval(checker);
    pageDoc.removeEventListener("click", onClick);
    pageDoc.removeEventListener("keydown", onKey);
    pageDoc.removeEventListener("pointermove", onPointer);
    stopLooking();
    window.clearTimeout(settling);
    if (greeting) {
      window.clearTimeout(greeting.timer);
      greeting.figure.classList.remove("is-greeting");
      greeting = null;
    }
    pageDoc.querySelectorAll(".ufpinho.is-curious").forEach((figure) => figure.classList.remove("is-curious"));
  });
}
