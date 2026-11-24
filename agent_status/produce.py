"""Name a clicked fruit or vegetable and project its calories."""

import re

from .protocol import envelope
from .receiver import Rejected

SESSION = "produce"
EXPRESSION = "produce"
HOLD_MS = 60000

# Kilocalories per 100 g, raw edible portion, rounded from USDA FoodData Central.
_CATALOG = (
    ("苹果", ("苹果", "apple"), 52),
    ("香蕉", ("香蕉", "banana"), 89),
    ("梨", ("梨", "pear"), 57),
    ("桃", ("桃", "peach"), 39),
    ("橙子", ("橙子", "柳橙", "orange"), 47),
    ("橘子", ("橘子", "桔子", "柑橘", "mandarin", "tangerine"), 53),
    ("柠檬", ("柠檬", "lemon"), 29),
    ("葡萄", ("葡萄", "grape"), 69),
    ("草莓", ("草莓", "strawberry"), 32),
    ("蓝莓", ("蓝莓", "blueberry"), 57),
    ("西瓜", ("西瓜", "watermelon"), 30),
    ("哈密瓜", ("哈密瓜", "cantaloupe"), 34),
    ("猕猴桃", ("猕猴桃", "奇异果", "kiwifruit", "kiwi"), 61),
    ("芒果", ("芒果", "mango"), 60),
    ("菠萝", ("菠萝", "凤梨", "pineapple"), 50),
    ("樱桃", ("樱桃", "车厘子", "cherry"), 63),
    ("荔枝", ("荔枝", "lychee", "litchi"), 66),
    ("柚子", ("柚子", "grapefruit", "pomelo"), 38),
    ("木瓜", ("木瓜", "papaya"), 43),
    ("牛油果", ("牛油果", "鳄梨", "avocado"), 160),
    ("番茄", ("番茄", "西红柿", "tomato"), 18),
    ("黄瓜", ("黄瓜", "cucumber"), 15),
    ("胡萝卜", ("胡萝卜", "carrot"), 41),
    ("白菜", ("白菜", "大白菜", "cabbage"), 17),
    ("菠菜", ("菠菜", "spinach"), 23),
    ("西兰花", ("西兰花", "青花菜", "broccoli"), 34),
    ("生菜", ("生菜", "lettuce"), 15),
    ("土豆", ("土豆", "马铃薯", "potato"), 77),
    ("红薯", ("红薯", "地瓜", "甘薯", "sweet potato"), 86),
    ("洋葱", ("洋葱", "onion"), 40),
    ("茄子", ("茄子", "eggplant", "aubergine"), 25),
    ("青椒", ("青椒", "彩椒", "柿子椒", "bell pepper"), 20),
    ("南瓜", ("南瓜", "pumpkin"), 26),
    ("冬瓜", ("冬瓜", "winter melon"), 13),
    ("芹菜", ("芹菜", "celery"), 14),
    ("玉米", ("玉米", "sweet corn", "corn"), 86),
)

_LATIN = re.compile(r"^[a-z][a-z ]*$")


def identify(hint):
    """Return (Chinese name, kcal per 100 g), or None when the hint is not produce."""
    text = re.sub(r"\s+", " ", hint or "").strip().lower()
    if not text:
        return None
    found = None
    length = 0
    for name, aliases, kcal in _CATALOG:
        for alias in aliases:
            if len(alias) <= length or not _contains(text, alias.lower()):
                continue
            found = (name, kcal)
            length = len(alias)
    return found


def project_produce(receiver, agent, body):
    if not isinstance(body, dict) or set(body) - {"hint"}:
        raise Rejected(400, "expected hint")
    hint = body.get("hint")
    if not isinstance(hint, str) or not hint.strip():
        raise Rejected(400, "expected hint")
    found = identify(hint)
    if found is None:
        return {"ok": True, "skipped": True}
    name, kcal = found
    payload = {"intent": "discovery", "expression_id": EXPRESSION,
               "title": name, "message": f"{kcal} 千卡/100克",
               "ttl_ms": HOLD_MS, "duration_ms": HOLD_MS}
    receipt = receiver.receive(envelope("agent.expression", agent, SESSION, payload), agent)
    return {"ok": True, "event_id": receipt["event_id"],
            "expression": {"title": payload["title"], "message": payload["message"]}}


def dismiss_produce(receiver, agent):
    try:
        receiver.receive(envelope(
            "agent.expression.clear", agent, SESSION, {"expression_id": EXPRESSION}), agent)
    except Rejected:
        return {"ok": True, "skipped": True}
    return {"ok": True, "cleared": True}


def _contains(text, alias):
    if _LATIN.fullmatch(alias):
        return re.search(rf"(?<![a-z]){re.escape(alias)}(?![a-z])", text) is not None
    return alias in text
