"""A/C 等份额与主产品的对应关系。同一主基金的不同份额持仓相同。"""

from __future__ import annotations

import re

_CURRENCY_SUFFIX = re.compile(
    r"(?:\((?:人民币|美元|欧元|港币)\)|人民币|美元|欧元|港币)\s*$"
)
_CLASS_SUFFIX = re.compile(
    r"(?:(?<=[\u4e00-\u9fff])|(?<=[)\）]))[ABCDEHIY]类?$"
)

# 选代表份额时优先 A，无字母份额次之（常是老份额），再按规模。
_CLASS_PRIORITY = {"A": 0, "": 1, "C": 2}


def split_share_class(name: str) -> tuple[str, str]:
    """Return (product_name, share_class). share_class is '' when unnamed."""
    text = str(name).strip()
    text = _CURRENCY_SUFFIX.sub("", text).strip()
    match = _CLASS_SUFFIX.search(text)
    if not match:
        return text, ""
    share_class = match.group(0).replace("类", "")
    product_name = text[: match.start()].strip()
    return product_name, share_class


def class_rank(share_class: str) -> int:
    return _CLASS_PRIORITY.get(share_class, 9)
