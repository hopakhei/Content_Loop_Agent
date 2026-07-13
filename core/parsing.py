"""Parse Claude's Loop 3 output into structured units, and map the human labels
in that output onto the Notion select/multi-select option values.

Expected per-unit format (from prompts/generate.txt):

    ---
    【編號】【Content Type】【Platform】
    Hook A（反共識）：...
    Hook B（數據衝擊）：...
    Hook C（懸念缺口）：...
    Post Body：...
    ---
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

_HEADER_RE = re.compile(r"【\s*(\d+)\s*】\s*【\s*([^】]*?)\s*】\s*【\s*([^】]*?)\s*】")
_TRAILING_SEPARATOR_RE = re.compile(r"\s*\n-{3,}\s*$")


@dataclass
class Unit:
    number: int
    content_type_label: str = ""
    platform_label: str = ""
    hooks: dict[str, str] = field(default_factory=dict)
    post_body: str = ""


def _extract_field(block: str, label: str, following: list[str]) -> str:
    """Text after `label：` up to the next known label (or end of block)."""
    stop = "|".join(re.escape(f) for f in following)
    lookahead = rf"(?=\n\s*(?:{stop})\b|\Z)" if stop else r"(?=\Z)"
    pattern = re.compile(rf"{re.escape(label)}[^\n:：]*[:：]\s*(.*?){lookahead}", re.S)
    m = pattern.search(block)
    return m.group(1).strip() if m else ""


def parse_units(text: str) -> list[Unit]:
    """Extract all units from Claude's response. Tolerant of the leading
    '論點地圖' section and of `---` separators."""
    matches = list(_HEADER_RE.finditer(text))
    units: list[Unit] = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        units.append(
            Unit(
                number=int(m.group(1)),
                content_type_label=m.group(2).strip(),
                platform_label=m.group(3).strip(),
                hooks={
                    "A": _extract_field(block, "Hook A", ["Hook B", "Hook C", "Post Body"]),
                    "B": _extract_field(block, "Hook B", ["Hook C", "Post Body"]),
                    "C": _extract_field(block, "Hook C", ["Post Body"]),
                },
                post_body=_strip_trailing_separator(_extract_field(block, "Post Body", [])),
            )
        )
    return units


def _strip_trailing_separator(text: str) -> str:
    """Remove the structural `---` line that closes a unit, while preserving any
    intra-thread `---` separators inside the body."""
    return _TRAILING_SEPARATOR_RE.sub("", text).strip()


def map_content_type(label: str) -> Optional[str]:
    """Human label -> Content Drafts `Content Type` select option."""
    l = label or ""
    if "Thread" in l:
        return "Thread"
    if "反共識" in l:
        return "反共識"
    if "數據" in l:
        return "數據衝擊"
    if "Quote" in l:
        return "Quote Card"
    if "故事" in l:
        return "故事貼"
    if "偽科學" in l or "反面教材" in l:
        return "偽科學拆解"
    if "金句" in l:
        return "金句裂變"
    if "下集" in l or "鈎子" in l or "鉤子" in l:
        return "下集鈎子"
    return None


def map_platforms(label: str) -> list[str]:
    """Human label -> Content Drafts `Platform` multi_select values."""
    l = label or ""
    if "全平台" in l:
        return ["X", "Threads"]
    has_threads = "Threads" in l or "threads" in l
    has_x = bool(re.search(r"\bX\b", l)) or "＋X" in l or "/ X" in l or "X +" in l or "X＋" in l
    platforms = []
    if has_x:
        platforms.append("X")
    if has_threads:
        platforms.append("Threads")
    return platforms or ["X", "Threads"]


# Issue # -> Content Drafts `Source Article` select option.
# 1xx = 分析流程 series; 2xx = build-in-public series.
SOURCE_ARTICLE_BY_ISSUE = {
    101: "101 - 前言",
    102: "102 - 北極星",
    103: "103 - 故事",
    104: "104 - 假設",
    105: "105 - 畫樹",
    106: "106 - 下注",
    107: "107 - 組合",
    201: "201 - Build in Public",
}


def map_source_article(issue_number) -> Optional[str]:
    try:
        return SOURCE_ARTICLE_BY_ISSUE.get(int(issue_number))
    except (TypeError, ValueError):
        return None
