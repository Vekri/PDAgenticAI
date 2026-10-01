"""Run the three sample files from a terminal: python -m app"""

from __future__ import annotations

import sys

from app.formatting import fmt_ratio
from app.orchestrator import run_decision
from app.samples import SAMPLE_CATALOG, get_sample


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    for item in SAMPLE_CATALOG:
        result = run_decision(get_sample(item["id"]), use_llm=False, persist=False)
        ratios = result.key_ratios
        grade = result.risk_grade or "n/a"
        print(f"{result.application['business_name']}: {result.recommendation}")
        print(
            f"  PD {result.pd_display} ({grade})  "
            f"Debt/EBITDA {fmt_ratio(ratios['debt_to_ebitda'])}  "
            f"DSCR {fmt_ratio(ratios['dscr'])}  "
            f"Score {ratios['credit_score']}"
        )
        for line in result.why:
            print(f"  - {line}")
        print()


if __name__ == "__main__":
    main()
