"""Display helpers shared by the memo writer and the desk."""

from __future__ import annotations


def money(value: float | None) -> str:
    if value is None:
        return "n/a"
    sign = "-" if value < 0 else ""
    return f"{sign}${abs(value):,.0f}"


def fmt_ratio(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    rounded = round(float(value), digits)
    if abs(rounded - round(rounded, 1)) < 1e-9:
        return f"{rounded:.1f}x"
    return f"{rounded:.{digits}f}x"


def fmt_pct(value: float | None, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    return f"{float(value) * 100:.{digits}f}%"


def fmt_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):,.{digits}f}"
