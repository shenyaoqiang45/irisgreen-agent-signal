const vscode = require("vscode");
const fs = require("fs");
const http = require("http");
const https = require("https");
const os = require("os");
const path = require("path");
const {accept} = require("./accept");

const glosses = new Map();
let generation = 0;
let posted = "";
let timer = 0;
let warned = false;

function activate(context) {
  context.subscriptions.push(vscode.window.onDidChangeTextEditorSelection(event => {
    clearTimeout(timer);
    const editor = event.textEditor;
    timer = setTimeout(() => translateEditor(editor), 280);
  }));
}

function deactivate() {}

async function translateEditor(editor) {
  const config = vscode.workspace.getConfiguration("irisgreen");
  if (config.get("translate") === false || !editor || editor.selection.isEmpty) return;
  const source = accept(editor.document.getText(editor.selection));
  if (!source || source === posted) return;
  const current = ++generation;
  const auth = credential(config);
  if (auth.token.length < 24) {
    if (!warned) {
      warned = true;
      vscode.window.setStatusBarMessage("IrisGreen 划词翻译缺少接收器令牌", 5000);
    }
    return;
  }
  let chinese = glosses.get(source);
  if (!chinese) {
    chinese = await fetchTranslation(source);
    if (current !== generation) return;
    if (chinese) {
      if (glosses.size > 200) glosses.clear();
      glosses.set(source, chinese);
    }
  }
  if (!chinese || current !== generation) return;
  const body = JSON.stringify({text: source, translation: chinese});
  const result = await request(`http://127.0.0.1:${auth.port}/api/v1/selection`, {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${auth.token}`,
      "Content-Type": "application/json",
      "Content-Length": Buffer.byteLength(body)
    },
    body
  });
  if (!result || !result.expression || current !== generation) return;
  posted = source;
}

function credential(config) {
  const port = Number(config.get("port")) || 8171;
  const configured = String(config.get("token") || "").trim();
  if (configured.length >= 24) return {token: configured, port};
  try {
    const file = path.join(os.homedir(), ".cursor", "irisgreen-status.json");
    const saved = JSON.parse(fs.readFileSync(file, "utf8"));
    if (typeof saved.token === "string" && saved.token.length >= 24) {
      return {token: saved.token, port: Number(saved.port) || port};
    }
  } catch { /* the setting can still supply the token */ }
  return {token: "", port};
}

async function fetchTranslation(text) {
  const edge = await request("https://edge.microsoft.com/translate/translatetext?to=zh-Hans", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify([text])
  });
  const hit = edge && edge[0];
  const detected = hit && hit.detectedLanguage && hit.detectedLanguage.language;
  if (detected && /^zh\b/i.test(detected)) return "";
  const line = hit && hit.translations && hit.translations[0] && hit.translations[0].text;
  if (line && String(line).trim()) return String(line).trim();
  const backup = await request(
    "https://api.mymemory.translated.net/get?langpair=autodetect|zh-CN&q=" + encodeURIComponent(text));
  const fallback = ((backup && backup.responseData && backup.responseData.translatedText) || "").trim();
  return fallback && fallback !== text ? fallback : "";
}

function request(url, options = {}) {
  return new Promise(resolve => {
    const lib = url.startsWith("https:") ? https : http;
    const headers = {...(options.headers || {})};
    if (options.body && !headers["Content-Length"]) {
      headers["Content-Length"] = Buffer.byteLength(options.body);
    }
    const req = lib.request(url, {method: options.method || "GET", headers, timeout: 4000}, res => {
      const chunks = [];
      res.on("data", chunk => chunks.push(chunk));
      res.on("end", () => {
        if (res.statusCode < 200 || res.statusCode >= 300) return resolve(null);
        try {
          resolve(JSON.parse(Buffer.concat(chunks).toString("utf8")));
        } catch {
          resolve(null);
        }
      });
    });
    req.on("error", () => resolve(null));
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
    if (options.body) req.write(options.body);
    req.end();
  });
}

module.exports = {activate, deactivate};
