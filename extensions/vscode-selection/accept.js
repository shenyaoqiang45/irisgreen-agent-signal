function accept(value) {
  const text = String(value || "").replace(/[\u200b-\u200d\ufeff]/g, "").replace(/\s+/g, " ").trim();
  if (!text || text.length > 140) return "";
  if ((text.match(/[.?!](?:\s|$)/g) || []).length > 1) return "";
  if (/[\u3400-\u9fff]/.test(text)) return "";
  const words = text.match(/[A-Za-z]+(?:'[A-Za-z]+)?/g) || [];
  if (!words.length || words.length > 24) return "";
  const letters = words.reduce((sum, word) => sum + word.length, 0);
  if (letters / text.replace(/\s/g, "").length < 0.55) return "";
  return text;
}

module.exports = {accept};
