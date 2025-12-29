from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TopicCategory:
    key: str
    label: str


CATEGORIES: list[TopicCategory] = [
    TopicCategory(key="economy", label="経済・財政"),
    TopicCategory(key="welfare", label="社会保障・子育て"),
    TopicCategory(key="security", label="外交・安全保障"),
    TopicCategory(key="rights", label="人権・多様性"),
    TopicCategory(key="digital", label="デジタル・行政改革"),
    TopicCategory(key="other", label="その他"),
]


EXPLICIT_TOPIC_TO_CATEGORY: dict[str, str] = {
    # ここは運用で必要に応じて追記（topic_id -> category key）
}


def categorize_topic(*, topic_id: str, topic_name: str | None) -> TopicCategory:
    tid = (topic_id or "").strip()
    name = (topic_name or "").strip()
    key = EXPLICIT_TOPIC_TO_CATEGORY.get(tid)
    if key:
        return next((c for c in CATEGORIES if c.key == key), CATEGORIES[-1])

    text = f"{tid} {name}".lower()

    # economy / finance
    if any(k in text for k in ["財政", "税", "消費税", "賃金", "物価", "成長", "産業", "経済", "金融", "最低賃金"]):
        return next(c for c in CATEGORIES if c.key == "economy")
    # welfare / education / child
    if any(k in text for k in ["社会保障", "年金", "医療", "介護", "子育て", "教育", "奨学", "保育"]):
        return next(c for c in CATEGORIES if c.key == "welfare")
    # security / foreign
    if any(k in text for k in ["安全保障", "防衛", "外交", "自衛隊", "反撃", "日米", "中国", "北朝鮮"]):
        return next(c for c in CATEGORIES if c.key == "security")
    # rights / diversity / immigration
    if any(k in text for k in ["人権", "ジェンダー", "夫婦別姓", "lgbt", "同性", "移民", "難民", "入管", "表現"]):
        return next(c for c in CATEGORIES if c.key == "rights")
    # digital / gov / ai
    if any(k in text for k in ["デジタル", "行政", "規制改革", "ai", "人工知能", "dx", "マイナン"]):
        return next(c for c in CATEGORIES if c.key == "digital")

    return next(c for c in CATEGORIES if c.key == "other")
