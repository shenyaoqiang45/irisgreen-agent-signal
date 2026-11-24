const token = document.querySelector("#token");
const port = document.querySelector("#port");
const enabled = document.querySelector("#enabled");
const translate = document.querySelector("#translate");
const state = document.querySelector("#state");

const summary = document.querySelector("#summary");

function showSummary(saved) {
  summary.textContent = saved.lastMessage ? `${saved.lastTitle || ""}\n${saved.lastMessage}` : "";
}

chrome.storage.local.get(["token", "port", "enabled", "translate", "lastTitle", "lastMessage"]).then(saved => {
  token.value = saved.token || "";
  port.value = saved.port || 8171;
  enabled.checked = saved.enabled !== false;
  translate.checked = saved.translate !== false;
  showSummary(saved);
});

chrome.storage.onChanged.addListener(changes => {
  if (changes.lastMessage || changes.lastTitle) {
    chrome.storage.local.get(["lastTitle", "lastMessage"]).then(showSummary);
  }
});

document.querySelector("#save").addEventListener("click", async () => {
  const next = {
    token: token.value.trim(),
    port: Number(port.value) || 8171,
    enabled: enabled.checked,
    translate: translate.checked
  };
  await chrome.storage.local.set(next);
  state.textContent = next.token.length >= 24 ? "已保存" : "令牌至少 24 个字符";
});
