// Forwards lines to the local server, one room at a time and in order, and tells the panel
// when there is something new to show. It never talks to Showdown.
const SERVER = "http://127.0.0.1:8765";
const tabs = new Map();  // tab id -> {room, turn, at}
const queues = new Map();  // room -> the promise of its last post

chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true});

function notify(tabId) {
  chrome.runtime.sendMessage({type: "update", tabId, ...tabs.get(tabId)}).catch(() => {});
}

chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message.type === "state") {
    reply(tabs.get(message.tabId) || null);
    return;
  }
  const tabId = sender.tab && sender.tab.id;
  if (tabId === undefined) return;
  if (message.type === "turn") {
    tabs.set(tabId, {...tabs.get(tabId), room: message.room, turn: message.turn, at: message.at});
    notify(tabId);
    return;
  }
  if (message.type === "lines") {
    const previous = queues.get(message.room) || Promise.resolve();
    const posted = previous.then(() => fetch(`${SERVER}/line`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({room: message.room, lines: message.lines, source: message.source}),
    })).then(() => {
      const known = tabs.get(tabId) || {};
      const turn = message.source === "replay" ? known.turn : undefined;
      tabs.set(tabId, {room: message.room, turn, at: message.at});
      notify(tabId);
    }).catch(() => chrome.runtime.sendMessage({type: "offline"}).catch(() => {}));
    queues.set(message.room, posted);
  }
});

chrome.tabs.onRemoved.addListener((tabId) => tabs.delete(tabId));
