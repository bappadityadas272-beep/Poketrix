// Runs in the Showdown client's own page. It only listens: every message the server sends
// over the client's socket is copied, in arrival order, to relay.js. Nothing is ever sent.
(() => {
  const Native = window.WebSocket;
  function forward(data) {
    if (typeof data !== "string") return;
    // A SockJS frame holds a JSON array of messages ("a[...]"); a plain socket sends one.
    let messages = [data];
    if (data.startsWith("a[")) {
      try { messages = JSON.parse(data.slice(1)); } catch { return; }
    }
    const at = Date.now();
    for (const message of messages) {
      const lines = message.split("\n");
      if (!lines[0].startsWith(">battle-")) continue;
      window.postMessage({poketrix: true, room: lines[0].slice(1), lines: lines.slice(1), at}, "*");
    }
  }
  function Listening(...args) {
    const socket = new Native(...args);
    socket.addEventListener("message", (event) => forward(event.data));
    return socket;
  }
  Listening.prototype = Native.prototype;
  Object.assign(Listening, {CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3});
  window.WebSocket = Listening;
})();
