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
    watchOpenedMedia();
  }, 1200);

  let selectionTimer = 0;
  let gesture = "";
  const remember = () => {
    const text = selectedPhrase();
    if (text) gesture = text;
  };
  const publish = () => {
    const text = selectedPhrase() || gesture;
    gesture = "";
    if (!text) return;
    chrome.runtime.sendMessage({type: "selection", text}).catch(() => {});
  };
  const settle = () => {
    clearTimeout(selectionTimer);
    selectionTimer = setTimeout(publish, 320);
  };
  // Capture phase: X stops the bubble, and a timeline redraw often clears the
  // selection before a deferred read. Keep the text from the moment it existed.
  document.addEventListener("selectionchange", () => {
    remember();
    settle();
  }, true);
  document.addEventListener("click", event => {
    const img = event.target.closest && event.target.closest("img");
    if (!img) return;
    const box = img.getBoundingClientRect();
    if (box.width < 80 || box.height < 80) return;
    const hint = produceHint(img);
    if (!hint) return;
    chrome.runtime.sendMessage({type: "produce", hint}).catch(() => {});
  }, true);
  for (const event of ["pointerup", "mouseup"]) {
    document.addEventListener(event, () => {
      remember();
      if (!gesture) return;
      clearTimeout(selectionTimer);
      publish();
    }, true);
  }

  let mediaKey = "";
  const watchOpenedMedia = () => {
    const host = location.hostname.replace(/^www\./, "");
    const opened = (host === "x.com" || host === "twitter.com")
      && /\/status\/\d+\/photo\/\d+/.test(location.pathname);
    if (!opened) {
      if (!mediaKey) return;
      mediaKey = "";
      chrome.runtime.sendMessage({type: "media-clear"}).catch(() => {});
      return;
    }
    const img = largestTwimg();
    const src = img && enlarge(img.currentSrc || img.src);
    if (!src || src === mediaKey) return;
    mediaKey = src;
    chrome.runtime.sendMessage({type: "media", src}).catch(() => {});
  };
}

function largestTwimg() {
  const candidates = [...document.querySelectorAll("img")].filter(img => {
    const src = img.currentSrc || img.src || "";
    if (!/twimg\.com/.test(src)) return false;
    const box = img.getBoundingClientRect();
    return box.width >= 120 && box.height >= 120;
  });
  candidates.sort((a, b) => b.clientWidth * b.clientHeight - a.clientWidth * a.clientHeight);
  return candidates[0] || null;
}

function enlarge(src) {
  if (!src) return "";
  try {
    const url = new URL(src, location.href);
    if (url.hostname.endsWith("twimg.com") && url.pathname.includes("/media/")) {
      url.searchParams.set("name", "medium");
    }
    return url.href;
  } catch {
    return src;
  }
}

function produceHint(img) {
  const bits = [img.alt, img.title, img.getAttribute("aria-label")];
  const caption = img.closest("figure") && img.closest("figure").querySelector("figcaption");
  if (caption) bits.push(caption.innerText);
  try {
    const url = new URL(img.currentSrc || img.src || "", location.href);
    bits.push(decodeURIComponent(url.pathname).replace(/[\\/_.-]+/g, " "));
  } catch { /* an unnamed picture has nothing to look up */ }
  return bits.filter(Boolean).join(" ").replace(/\s+/g, " ").trim().slice(0, 300);
}

function selectedPhrase() {
  const active = document.activeElement;
  if (active && active.tagName === "INPUT" && active.type === "password") return "";
  const text = String(window.getSelection() || "")
    .replace(/[\u200b-\u200d\ufeff]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  if (!text || text.length > 140) return "";
  if ((text.match(/(?:[。！？]|[.?!](?:\s|$))/g) || []).length > 1) return "";
  if (!/\p{L}/u.test(text)) return "";
  if (text.split(/\s+/).length > 24) return "";
  return text;
}
