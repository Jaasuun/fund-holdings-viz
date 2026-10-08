"""中基协《公募基金市场数据》月报：近两年份额/净值汇总表。"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import pymupdf
import requests

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw" / "amac_monthly"
PROCESSED_DIR = ROOT / "data" / "processed"
LIST_BASE = "https://www.amac.org.cn/sjtj/tjbg/gmjj/"
NOTE = (
    "数据来源：中国证券投资基金业协会《公募基金市场数据》月报 PDF；"
    "含各类基金数量、份额（亿份）、净值（亿元）；默认展示近 24 个自然月。"
)
CATEGORY_ORDER = [
    "股票基金",
    "混合基金",
    "债券基金",
    "货币市场基金",
    "基金中基金",
    "其他基金",
    "其中：QDII基金",
    "封闭式基金",
    "开放式基金",
    "全部",
]
_CATEGORY_ALIAS = {
    "其中：股票基金": "股票基金",
    "其中：混合基金": "混合基金",
    "其中：债券基金": "债券基金",
    "其中：货币基金": "货币市场基金",
    "其中：货币市场基金": "货币市场基金",
    "其中：QDII基金": "其中：QDII基金",
    "合计": "全部",
}

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9",
}
_TITLE_RE = re.compile(r"公募基金市场数据[（(]\s*(\d{4})\s*年\s*(\d{1,2})\s*月\s*[)）]")
# 类别与数字之间须有空白（PDF 常分行），避免正文「净值合计39.63 万亿元」误匹配
_ROW_RE = re.compile(
    r"(封闭式基金|开放式基金|股票基金|债券基金|货币市场基金|混合基金|基金中基金|其他基金|"
    r"其中：股票基金|其中：混合基金|其中：债券基金|其中：货币基金|其中：货币市场基金|"
    r"其中：QDII\s*基金|合计|全部)"
    r"\s+(\d[\d,]*)\s+(\d[\d,]*(?:\.\d+)?)\s+(\d[\d,]*(?:\.\d+)?)"
)


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update(_HEADERS)
    return session


def _get_text(session: requests.Session, url: str) -> str:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return response.content.decode("utf-8", "replace")


def list_monthly_reports(session: requests.Session | None = None) -> list[dict]:
    """列出协会站点上的月报 PDF（去重，新→旧）。"""
    session = session or _session()
    pages = ["index.html", *[f"index_{i}.html" for i in range(1, 6)]]
    found: dict[str, dict] = {}
    for page in pages:
        url = urljoin(LIST_BASE, page)
        try:
            html = _get_text(session, url)
        except Exception as exc:  # noqa: BLE001
            print(f"  列表页失败 {page}: {exc}", flush=True)
            continue
        for match in re.finditer(
            r'<a[^>]+href=["\']([^"\']+\.pdf)["\'][^>]*>(.*?)</a>',
            html,
            flags=re.I | re.S,
        ):
            href, raw_title = match.group(1), match.group(2)
            title = re.sub(r"<[^>]+>", "", raw_title)
            title = re.sub(r"\s+", " ", title).strip()
            parsed = _TITLE_RE.search(title)
            if not parsed:
                continue
            year, month = int(parsed.group(1)), int(parsed.group(2))
            month_key = f"{year:04d}-{month:02d}"
            pdf_url = urljoin(url, href)
            # 同月保留先扫到的（列表页通常更新更靠前）
            found.setdefault(
                month_key,
                {
                    "month": month_key,
                    "year": year,
                    "month_num": month,
                    "title": f"公募基金市场数据（{year}年{month}月）",
                    "pdf_url": pdf_url,
                },
            )
        time.sleep(0.15)
    return [found[key] for key in sorted(found.keys(), reverse=True)]


def _to_float(text: str) -> float:
    return float(str(text).replace(",", "").replace(" ", ""))


def _normalize_category(name: str) -> str:
    compact = re.sub(r"\s+", "", name)
    return _CATEGORY_ALIAS.get(compact, compact)


def parse_monthly_pdf(pdf_bytes: bytes, month: str) -> dict:
    """从月报 PDF 解析当月各类份额/净值（取表中左侧当月三列）。

    兼容两类表头：
    - 新口径：股票/债券/货币/混合/FOF/其他/全部
    - 旧口径：封闭式/开放式/其中：股票…/合计
    """
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    text = "\n".join(page.get_text("text") for page in doc)
    doc.close()
    categories: dict[str, dict] = {}
    for match in _ROW_RE.finditer(text):
        category = _normalize_category(match.group(1))
        row = {
            "fund_count": int(_to_float(match.group(2))),
            "share_yi": round(_to_float(match.group(3)), 2),
            "nav_yi": round(_to_float(match.group(4)), 2),
        }
        prev = categories.get(category)
        # 同名多行时取数量更大的（表体优先于页眉/脚注残留）
        if prev is None or row["fund_count"] > prev["fund_count"]:
            categories[category] = row
    if "全部" not in categories:
        raise ValueError(f"{month} PDF 未解析到「全部/合计」行")
    if categories["全部"]["fund_count"] < 1000:
        raise ValueError(
            f"{month} 「全部」行异常：数量={categories['全部']['fund_count']}"
        )
    return {
        "month": month,
        "categories": categories,
        "total_share_yi": categories["全部"]["share_yi"],
        "total_nav_yi": categories["全部"]["nav_yi"],
        "total_fund_count": categories["全部"]["fund_count"],
    }


def _download_pdf(session: requests.Session, url: str, cache: Path, force: bool) -> bytes:
    if cache.is_file() and not force:
        return cache.read_bytes()
    response = session.get(url, timeout=90)
    response.raise_for_status()
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_bytes(response.content)
    return response.content


def run(
    *,
    months: int = 24,
    force: bool = False,
    xueqiu_out: Path | None = None,
) -> dict:
    session = _session()
    print(f"拉取中基协公募月报列表（近 {months} 个月）…", flush=True)
    reports = list_monthly_reports(session)
    if not reports:
        raise SystemExit("未从中基协站点解析到任何《公募基金市场数据》PDF")
    selected = reports[: max(1, months)]
    print(f"  列表共 {len(reports)} 期，本次取 {len(selected)} 期", flush=True)

    path: list[dict] = []
    for item in selected:
        month = item["month"]
        cache = RAW_DIR / f"amac_{month}.pdf"
        print(f"  {month} {item['pdf_url']}", flush=True)
        try:
            pdf_bytes = _download_pdf(session, item["pdf_url"], cache, force=force)
            parsed = parse_monthly_pdf(pdf_bytes, month)
        except Exception as exc:  # noqa: BLE001
            print(f"    失败：{exc}", flush=True)
            continue
        path.append(
            {
                "month": month,
                "label": month,
                "title": item["title"],
                "pdf_url": item["pdf_url"],
                "fund_count": parsed["total_fund_count"],
                "share_yi": parsed["total_share_yi"],
                "nav_yi": parsed["total_nav_yi"],
                "categories": parsed["categories"],
            }
        )
        time.sleep(0.2)

    if not path:
        raise SystemExit("月报均解析失败")

    path = sorted(path, key=lambda row: row["month"], reverse=True)
    latest = path[0]
    payload = {
        "source": "amac",
        "note": NOTE,
        "category_order": CATEGORY_ORDER,
        "months": months,
        "asof": latest["month"],
        "latest": {
            "month": latest["month"],
            "fund_count": latest["fund_count"],
            "share_yi": latest["share_yi"],
            "nav_yi": latest["nav_yi"],
            "categories": latest["categories"],
            "pdf_url": latest["pdf_url"],
        },
        "path": path,
        "pulled_at": datetime.now(timezone.utc).isoformat(),
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    local_path = PROCESSED_DIR / "amac_monthly_scale.json"
    local_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    print(f"已写入 {local_path}，{len(path)} 期，最新 {latest['month']}")
    if xueqiu_out:
        xueqiu_out = Path(xueqiu_out)
        xueqiu_out.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(local_path, xueqiu_out)
        print(f"已复制 {xueqiu_out}")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="拉取中基协公募基金市场数据月报")
    parser.add_argument("--months", type=int, default=24, help="近多少个月，默认 24")
    parser.add_argument("--force", action="store_true", help="忽略 PDF 缓存重下")
    parser.add_argument("--xueqiu-out", default=None, help="同步到雪球 processed 目录")
    args = parser.parse_args()
    today = date.today()
    print(f"今天 {today.isoformat()}")
    run(
        months=args.months,
        force=args.force,
        xueqiu_out=Path(args.xueqiu_out).expanduser() if args.xueqiu_out else None,
    )


if __name__ == "__main__":
    main()
