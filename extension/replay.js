// Demo mode: on a replay page, send the whole log once, then follow the turn on screen.
(async () => {
  const id = location.pathname.replace(/^\/+|\/+$/g, "").replace(/\.\w+$/, "");
  if (!id) return;
  const room = `replay-${id}`;
  const answer = await fetch(`${location.origin}/${id}.log`);
  if (!answer.ok) return;
  const lines = (await answer.text()).split("\n");
  chrome.runtime.sendMessage({type: "lines", room, lines, at: Date.now(), source: "replay"});

  let shown = null;
  setInterval(() => {
    const counter = [...document.querySelectorAll(".turn")]
      .map((element) => /Turn (\d+)/.exec(element.textContent))
      .find(Boolean);
    const turn = counter ? Number(counter[1]) : 1;
    if (turn !== shown) {
      shown = turn;
      chrome.runtime.sendMessage({type: "turn", room, turn, at: Date.now()});
    }
  }, 400);
})();
