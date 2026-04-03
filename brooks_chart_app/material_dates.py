"""提取 ES/Emini 相关资料里的高置信度日期索引。"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
import json
import re


REPO_DIR: Path = Path(__file__).resolve().parent.parent
KNOWLEDGE_ROOT: Path = REPO_DIR / "策略资料" / "al brooks参考资料agent专用版 "
CACHE_PATH: Path = REPO_DIR / ".vntrader" / "brooks_material_dates_es.json"
PAGE_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})/(\d{1,2})(?:/|\s*/\s*)(\d{2,4})(?!\d)")
ES_KEYWORD_RE = re.compile(r"Emini|ES\b|@ES|Globex|S&P cash index|S&P futures|Emini 5 min|Emini 1 min", re.I)
TITLE_RE = re.compile(r'^title:\s*"(?P<title>.+)"$', re.M)

# 这些页在 OCR 里只有月/日，但价格区间和 ES 历史能较高置信度反推出年份。
MANUAL_PAGE_DATE_OVERRIDES: dict[str, tuple[str, ...]] = {
    "Video 15H Breakouts突破/pages/page-0017.md": ("2016-12-13", "2016-12-14"),
    "Video 15H Breakouts突破/pages/page-0019.md": ("2017-04-20", "2017-04-21"),
}


@dataclass(frozen=True)
class MaterialDateRef:
    """单个资料页和日期的映射。"""

    date: str
    source: str
    title: str
    page_path: str
    confidence: str
    evidence: str


def normalize_year(year: int) -> int:
    """把两位年份统一映射到 2000 年以后。"""
    if year < 100:
        return 2000 + year
    return year


def infer_source_label(relative_path: Path) -> str:
    """按目录判断资料来源。"""
    top = relative_path.parts[0]
    if top.startswith("百科幻灯片"):
        return "百科"
    if top.startswith("Ali Flash Cards"):
        return "Ali"
    return "课程"


def extract_title(text: str, relative_path: Path) -> str:
    """优先用 frontmatter 里的 title。"""
    match = TITLE_RE.search(text)
    if match:
        return match.group("title")
    return relative_path.stem


def extract_full_dates(text: str) -> set[str]:
    """提取高置信度的完整日期。"""
    results: set[str] = set()
    for month_text, day_text, year_text in PAGE_DATE_RE.findall(text):
        month = int(month_text)
        day = int(day_text)
        year = normalize_year(int(year_text))
        if not (1 <= month <= 12 and 1 <= day <= 31 and 2000 <= year <= 2035):
            continue
        try:
            current = date(year, month, day)
        except ValueError:
            continue
        results.add(current.isoformat())
    return results


def build_material_date_refs() -> list[MaterialDateRef]:
    """扫描资料目录，建立 ES/Emini 高置信度日期索引。"""
    refs: list[MaterialDateRef] = []
    for page_path in KNOWLEDGE_ROOT.rglob("pages/*.md"):
        relative_path = page_path.relative_to(KNOWLEDGE_ROOT)
        text = page_path.read_text(encoding="utf-8", errors="ignore")
        if not ES_KEYWORD_RE.search(text) and str(relative_path).replace("\\", "/") not in MANUAL_PAGE_DATE_OVERRIDES:
            continue

        title = extract_title(text, relative_path)
        source = infer_source_label(relative_path)
        relative_key = str(relative_path).replace("\\", "/")

        for date_text in sorted(extract_full_dates(text)):
            refs.append(
                MaterialDateRef(
                    date=date_text,
                    source=source,
                    title=title,
                    page_path=str(page_path.resolve()),
                    confidence="高",
                    evidence="页面文本中存在完整日期",
                )
            )

        for date_text in MANUAL_PAGE_DATE_OVERRIDES.get(relative_key, ()):
            refs.append(
                MaterialDateRef(
                    date=date_text,
                    source=source,
                    title=title,
                    page_path=str(page_path.resolve()),
                    confidence="较高",
                    evidence="依据页内月日与 ES 价格区间手工反推年份",
                )
            )

    deduped: dict[tuple[str, str], MaterialDateRef] = {}
    for ref in refs:
        deduped[(ref.date, ref.page_path)] = ref
    return sorted(deduped.values(), key=lambda item: (item.date, item.source, item.title))


def load_material_date_refs(force_rebuild: bool = False) -> dict[str, list[MaterialDateRef]]:
    """读取或重建资料日期索引。"""
    if CACHE_PATH.exists() and not force_rebuild:
        payload = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        refs = [MaterialDateRef(**item) for item in payload]
    else:
        refs = build_material_date_refs()
        CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        CACHE_PATH.write_text(
            json.dumps([asdict(item) for item in refs], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    grouped: dict[str, list[MaterialDateRef]] = {}
    for ref in refs:
        grouped.setdefault(ref.date, []).append(ref)
    return grouped
