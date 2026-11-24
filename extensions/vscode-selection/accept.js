function accept(value) {
  const text = String(value || "").replace(/[\u200b-\u200d\ufeff]/g, "").replace(/\s+/g, " ").trim();
  if (!text || text.length > 140) return "";
  if ((text.match(/(?:[。！？]|[.?!](?:\s|$))/g) || []).length > 1) return "";
  if (!/\p{L}/u.test(text)) return "";
  if (text.split(/\s+/).length > 24) return "";
  return text;
}

module.exports = {accept};
