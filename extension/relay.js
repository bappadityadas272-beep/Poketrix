// Passes what page.js copied to the extension's background worker, unchanged and in order.
window.addEventListener("message", (event) => {
  if (event.source !== window || !event.data || event.data.poketrix !== true) return;
  const {room, lines, at} = event.data;
  chrome.runtime.sendMessage({type: "lines", room, lines, at, source: "live"});
});
