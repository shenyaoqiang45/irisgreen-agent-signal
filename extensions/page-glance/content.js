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

  let selectionTimer = 0;
  const sendSelection = () => {
    const text = selectedEnglish();
    if (!text) return;
    chrome.runtime.sendMessage({type: "selection", text}).catch(() => {});
  };
  document.addEventListener("selectionchange", () => {
    clearTimeout(selectionTimer);
    selectionTimer = setTimeout(sendSelection, 280);
  });
  document.addEventListener("mouseup", () => {
    clearTimeout(selectionTimer);
    sendSelection();
  });
}

function selectedEnglish() {
  const active = document.activeElement;
  if (active && active.tagName === "INPUT" && active.type === "password") return "";
  const text = String(window.getSelection() || "")
    .replace(/[\u200b-\u200d\ufeff]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text || text.length > 140) return "";
  if ((text.match(/[.?!](?:\s|$)/g) || []).length > 1) return "";
  if (/[\u3400-\u9fff]/.test(text)) return "";
  const words = text.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || [];
  if (!words.length || words.length > 24) return "";
  const letters = words.reduce((sum, word) => sum + word.length, 0);
  if (letters / text.replace(/\s/g, "").length < 0.55) return "";
  return text;
}
