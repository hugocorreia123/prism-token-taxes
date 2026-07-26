#!/usr/bin/env python3
"""Generate Prism's diagrams as SVG + PNG.

Geometry is computed rather than hand-placed, so nothing drifts out of
alignment when a label changes length. Run:  python docs/make_diagrams.py
"""
from pathlib import Path

import cairosvg

SLATE = ("#475569", "#F1F5F9")
TEAL = ("#0E7490", "#ECFEFF")
INDIGO = ("#4F46E5", "#EEF2FF")
AMBER = ("#B45309", "#FFFBEB")
GREEN = ("#047857", "#ECFDF5")
ROSE = ("#BE123C", "#FFF1F2")

INK, MUTED = "#0F172A", "#64748B"
FONT = "DejaVu Sans, Helvetica, Arial, sans-serif"

out = []


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size=14, fill=INK, weight="normal", anchor="middle",
         style="normal", spacing=None):
    sp = f' letter-spacing="{spacing}"' if spacing else ""
    out.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" '
               f'font-size="{size}" font-weight="{weight}" font-style="{style}" '
               f'fill="{fill}" text-anchor="{anchor}"{sp}>{esc(s)}</text>')


def _labels(cx, cy, lines):
    start = cy - (len(lines) - 1) * 8.5
    for i, (s, sub) in enumerate(lines):
        text(cx, start + i * 17 + 5, s, size=12 if sub else 13.5,
             fill=MUTED if sub else INK, weight="normal" if sub else "bold")


def panel(x, y, w, h, label, color):
    stroke, tint = color
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" '
               f'fill="{tint}" stroke="{stroke}" stroke-opacity="0.28" '
               f'stroke-width="1.5"/>')
    text(x + w / 2, y + 30, label.upper(), size=12.5, fill=stroke,
         weight="bold", spacing="1.6")


def box(x, y, w, h, lines, color, emphasis=False, note=None):
    stroke, tint = color
    out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
               f'fill="{tint if emphasis else "#FFFFFF"}" stroke="{stroke}" '
               f'stroke-width="{2.4 if emphasis else 1.7}"/>')
    _labels(x + w / 2, y + h / 2, lines)
    if note:
        text(x + w / 2, y + h + 20, note, size=11.5, fill=MUTED, style="italic")


def hexbox(x, y, w, h, lines, color, note=None):
    stroke, tint = color
    c = 22
    out.append(f'<polygon points="{x+c},{y} {x+w-c},{y} {x+w},{y+h/2} '
               f'{x+w-c},{y+h} {x+c},{y+h} {x},{y+h/2}" fill="{tint}" '
               f'stroke="{stroke}" stroke-width="2.6"/>')
    _labels(x + w / 2, y + h / 2, lines)
    if note:
        text(x + w / 2, y + h + 20, note, size=11.5, fill=MUTED, style="italic")


def store(x, y, w, h, lines, color, note=None):
    stroke, tint = color
    ry, rx = 9, w / 2
    out.append(f'<path d="M {x},{y+ry} L {x},{y+h-ry} A {rx},{ry} 0 0 0 '
               f'{x+w},{y+h-ry} L {x+w},{y+ry} Z" fill="{tint}" '
               f'stroke="{stroke}" stroke-width="1.9"/>')
    out.append(f'<ellipse cx="{x+rx}" cy="{y+ry}" rx="{rx}" ry="{ry}" '
               f'fill="#FFFFFF" stroke="{stroke}" stroke-width="1.9"/>')
    _labels(x + w / 2, y + h / 2 + 4, lines)
    if note:
        text(x + w / 2, y + h + 20, note, size=11.5, fill=MUTED, style="italic")


def arrow(x1, y1, x2, y2, color=MUTED, width=2.0, note=None, side="right"):
    out.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
               f'stroke="{color}" stroke-width="{width}" stroke-linecap="round" '
               f'marker-end="url(#head-{color.lstrip("#")})"/>')
    if note:
        dx = 14 if side == "right" else -14
        text(x1 + dx, (y1 + y2) / 2 + 4, note, size=11.5, fill=MUTED,
             style="italic", anchor="start" if side == "right" else "end")


def parrow(d, color=MUTED, width=2.2):
    out.append(f'<path d="{d}" fill="none" stroke="{color}" '
               f'stroke-width="{width}" stroke-linecap="round" '
               f'stroke-linejoin="round" '
               f'marker-end="url(#head-{color.lstrip("#")})"/>')


def header(w, h, title, subtitle):
    marks = []
    for c in {SLATE[0], TEAL[0], INDIGO[0], AMBER[0], GREEN[0], ROSE[0], MUTED}:
        marks.append(f'<marker id="head-{c.lstrip("#")}" viewBox="0 0 10 10" '
                     f'refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" '
                     f'orient="auto-start-reverse">'
                     f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{c}"/></marker>')
    out.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" '
               f'height="{h}" viewBox="0 0 {w} {h}">')
    out.append(f'<defs>{"".join(marks)}</defs>')
    out.append(f'<rect width="{w}" height="{h}" rx="18" fill="#FCFDFE" '
               f'stroke="#E2E8F0" stroke-width="2"/>')
    text(w / 2, 52, title, size=27, weight="bold")
    text(w / 2, 79, subtitle, size=14, fill=MUTED)


def save(name, w, h):
    out.append("</svg>")
    svg = Path(f"/home/claude/{name}.svg")
    svg.write_text("\n".join(out))
    cairosvg.svg2png(url=str(svg), write_to=f"/home/claude/{name}.png", scale=2.0)
    print(f"  {name}.svg + {name}.png  ({w}×{h})")


# ===================================================== diagram 1: pipeline
def build_pipeline():
    global out
    out = []
    W, H = 1660, 630
    header(W, H, "Prism — experimental pipeline",
           "every stage is a gate: nothing reaches the next box unverified, "
           "and nothing that fails the last one is reported as a saving")

    PY, PH = 108, 440
    TOP, BH, GAP = PY + 52, 76, 54
    cols = [
        dict(x=36, w=228, color=SLATE, label="Public datasets"),
        dict(x=320, w=300, color=TEAL, label="1 · Suite construction"),
        dict(x=676, w=300, color=INDIGO, label="2 · Execution"),
        dict(x=1032, w=300, color=AMBER, label="3 · Analysis"),
        dict(x=1388, w=236, color=SLATE, label="Verdict"),
    ]
    for c in cols:
        panel(c["x"], PY, c["w"], PH, c["label"], c["color"])

    span = BH * 3 + GAP * 2
    pair = BH * 2 + GAP
    y0 = TOP + (span - pair) / 2

    c = cols[0]
    box(c["x"] + 24, y0, c["w"] - 48, BH,
        [("GSM8K-hard", False), ("math + tool use", True)], SLATE)
    box(c["x"] + 24, y0 + BH + GAP, c["w"] - 48, BH,
        [("BFCL-v4", False), ("multi-turn agent", True)], SLATE)

    c = cols[1]
    bx, bw = c["x"] + 26, c["w"] - 52
    y = TOP
    box(bx, y, bw, BH, [("extract + derive", False),
                        ("ground truth from the", True),
                        ("dataset's own annotations", True)], TEAL)
    arrow(bx + bw / 2, y + BH + 6, bx + bw / 2, y + BH + GAP - 6)
    y += BH + GAP
    hexbox(bx, y, bw, BH, [("verify_suite", False),
                           ("independent re-derivation", True)], TEAL)
    arrow(bx + bw / 2, y + BH + 6, bx + bw / 2, y + BH + GAP - 6,
          note="29 of 69 rejected")
    y += BH + GAP
    store(bx, y, bw, BH, [("53 tasks", False), ("EN + PT", True)], TEAL)

    c = cols[2]
    bx, bw = c["x"] + 26, c["w"] - 52
    y = TOP
    box(bx, y, bw, BH, [("factorial expansion", False),
                        ("8 conditions × 2 seeds", True)], INDIGO)
    arrow(bx + bw / 2, y + BH + 6, bx + bw / 2, y + BH + GAP - 6)
    y += BH + GAP
    box(bx, y, bw, BH, [("harness", False),
                        ("tool schemas in-prompt,", True),
                        ("never native tool-calling", True)], INDIGO,
        emphasis=True)
    arrow(bx + bw / 2, y + BH + 6, bx + bw / 2, y + BH + GAP - 6,
          note="848 runs · 0 errors")
    y += BH + GAP
    store(bx, y, bw, BH, [("append-only JSONL", False),
                          ("+ hash-pinned manifest", True)], INDIGO)

    c = cols[3]
    bx, bw = c["x"] + 26, c["w"] - 52
    y = TOP
    box(bx, y, bw, BH, [("GLMs", False), ("tokens and accuracy", True)], AMBER)
    arrow(bx + bw / 2, y + BH + 6, bx + bw / 2, y + BH + GAP - 6)
    y += BH + GAP
    box(bx, y, bw, BH, [("cluster bootstrap", False),
                        ("resamples tasks, not rows", True),
                        ("BCa intervals", True)], AMBER)
    arrow(bx + bw / 2, y + BH + 6, bx + bw / 2, y + BH + GAP - 6)
    y += BH + GAP
    hexbox(bx, y, bw, BH, [("accuracy within 3pp?", False),
                           ("non-inferiority gate", True)], AMBER)
    text(bx + bw / 2, y + BH + 20, "3 of 4 arms in this study fail here",
         size=11.5, fill=MUTED, style="italic")

    c = cols[4]
    bx, bw = c["x"] + 24, c["w"] - 48
    box(bx, y0, bw, BH, [("claimable saving", False)], GREEN, emphasis=True)
    box(bx, y0 + BH + GAP, bw, BH, [("frontier point only", False),
                                    ("no efficiency claim", True)], ROSE,
        emphasis=True)

    mid = PY + PH / 2
    for a, b in zip(cols, cols[1:-1]):
        arrow(a["x"] + a["w"] + 9, mid, b["x"] - 9, mid, color=b["color"][0],
              width=3.0)

    gx = cols[3]["x"] + cols[3]["w"]
    py, fy = y0 + BH / 2, y0 + BH + GAP + BH / 2
    parrow(f"M {gx+9},{mid} H {gx+26} V {py} H {cols[4]['x']-9}", GREEN[0], 2.6)
    parrow(f"M {gx+9},{mid} H {gx+26} V {fy} H {cols[4]['x']-9}", ROSE[0], 2.6)
    text(gx + 31, py - 12, "pass", size=12, fill=GREEN[0], weight="bold",
         anchor="start")
    text(gx + 31, fy + 22, "fail", size=12, fill=ROSE[0], weight="bold",
         anchor="start")

    text(W / 2, H - 24,
         "ground truth is derived and independently re-verified, never "
         "hand-written  ·  the accuracy gate sits between the measurement "
         "and the claim", size=12.5, fill=MUTED, style="italic")
    save("prism_architecture", W, H)


# ===================================================== diagram 2: one run
def build_runloop():
    global out
    out = []
    W, H = 1420, 690
    header(W, H, "Inside a single run",
           "the Structure factor changes only the schemas in the first box; "
           "the Budget factor caps each reply. Everything else is held identical.")

    A = (50, 305, 250, 100)
    B = (380, 315, 180, 80)
    C = (640, 305, 230, 100)
    D = (615, 130, 280, 88)
    E = (615, 492, 280, 88)
    F = (960, 315, 160, 80)
    G = (1180, 315, 190, 80)

    box(*A, [("system prompt", False), ("+ tool schemas,", True),
             ("raw or compressed", True)], SLATE)
    box(*B, [("model reply", False)], INDIGO, emphasis=True)
    hexbox(*C, [("parse the reply", False)], INDIGO)
    box(*D, [("execute tool", False),
             ("calculator, lookup, or", True),
             ("filesystem simulator", True)], TEAL)
    box(*E, [("protocol_violation", False), ("logged, never corrected", True)],
        ROSE)
    box(*F, [("judge", False), ("value or state", True)], AMBER)
    store(*G, [("record outcome", False), ("+ every token", True)], AMBER)

    arrow(A[0] + A[2], 355, B[0] - 9, 355, width=2.4)
    arrow(B[0] + B[2], 355, C[0] - 9, 355, width=2.4)

    cx = C[0] + C[2] / 2
    arrow(cx, C[1] - 6, cx, D[1] + D[3] + 9, color=TEAL[0], width=2.4)
    text(cx + 14, (C[1] + D[1] + D[3]) / 2, "a tool call", size=12,
         fill=TEAL[0], weight="bold", anchor="start")
    arrow(cx, C[1] + C[3] + 6, cx, E[1] - 9, color=ROSE[0], width=2.4)
    text(cx + 14, (C[1] + C[3] + E[1]) / 2 + 4, "neither", size=12,
         fill=ROSE[0], weight="bold", anchor="start")
    arrow(C[0] + C[2] + 9, 355, F[0] - 9, 355, color=AMBER[0], width=2.4)
    text((C[0] + C[2] + F[0]) / 2, 343, "ANSWER:", size=12, fill=AMBER[0],
         weight="bold")
    arrow(F[0] + F[2], 355, G[0] - 9, 355, color=AMBER[0], width=2.4)

    bcx = B[0] + B[2] / 2
    top_y, bot_y = D[1] + D[3] / 2, E[1] + E[3] / 2
    parrow(f"M {D[0]-6},{top_y} H {bcx} V {B[1]-9}", TEAL[0], 2.4)
    text((D[0] + bcx) / 2 - 6, top_y - 13, "result appended, loop continues",
         size=11.5, fill=MUTED, style="italic")
    parrow(f"M {E[0]-6},{bot_y} H {bcx} V {B[1]+B[3]+9}", ROSE[0], 2.4)
    text((E[0] + bcx) / 2 - 6, bot_y + 22, "retried, never repaired",
         size=11.5, fill=MUTED, style="italic")

    text(W / 2, H - 24,
         "malformed replies are measured, not silently fixed — repairing them "
         "would hide the failure mode compression is suspected of causing",
         size=12.5, fill=MUTED, style="italic")
    save("prism_run_loop", W, H)


if __name__ == "__main__":
    build_pipeline()
    build_runloop()
