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
  if (!message || !sender.tab || sender.tab.id == null) return;
  if (message.type === "page-changed") {
    schedule({frameId: 0, tabId: sender.tab.id, url: sender.tab.url || "https://tab"});
  } else if (message.type === "selection") {
    translateSelection(message.text, sender.tab.id);
  }
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

const glosses = new Map();
let selectionGeneration = 0;
let inflightSelection = "";

async function translateSelection(text, tabId) {
  const source = String(text || "").replace(/\s+/g, " ").trim();
  if (!source || source === inflightSelection) return;
  const generation = ++selectionGeneration;
  inflightSelection = source;
  try {
    const tab = await chrome.tabs.get(tabId).catch(() => null);
    if (!tab || !tab.active || generation !== selectionGeneration) return;
    const settings = await chrome.storage.local.get(["translate", "token", "port"]);
    if (settings.translate === false || (settings.token || "").length < 24) return;
    let chinese = glosses.get(source);
    if (!chinese) {
      chinese = await fetchTranslation(source);
      if (chinese && glosses.size > 200) glosses.clear();
      if (chinese) glosses.set(source, chinese);
    }
    if (!chinese || generation !== selectionGeneration) return;
    const current = await chrome.tabs.get(tabId).catch(() => null);
    if (!current || !current.active) return;
    const response = await fetch(`http://127.0.0.1:${Number(settings.port) || 8171}/api/v1/selection`, {
      method: "POST",
      headers: {"Authorization": `Bearer ${settings.token}`, "Content-Type": "application/json"},
      body: JSON.stringify({text: source, translation: chinese})
    });
    const body = await response.json();
    if (!response.ok || !body.expression || generation !== selectionGeneration) return;
    await chrome.storage.local.set({
      lastTitle: body.expression.title,
      lastMessage: body.expression.message
    });
  } catch {
    return;
  } finally {
    if (inflightSelection === source) inflightSelection = "";
  }
}

async function fetchTranslation(text) {
  const edge = await requestTranslation(
    "https://edge.microsoft.com/translate/translatetext?from=en&to=zh-Hans",
    {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify([text])});
  const line = edge && edge[0] && edge[0].translations && edge[0].translations[0] && edge[0].translations[0].text;
  if (line && line.trim()) return line.trim();
  const backup = await requestTranslation(
    "https://api.mymemory.translated.net/get?langpair=en|zh-CN&q=" + encodeURIComponent(text));
  return ((backup && backup.responseData && backup.responseData.translatedText) || "").trim();
}

async function requestTranslation(url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 4000);
  try {
    const response = await fetch(url, {...(options || {}), signal: controller.signal});
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
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
  const readText = (root) => {
    if (!root) return "";
    const copy = root.cloneNode(true);
    copy.querySelectorAll("nav, aside, footer, [role=navigation], [role=contentinfo]").forEach(node => node.remove());
    const holder = document.createElement("div");
    holder.style.cssText = "position:fixed;left:-10000px;top:0;width:800px;visibility:hidden";
    holder.appendChild(copy);
    document.documentElement.appendChild(holder);
    const value = copy.innerText || copy.textContent || "";
    holder.remove();
    return value;
  };
  const hidden = "nav, aside, footer, [role=navigation], [role=contentinfo]";
  const cards = [...document.querySelectorAll(".markdown-card")]
    .filter(el => !el.closest(hidden));
  const mains = [...document.querySelectorAll("article, main, [role=main]")]
    .filter(el => !el.closest(hidden));
  const source = cards.length ? cards[cards.length - 1] : mains[0];
  const body = readText(source || document.body);
  const text = clean(body)
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
