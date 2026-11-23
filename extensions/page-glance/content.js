if (globalThis.__irisgreenWatch) {
  // A reload injects this file again. One watcher is enough.
} else {
  globalThis.__irisgreenWatch = true;
  const clock = /\b\d{1,2}:\d{2}(?::\d{2})?\b/g;
  let sent = "";
  let pending = "";
  let hits = 0;
  let timer = 0;

  const signature = () => {
    const text = ((document.body && document.body.innerText) || "").replace(clock, "");
    return `${location.href}\n${text.length}\n${text.slice(0, 160)}\n${text.slice(-320)}`;
  };

  const sample = () => {
    const next = signature();
    if (next === sent) {
      pending = "";
      hits = 0;
      return;
    }
    if (next !== pending) {
      pending = next;
      hits = 1;
      return;
    }
    hits += 1;
    if (hits < 2) return;
    sent = next;
    chrome.runtime.sendMessage({type: "page-changed"}).catch(() => {});
  };

  setInterval(() => {
    clearTimeout(timer);
    timer = setTimeout(sample, 400);
  }, 1200);
}
