// Progressive presentation of a freshly received answer. The service sends the answer whole, after
// the guard accepted it; nothing here reads, generates or changes content: the page only shows what
// it already holds, in reading order, so that the layout really grows with what is visible.
//
//   PENDING            the question was sent; the progress figure is shown (bridge.js).
//   REVEALING_ANSWER   the answer text is built into a visual copy, node by node, word by word. The
//                      rendered original stays in the page for assistive technology only, with no
//                      size; everything after the text in the message takes no space yet.
//   REVEALING_SOURCES  the copy is swapped for the original in one frame (same markup, same height),
//                      then the following parts enter one by one: the copy button, the notes, the
//                      sources heading, its hint, each norm and each of its articles.
//   COMPLETE           nothing is held; the page is exactly as Streamlit rendered it.
//
// Only an answer that arrives after a question sent in this page is presented; answers already in
// the conversation (a reload, another conversation, a rerun) are shown at once. Anything unexpected
// (a part rendered again, the message gone, the reader clicking into the parts) completes it.
const PRESENT_MARKDOWN = '[data-testid="stMarkdownContainer"]:not([data-ufpi-copy-of])';
const PRESENT_TEXT_MIN_MS = 500;
const PRESENT_TEXT_MAX_MS = 2000;
const PRESENT_MS_PER_WORD = 4;
const PRESENT_STEP_MIN_MS = 45;
const PRESENT_STEP_MAX_MS = 110;
const PRESENT_STEPS_MS = 800;
// Notes stated before the text (clarification, limitation) enter first, then the text begins.
const PRESENT_NOTES_MS = 160;
// Streamlit may take the progress figure's place for the answer's message before its text arrives.
const PRESENT_WAIT_MS = 3000;
const ACTIVE_CONVERSATION = '[class*="st-key-conv_open_active_"]';

// What a sent question may present: the AI message right after it, in the conversation it was
// sent in, before the window after the progress figure closes. Nothing else is ever presented.
let armed = null;
let presenting = null;

const keyOf = (el, prefix) =>
  el ? [...el.classList].find((name) => name.startsWith(prefix)) || null : null;
const activeConversation = () => keyOf(doc.querySelector(ACTIVE_CONVERSATION), "st-key-conv_open_active_");

// A question was sent (its progress figure was just inserted, after the question itself).
function armPresentation() {
  completePresentation(); // A new question ends any presentation still running.
  disarmPresentation();
  if (stillMotion.matches) return;
  const questions = [...doc.querySelectorAll('[class*="st-key-msg_human_"]')]
    .map((el) => Number((keyOf(el, "st-key-msg_human_") || "").slice("st-key-msg_human_".length)))
    .filter((index) => Number.isInteger(index));
  if (!questions.length) return;
  const index = Math.max(...questions) + 1;
  armed = {
    message: `st-key-msg_ai_${index}`,
    answer: `st-key-ans_${index}`,
    conversation: activeConversation(),
    until: 0,
    held: new Set(),
  };
}

// The progress figure is gone: the turn has ended, with or without an answer.
function closePresentationWindow() {
  if (armed && !armed.until) armed.until = window.parent.performance.now() + PRESENT_WAIT_MS;
}

// Nothing armed stays held: notes held while waiting for the text are shown as rendered.
function disarmPresentation() {
  if (!armed) return;
  armed.held.forEach((el) => el.removeAttribute("data-ufpi-wait"));
  armed = null;
}

const presentationActive = () => presenting !== null;

// The column of a message: its first vertical block (the answer's own block is one too, inside it).
const columnOf = (message) =>
  message.querySelector('[data-testid="stChatMessageContent"] [data-testid="stVerticalBlock"]');

// The parts of the message that follow the answer text, in page order; the figure stays in place
// (it is positioned at the top of the message and is the transition's destination).
function laterParts(state) {
  const parts = [];
  let after = false;
  for (const child of state.column.children) {
    if (child.contains(state.box)) after = true;
    else if (after && !child.querySelector(".ufpinho-chat")) parts.push(child);
  }
  return parts;
}

const hold = (el) => el.setAttribute("data-ufpi-wait", "");

function release(el) {
  el.removeAttribute("data-ufpi-wait");
  if (!stillMotion.matches) el.setAttribute("data-ufpi-enter", "");
}

// Called in the mutation callback, before the browser paints a newly inserted node.
function presentFreshAnswer() {
  if (presenting) {
    holdLaterParts(presenting);
    return;
  }
  if (!armed) return;
  const now = window.parent.performance.now();
  const late = armed.until && now > armed.until;
  if (late || stillMotion.matches || activeConversation() !== armed.conversation) {
    // Too late, reduced motion, or another conversation: everything is shown as it is.
    disarmPresentation();
    return;
  }
  const message = doc.querySelector(`.${armed.message}`);
  const column = message && columnOf(message);
  if (!column) return;
  const box = column.querySelector(`.${armed.answer}`);
  const original = box && box.querySelector(PRESENT_MARKDOWN);
  if (!original) {
    // Notes stated before the text wait for it; a message that ends without text (an error) shows
    // them as soon as its last part, the figure, has arrived.
    for (const child of column.children) {
      if (child.querySelector(".ufpinho-chat")) {
        disarmPresentation();
        return;
      }
      if (child.querySelector(".ufpi-note") && !child.hasAttribute("data-ufpi-wait")) {
        hold(child);
        armed.held.add(child);
      }
    }
    return;
  }
  const notes = [...armed.held];
  armed = null;
  if (stillMotion.matches || !message.querySelector('[data-testid="stChatMessage"]')) {
    notes.forEach((el) => el.removeAttribute("data-ufpi-wait"));
    return;
  }
  presenting = {
    stage: "REVEALING_ANSWER",
    box,
    column,
    message: message.querySelector('[data-testid="stChatMessage"]'),
    original,
    text: original.textContent,
    conversation: activeConversation(),
    copy: null,
    events: [],
    next: 0,
    words: 0,
    shown: 0,
    duration: 0,
    started: 0,
    released: 0,
    steps: [],
    step: 0,
    gap: 0,
    held: new Set(notes),
    frame: 0,
  };
  holdLaterParts(presenting);
  buildAnswerCopy(presenting);
  // Notes before the text enter first; the text begins just after them.
  notes.forEach((el) => {
    presenting.held.delete(el);
    if (el.isConnected) release(el);
  });
  if (notes.length) presenting.started += PRESENT_NOTES_MS;
  presenting.message.addEventListener("click", completeOnInteraction, true);
  presenting.frame = window.parent.requestAnimationFrame(presentFrame);
}

// Every part after the text not yet released takes no space; parts released before a rerun that
// rendered them again are shown, never held back a second time.
function holdLaterParts(state) {
  if (state.stage === "COMPLETE") return;
  laterParts(state).forEach((part, index) => {
    if (index < state.released || part.hasAttribute("data-ufpi-wait")) return;
    hold(part);
    state.held.add(part);
  });
}

// Plan the copy: shallow copies of the original's elements, appended in reading order, and its
// text appended word by word, so the copy is always a prefix of the original, laid out as it.
function buildAnswerCopy(state) {
  const copy = state.original.cloneNode(false);
  copy.setAttribute("data-ufpi-copy-of", "answer");
  copy.setAttribute("aria-hidden", "true");
  copy.setAttribute("inert", "");
  copy.removeAttribute("id");
  const walk = (source, target) => {
    source.childNodes.forEach((child) => {
      if (child.nodeType === 3) {
        const text = doc.createTextNode("");
        state.events.push({ run: () => target.appendChild(text), words: 0 });
        child.nodeValue.split(/(\s+)/).forEach((part) => {
          if (part) state.events.push({ run: () => text.appendData(part), words: /\S/.test(part) ? 1 : 0 });
        });
      } else if (child.nodeType === 1) {
        const element = child.cloneNode(false);
        element.removeAttribute("id");
        state.events.push({ run: () => target.appendChild(element), words: 0 });
        walk(child, element);
      }
    });
  };
  walk(state.original, copy);
  state.words = state.events.reduce((sum, event) => sum + event.words, 0);
  state.duration = Math.min(
    PRESENT_TEXT_MAX_MS,
    Math.max(PRESENT_TEXT_MIN_MS, state.words * PRESENT_MS_PER_WORD + 300),
  );
  state.original.setAttribute("data-ufpi-held", "");
  state.original.after(copy);
  state.copy = copy;
  state.started = window.parent.performance.now();
}

// The rendering this presentation depends on is still the one it started with: the same
// conversation, and the same original text (Streamlit may reuse nodes in place for another one).
function presentationIntact(state) {
  return (
    !stillMotion.matches &&
    state.message.isConnected &&
    state.original.isConnected &&
    state.original.textContent === state.text &&
    activeConversation() === state.conversation &&
    (state.stage !== "REVEALING_ANSWER" ||
      (state.original.hasAttribute("data-ufpi-held") && state.copy && state.copy.isConnected))
  );
}

function presentFrame(now) {
  const state = presenting;
  if (!state) return;
  state.frame = 0;
  if (!presentationIntact(state)) {
    completePresentation();
    return;
  }
  if (state.stage === "REVEALING_ANSWER") {
    const target = Math.ceil(state.words * Math.min(1, (now - state.started) / state.duration));
    while (state.next < state.events.length) {
      const event = state.events[state.next];
      if (event.words && state.shown >= target) break;
      event.run();
      state.shown += event.words;
      state.next += 1;
    }
    if (state.next >= state.events.length) beginSources(state, now);
  } else if (state.stage === "REVEALING_SOURCES") {
    while (state.step < state.steps.length && now >= state.started + state.step * state.gap) {
      state.steps[state.step]();
      state.step += 1;
    }
    if (state.step >= state.steps.length) {
      completePresentation();
      return;
    }
  }
  keepTurnEnd(); // The reader following the end sees the new line at once (bridge.js).
  state.frame = window.parent.requestAnimationFrame(presentFrame);
}

// The full copy and the original have the same markup in the same place: swapping them in one frame
// changes nothing on screen. Then the following parts enter in order.
function beginSources(state, now) {
  state.original.removeAttribute("data-ufpi-held");
  state.copy.remove();
  state.copy = null;
  state.stage = "REVEALING_SOURCES";
  state.started = now;
  laterParts(state).forEach((part, index) => {
    state.steps.push(() => {
      state.released = Math.max(state.released, index + 1);
      state.held.delete(part);
      if (part.isConnected) release(part);
    });
    // Sources listed open enter heading first, then hint, each norm and each of its articles. A
    // closed list ("Trechos consultados") shows only its heading, as it always does.
    const sources = part.querySelector("details.ufpi-sources[open]");
    if (!sources) return;
    const items = sources.querySelectorAll(".ufpi-sources-hint, .ufpi-norm, .ufpi-ref");
    items.forEach((item) => {
      hold(item);
      state.held.add(item);
      state.steps.push(() => {
        state.held.delete(item);
        if (item.isConnected) release(item);
      });
    });
  });
  state.gap = Math.min(
    PRESENT_STEP_MAX_MS,
    Math.max(PRESENT_STEP_MIN_MS, PRESENT_STEPS_MS / Math.max(1, state.steps.length)),
  );
}

// The reader opening an article or using a control while the parts enter sees all of it at once.
function completeOnInteraction(event) {
  if (presenting && presenting.stage === "REVEALING_SOURCES" && !event.target.closest(".ufpinho")) {
    completePresentation();
  }
}

// Whatever happened, nothing stays held: every part, and the original text, are shown as rendered.
function completePresentation() {
  const state = presenting;
  if (!state) return;
  state.stage = "COMPLETE";
  if (state.frame) window.parent.cancelAnimationFrame(state.frame);
  state.message.removeEventListener("click", completeOnInteraction, true);
  if (state.copy) state.copy.remove();
  state.original.removeAttribute("data-ufpi-held");
  state.held.forEach((el) => el.removeAttribute("data-ufpi-wait"));
  doc.querySelectorAll("[data-ufpi-wait], [data-ufpi-held]").forEach((el) => {
    el.removeAttribute("data-ufpi-wait");
    el.removeAttribute("data-ufpi-held");
  });
  doc.querySelectorAll("[data-ufpi-copy-of]").forEach((el) => el.remove());
  // Still part of the turn: what has just become visible is followed before the turn ends.
  keepTurnEnd();
  presenting = null;
  // The entrance marks are removed once their animation has played.
  window.setTimeout(() => {
    if (presenting) return;
    doc.querySelectorAll("[data-ufpi-enter]").forEach((el) => el.removeAttribute("data-ufpi-enter"));
  }, 400);
}

// Reduced motion turned on at any moment shows everything at once, without waiting for a change.
function presentStill() {
  if (!stillMotion.matches) return;
  disarmPresentation();
  completePresentation();
}
stillMotion.addEventListener("change", presentStill);

window.addEventListener("pagehide", () => {
  stillMotion.removeEventListener("change", presentStill);
  completePresentation();
});
