// chat_input has no stop-action API in Streamlit 1.40. Overlay the native
// callback button on its submit target, without reparenting React-owned nodes.
// The host is absolute and present even when idle: neither it nor polling
// contributes a row, a gap, or a footer height change.
let stopWasFocused = false;
let stopWasVisible = false;
let waitClockNode = null;
let waitClockStart = 0;
let waitClockElapsed = 0;

function syncWaitControl() {
  const host = doc.querySelector('.st-key-composer_action');
  const stop = host && host.querySelector('button');
  const composer = doc.querySelector('[data-testid="stChatInput"]');
  const send = composer && composer.querySelector('[data-testid="stChatInputSubmitButton"]');
  if (host && stop && !stop.disabled && send && host.offsetParent) {
    const target = send.getBoundingClientRect();
    const parent = host.offsetParent;
    const origin = parent.getBoundingClientRect();
    host.style.left = `${target.left - origin.left - parent.clientLeft + parent.scrollLeft}px`;
    host.style.top = `${target.top - origin.top - parent.clientTop + parent.scrollTop}px`;
    host.style.visibility = 'visible';
    stop.setAttribute('aria-label', 'Parar a espera da resposta');
    stop.title = 'Parar';
    composer.classList.add('ufpi-waiting');
    stopWasVisible = true;
  } else {
    if (host) host.style.visibility = 'hidden';
    if (composer) composer.classList.remove('ufpi-waiting');
    // Return keyboard focus only if the reader was using the stop control.
    const box = composer && composer.querySelector('textarea');
    if (stopWasVisible && stopWasFocused && box && !box.disabled) {
      box.focus({ preventScroll: true });
      stopWasFocused = false;
    }
    stopWasVisible = false;
  }
}

function noteStopFocus(event) {
  stopWasFocused = Boolean(event.target.closest('.st-key-composer_action'));
}

function updateWaitClock() {
  const node = doc.querySelector('.ufpi-progress-elapsed');
  if (node !== waitClockNode) {
    waitClockNode = node;
    waitClockElapsed = node ? Number(node.dataset.elapsed) : 0;
    waitClockStart = window.parent.performance.now();
  }
  if (node) {
    const seconds = waitClockElapsed + Math.floor((window.parent.performance.now() - waitClockStart) / 1000);
    const label = `${seconds} s`;
    if (node.textContent !== label) node.textContent = label;
  }
}

const waitObserver = new MutationObserver(() => {
  syncWaitControl();
  updateWaitClock();
});
waitObserver.observe(doc.body, { childList: true, subtree: true });
const waitResize = new window.parent.ResizeObserver(syncWaitControl);
const waitBottom = doc.querySelector('[data-testid="stBottom"]');
if (waitBottom) waitResize.observe(waitBottom);
const waitTimer = window.setInterval(updateWaitClock, 250);
doc.addEventListener('focusin', noteStopFocus);
window.parent.addEventListener('resize', syncWaitControl);
doc.addEventListener('scroll', syncWaitControl, { capture: true, passive: true });
window.addEventListener('pagehide', () => {
  waitObserver.disconnect();
  waitResize.disconnect();
  window.clearInterval(waitTimer);
  doc.removeEventListener('focusin', noteStopFocus);
  window.parent.removeEventListener('resize', syncWaitControl);
  doc.removeEventListener('scroll', syncWaitControl, { capture: true });
});
syncWaitControl();
updateWaitClock();
