"""Draw the credit schema: primary keys, uniqueness, and foreign keys.

Writes 10_schedule_and_deploy/credit-etl-keys.gif. Every primary key is unique.
There are no extra UNIQUE constraints beyond those primary keys.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "10_schedule_and_deploy" / "credit-etl-keys.gif"

W, H = 2000, 1480
BG = (246, 248, 250)
WHITE = (255, 255, 255)
INK = (23, 32, 42)
MUTED = (84, 96, 109)
LINE = (148, 163, 184)
PK = (154, 52, 18)
FK = (30, 64, 175)
CARD_EDGE = (203, 213, 225)

INPUT = (29, 78, 216)
TRANSFORM = (180, 83, 9)
OUTPUT = (21, 128, 61)
CONTROL = (71, 85, 105)
VIEW = (91, 33, 182)


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "segoeuib.ttf" if bold else "segoeui.ttf"
    return ImageFont.truetype(f"C:/Windows/Fonts/{name}", size)


TITLE = font(28, True)
HEAD = font(18, True)
BODY = font(15)
SMALL = font(13)
LEGEND = font(15, True)


def card(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], title: str, lines: list[tuple[str, str]], accent: tuple[int, int, int]) -> None:
    x, y, w, h = box
    draw.rounded_rectangle((x, y, x + w, y + h), radius=10, fill=WHITE, outline=CARD_EDGE, width=2)
    draw.rectangle((x, y, x + 8, y + h), fill=accent)
    draw.text((x + 22, y + 12), title, font=HEAD, fill=INK)
    yy = y + 42
    for kind, text in lines:
        color = PK if kind == "pk" else FK if kind == "fk" else MUTED
        draw.text((x + 22, yy), text, font=BODY, fill=color)
        yy += 22


def arrow(draw: ImageDraw.ImageDraw, points: list[tuple[int, int]], color: tuple[int, int, int] = FK) -> None:
    draw.line(points, fill=color, width=2)
    x1, y1 = points[-2]
    x2, y2 = points[-1]
    angle = math.atan2(y2 - y1, x2 - x1)
    length = 10
    for turn in (2.6, -2.6):
        draw.line(
            [
                (x2, y2),
                (x2 - length * math.cos(angle + turn), y2 - length * math.sin(angle + turn)),
            ],
            fill=color,
            width=2,
        )


def label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    draw.text(xy, text, font=SMALL, fill=FK)


def render() -> Image.Image:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.text((40, 24), "credit database  ·  credit schema  ·  primary keys, unique keys, relationships", font=TITLE, fill=INK)
    draw.rounded_rectangle((40, 68, 1840, 108), radius=8, fill=WHITE, outline=CARD_EDGE)
    draw.rectangle((52, 82, 72, 94), fill=PK)
    draw.text((80, 76), "PK unique", font=LEGEND, fill=PK)
    draw.rectangle((210, 82, 248, 86), fill=FK)
    draw.text((258, 76), "FK relationship", font=LEGEND, fill=FK)
    draw.text((460, 76), "Every 15 min: Desktop\\credit-inbox  →  input tables  →  score  →  decision tables. Pickup stored in schedule_capture.", font=BODY, fill=MUTED)

    schema = (40, 128, 460, 100)
    load = (770, 128, 460, 118)
    deployment = (1500, 128, 440, 100)
    loan = (770, 310, 460, 112)
    financial = (40, 500, 440, 136)
    bureau = (520, 500, 440, 136)
    bank = (1040, 500, 440, 136)
    market = (1520, 500, 440, 136)
    feature = (770, 720, 460, 140)
    decision = (770, 940, 460, 180)
    checks = (40, 1200, 600, 136)
    evidence = (700, 1200, 600, 136)
    audit = (1360, 1200, 600, 136)
    view = (40, 1368, 1920, 84)

    loan_bottom = loan[1] + loan[3]
    arrow(draw, [(financial[0] + 220, financial[1]), (financial[0] + 220, 468), (loan[0] + 50, 468), (loan[0] + 50, loan_bottom)])
    arrow(draw, [(bureau[0] + 220, bureau[1]), (bureau[0] + 220, 478), (loan[0] + 160, 478), (loan[0] + 160, loan_bottom)])
    arrow(draw, [(bank[0] + 220, bank[1]), (bank[0] + 220, 478), (loan[0] + 300, 478), (loan[0] + 300, loan_bottom)])
    arrow(draw, [(market[0] + 220, market[1]), (market[0] + 220, 468), (loan[0] + 410, 468), (loan[0] + 410, loan_bottom)])
    arrow(draw, [(1000, feature[1]), (1000, 660), (loan[0] + 230, 660), (loan[0] + 230, loan_bottom)])
    label(draw, (1010, 680), "FK application_id")

    gutter = 1984
    arrow(
        draw,
        [
            (feature[0] + feature[2], feature[1] + 36),
            (gutter, feature[1] + 36),
            (gutter, deployment[1] + deployment[3]),
            (deployment[0] + deployment[2] - 20, deployment[1] + deployment[3]),
        ],
    )
    label(draw, (1688, 690), "FK deployment_id → deployment")

    arrow(draw, [(decision[0] + 230, decision[1]), (feature[0] + 230, feature[1] + feature[3])])
    label(draw, (1010, 880), "FK run_id → feature_record")

    arrow(draw, [(decision[0], decision[1] + 70), (18, decision[1] + 70), (18, loan[1] + 56), (loan[0], loan[1] + 56)])
    label(draw, (28, 336), "FK application_id → loan_application")

    arrow(
        draw,
        [
            (decision[0] + decision[2], decision[1] + 100),
            (gutter, decision[1] + 100),
            (gutter, deployment[1] + deployment[3]),
            (deployment[0] + deployment[2] - 20, deployment[1] + deployment[3]),
        ],
    )
    label(draw, (1560, 900), "FK deployment_id → deployment")

    arrow(draw, [(checks[0] + 300, checks[1]), (decision[0] + 80, decision[1] + decision[3])])
    arrow(draw, [(evidence[0] + 300, evidence[1]), (decision[0] + 230, decision[1] + decision[3])])
    arrow(draw, [(audit[0] + 300, audit[1]), (decision[0] + 380, decision[1] + decision[3])])
    label(draw, (40, 1164), "FK run_id  →  decision.run_id    ON DELETE CASCADE")

    card(draw, schema, "schema_migration", [("pk", "PK unique   version"), ("note", "One row per applied SQL file")], CONTROL)
    card(draw, load, "input_load", [("pk", "PK unique   load_id"), ("note", "application_id is not unique"), ("note", "No foreign key on this log")], CONTROL)
    card(draw, deployment, "deployment", [("pk", "PK unique   deployment_id"), ("note", "Version stamp for each run")], CONTROL)
    card(
        draw,
        loan,
        "loan_application",
        [("pk", "PK unique   application_id"), ("note", "Parent of the source tables")],
        INPUT,
    )
    for box, title in (
        (financial, "financial_statement"),
        (bureau, "credit_bureau"),
        (bank, "bank_relationship"),
        (market, "market_observation"),
    ):
        card(
            draw,
            box,
            title,
            [
                ("pk", "PK unique   application_id"),
                ("fk", "FK application_id"),
                ("fk", "    → loan_application"),
                ("note", "ON DELETE CASCADE"),
            ],
            INPUT,
        )
    card(
        draw,
        feature,
        "feature_record",
        [
            ("pk", "PK unique   run_id"),
            ("fk", "FK application_id → loan_application"),
            ("fk", "FK deployment_id → deployment"),
        ],
        TRANSFORM,
    )
    card(
        draw,
        decision,
        "decision",
        [
            ("pk", "PK unique   run_id"),
            ("fk", "FK run_id → feature_record"),
            ("fk", "FK application_id → loan_application"),
            ("fk", "FK deployment_id → deployment"),
            ("note", "recommendation: APPROVE, REVIEW, REJECT"),
        ],
        OUTPUT,
    )
    card(
        draw,
        checks,
        "decision_check",
        [("pk", "PK unique   (run_id, check_order)"), ("fk", "FK run_id → decision"), ("note", "ON DELETE CASCADE")],
        OUTPUT,
    )
    card(
        draw,
        evidence,
        "decision_evidence",
        [("pk", "PK unique   (run_id, evidence_order)"), ("fk", "FK run_id → decision"), ("note", "ON DELETE CASCADE")],
        OUTPUT,
    )
    card(
        draw,
        audit,
        "decision_audit",
        [("pk", "PK unique   (run_id, step)"), ("fk", "FK run_id → decision"), ("note", "ON DELETE CASCADE")],
        OUTPUT,
    )
    card(
        draw,
        view,
        "latest_decision    view",
        [("note", "One row per application_id, read from decision. No primary key. application_id is unique inside this view.")],
        VIEW,
    )
    return image


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frame = render()
    frame.save(OUT, format="GIF", save_all=True, optimize=False, loop=0, duration=1000)
    print(OUT)


if __name__ == "__main__":
    main()
