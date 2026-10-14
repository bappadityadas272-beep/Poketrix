// The side panel: shows what the local server advises for the battle in the active tab.
const SERVER = "http://127.0.0.1:8765";
const advice = document.getElementById("advice");
const mode = document.getElementById("mode");
const timing = document.getElementById("timing");

function element(tag, text, className) {
  const made = document.createElement(tag);
  if (text !== undefined) made.textContent = text;
  if (className) made.className = className;
  return made;
}

function section(title, items) {
  const box = document.createDocumentFragment();
  box.append(element("h2", title));
  const list = element("ol");
  for (const item of items) list.append(element("li", item));
  box.append(list);
  return box;
}

function render(shown, state) {
  advice.replaceChildren();
  mode.textContent = "";
  if (shown.status !== "ok") {
    advice.append(element("p", shown.message, shown.status === "rated" ? "off" : "quiet"));
    return;
  }
  mode.textContent = `Gen ${shown.generation} · turn ${shown.turn} · ${shown.mode}`;
  const top = element("div", undefined, "box");
  top.append(element("h1", shown.headline), element("div", shown.explanation));
  advice.append(top);
  advice.append(section("Top options", shown.options.map((option) =>
    `${option.label}: ${option.detail}` +
    (option.score === null ? " (not scored)" : ` · score ${option.score.toFixed(3)}`))));
  if (shown.sets.length) {
    advice.append(section(`${shown.theirs}: likeliest sets`, shown.sets.map((set) =>
      `${set.probability} ${set.moves.join(", ")}${set.item ? " @ " + set.item : ""}`)));
  }
  if (shown.threat) advice.append(element("h2", "Threat"), element("div", shown.threat));
  advice.append(element("h2", "Opponent tendency (ladder players; not used by the advice)"),
                element("div", shown.tendency.replace(/^Opponent tendency: /, "")));
  const since = state && state.at ? ` · shown ${Date.now() - state.at} ms after the line arrived` : "";
  timing.textContent = `Engine ${shown.engine_ms} ms${since}`;
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  return tab ? tab.id : undefined;
}

async function refresh(state) {
  const tabId = await activeTab();
  state = state || await chrome.runtime.sendMessage({type: "state", tabId});
  if (!state || !state.room) return;
  const query = new URLSearchParams({room: state.room});
  if (state.turn !== undefined && state.turn !== null) query.set("turn", state.turn);
  try {
    const answer = await fetch(`${SERVER}/advice?${query}`);
    render(await answer.json(), state);
  } catch {
    render({status: "offline", message: "The Poketrix server is not running: python -m poketrix serve"});
  }
}

chrome.runtime.onMessage.addListener(async (message) => {
  if (message.type === "offline") {
    render({status: "offline", message: "The Poketrix server is not running: python -m poketrix serve"});
  } else if (message.type === "update" && message.tabId === await activeTab()) {
    refresh(message);
  }
});
chrome.tabs.onActivated.addListener(() => refresh());
refresh();
