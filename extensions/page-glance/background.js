const SKIP = /^(chrome|edge|about|devtools|chrome-extension|view-source):/;
const timers = new Map();

chrome.runtime.onInstalled.addListener(() => {
  chrome.storage.local.set({enabled: true, port: 8171});
  watchOpenPages();
});
chrome.runtime.onStartup.addListener(watchOpenPages);
watchOpenPages();

for (const event of ["onCompleted", "onHistoryStateUpdated", "onReferenceFragmentUpdated"]) {
  chrome.webNavigation[event].addListener(details => schedule(details), {url: [{schemes: ["http", "https"]}]});
}
chrome.tabs.onActivated.addListener(({tabId}) => schedule({frameId: 0, tabId, url: "https://tab"}));
chrome.runtime.onMessage.addListener((message, sender) => {
  if (!message || message.type !== "page-changed" || !sender.tab || sender.tab.id == null) return;
  schedule({frameId: 0, tabId: sender.tab.id, url: sender.tab.url || "https://tab"});
});

async function watchOpenPages() {
  const tabs = await chrome.tabs.query({url: ["http://*/*", "https://*/*"]});
  for (const tab of tabs) {
    if (tab.id == null) continue;
    chrome.scripting.executeScript({target: {tabId: tab.id}, files: ["content.js"]}).catch(() => {});
  }
}

function schedule(details) {
  if (details.frameId !== 0 || SKIP.test(details.url)) return;
  clearTimeout(timers.get(details.tabId));
  timers.set(details.tabId, setTimeout(() => glance(details.tabId), 1200));
}

async function glance(tabId) {
  const tab = await chrome.tabs.get(tabId).catch(() => null);
  if (!tab || !tab.active || SKIP.test(tab.url || "")) return;
  const {enabled = true, token = "", port = 8171} = await chrome.storage.local.get(["enabled", "token", "port"]);
  if (!enabled || token.length < 24) return;
  let page;
  try {
    const [injected] = await chrome.scripting.executeScript({target: {tabId}, func: extract});
    page = injected && injected.result;
    if (!page || !page.text) return;
    const seen = await chrome.storage.session.get("last");
    const quiet = page.text.replace(/\b\d{1,2}:\d{2}(?::\d{2})?\b/g, "");
    const signature = `${page.url}\n${quiet.length}\n${quiet.slice(0, 180)}\n${quiet.slice(-320)}`;
    if (seen.last && seen.last.signature === signature) return;
    const response = await fetch(`http://127.0.0.1:${Number(port) || 8171}/api/v1/page/open`, {
      method: "POST",
      headers: {"Authorization": `Bearer ${token}`, "Content-Type": "application/json"},
      body: JSON.stringify(page)
    });
    const body = await response.json();
    if (!response.ok || !body.expression) return;
    await chrome.storage.session.set({last: {signature, at: Date.now()}});
    await chrome.storage.local.set({
      lastTitle: body.expression.title,
      lastMessage: body.expression.message
    });
  } catch {
    return;
  }
}

function extract() {
  const skip = /^(skip navigation|ask youtube|create|home|shorts|subscriptions|you|your channel|history|playlists|show more)$/i;
  const clean = (value) => (value || "")
    .replace(/[\u200b-\u200d\ufeff]/g, "")
    .replace(/^\(\d+\)\s*/, "")
    .replace(/^\d+\.\s*/, "")
    .replace(/\s+\d+\s+(?:hour|hours|minute|minutes|second|seconds).*$/i, "")
    .trim();
  const regions = [...document.querySelectorAll("article, main, [role=main], .markdown-card")]
    .filter(el => !el.closest("nav, aside, [role=navigation]"))
    .map(el => (el.innerText || "").trim())
    .filter(text => text.length >= 40);
  const body = (document.body && document.body.innerText) || "";
  const text = clean(regions.length ? regions[regions.length - 1] : body)
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .slice(0, 8000);
  const headings = [...document.querySelectorAll("h1")]
    .map(el => clean(el.innerText))
    .filter(item => item.length >= 2 && !skip.test(item));
  const labels = [...document.querySelectorAll(
    "ytd-rich-item-renderer a[aria-label], ytd-rich-grid-media a[aria-label], ytd-video-renderer a[aria-label]"
  )].map(el => clean(el.getAttribute("aria-label")))
    .filter(item => item.length >= 12 && !skip.test(item));
  const counts = new Map();
  for (const line of body.split(/\n/)) {
    const item = clean(line);
    if (item.length < 4 || item.length > 20 || skip.test(item)) continue;
    counts.set(item, (counts.get(item) || 0) + 1);
  }
  const repeated = [...counts.entries()].filter(([, count]) => count >= 2).map(([item]) => item);
  const title = headings[0] || labels[0] || repeated[repeated.length - 1] || clean(document.title) || document.title || "";
  return {url: location.href, title, text};
}
