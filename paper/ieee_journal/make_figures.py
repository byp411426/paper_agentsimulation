#!/usr/bin/env python3
"""Generate the three DisasterSociety core figures as editable SVG.

Figures follow docs/DisasterSociety_论文图片设计需求.md exactly:
  fig1 = motivated running example (3-stage household story)
  fig2 = DisasterSociety system architecture (static map)
  fig3 = social-process method mechanism (dynamic loop + state contracts)

Output: SVG sources + figures/manifest.json with SHA-256. PNG/PDF previews are
produced separately (Chrome headless) and recorded back into the manifest.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("/Users/linnuo/tmp/disastersociety/paper/ieee_journal/figures")
OUT.mkdir(parents=True, exist_ok=True)

WIDTH_IN = 7.16  # IEEE two-column figure width

# Colorblind-safe palette. Every color is also double-encoded by shape /
# label / line style, so the figure does not rely on color alone.
C = {
    "blue": "#2166AC", "blue_f": "#DCE7F3",
    "orange": "#D9720A", "orange_f": "#FBE7D0",
    "purple": "#7B3294", "purple_f": "#EBDCF0",
    "gray": "#383838", "gray_f": "#EDEDED",
    "green": "#1B7837", "green_f": "#DCEEE1",
    "red": "#B2182B", "red_f": "#F3D6D9",
    "ink": "#1F1F1F", "muted": "#5F5F5F",
    "line": "#8A8A8A", "white": "#FFFFFF",
}

FONT = "Helvetica, Arial, sans-serif"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _markers() -> str:
    m = []
    for name, col in [
        ("ink", C["ink"]), ("blue", C["blue"]), ("orange", C["orange"]),
        ("purple", C["purple"]), ("gray", C["gray"]), ("green", C["green"]),
        ("red", C["red"]), ("line", C["line"]),
    ]:
        m.append(
            f'<marker id="arr-{name}" viewBox="0 0 10 10" refX="8.5" refY="5" '
            f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{col}"/></marker>'
        )
    return "\n".join(m)


def svg_head(w: int, h: int) -> str:
    h_in = round(WIDTH_IN * h / w, 4)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" '
        f'width="{WIDTH_IN}in" height="{h_in}in" '
        f'font-family="{FONT}" fill="{C["ink"]}" '
        f'font-variant-numeric="tabular-nums">\n'
        f"<defs>\n{_markers()}\n</defs>\n"
    )


def txt(x, y, s, size=24, anchor="middle", color="ink", weight="normal",
        style="normal", spacing=None, opacity=1.0):
    extra = f' letter-spacing="{spacing}"' if spacing else ""
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" text-anchor="{anchor}" '
        f'fill="{C[color]}" font-weight="{weight}" font-style="{style}" '
        f'opacity="{opacity}"{extra}>{esc(s)}</text>'
    )


def line(x1, y1, x2, y2, color="ink", width=2, dash=None, marker=None):
    attrs = [f'x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}"', f'stroke="{C[color]}"',
             f'stroke-width="{width}"', 'stroke-linecap="round"']
    if dash:
        attrs.append(f'stroke-dasharray="{dash}"')
    if marker:
        attrs.append(f'marker-end="url(#arr-{marker})"')
    return f'<line {" ".join(attrs)}/>'


def poly(points, color="ink", width=2, dash=None, marker=None, fill="none"):
    pts = " ".join(f"{x},{y}" for x, y in points)
    attrs = [f'points="{pts}"', f'fill="{fill}"', f'stroke="{C[color]}"',
             f'stroke-width="{width}"', 'stroke-linejoin="round"',
             'stroke-linecap="round"']
    if dash:
        attrs.append(f'stroke-dasharray="{dash}"')
    if marker:
        attrs.append(f'marker-end="url(#arr-{marker})"')
    return f'<polyline {" ".join(attrs)}/>'


def box(x, y, w, h, fill="white", stroke="ink", sw=2, rx=10, dash=None):
    attrs = [f'x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"',
             f'fill="{C[fill]}"', f'stroke="{C[stroke]}"', f'stroke-width="{sw}"']
    if dash:
        attrs.append(f'stroke-dasharray="{dash}"')
    return f'<rect {" ".join(attrs)}/>'


def circle(cx, cy, r, fill="white", stroke="ink", sw=2, dash=None):
    attrs = [f'cx="{cx}" cy="{cy}" r="{r}"', f'fill="{C[fill]}"',
             f'stroke="{C[stroke]}"', f'stroke-width="{sw}"']
    if dash:
        attrs.append(f'stroke-dasharray="{dash}"')
    return f'<circle {" ".join(attrs)}/>'


def group(s: str) -> str:
    return f'<g>\n{s}\n</g>'


def person(cx, cy, s=1.0, color="blue", fill="blue_f", sw=2):
    """Simple vector person: head + shoulders. Height ~ 58*s units."""
    r = 11 * s
    hy = cy - 20 * s
    body = box(cx - 16 * s, cy, 32 * s, 32 * s, fill=fill, stroke=color,
               sw=sw, rx=14 * s)
    head = circle(cx, hy, r, fill=fill, stroke=color, sw=sw)
    return group(body + "\n" + head)


def vehicle(cx, cy, s=1.0, color="orange", fill="orange_f", sw=2):
    """Simple side-view vehicle: body + cabin + two wheels."""
    bw, bh = 88 * s, 28 * s
    x = cx - bw / 2
    y = cy - bh / 2
    body = box(x, y, bw, bh, fill=fill, stroke=color, sw=sw, rx=8 * s)
    cabin = box(cx - 8 * s, y - 16 * s, 34 * s, 18 * s, fill=fill,
                stroke=color, sw=sw, rx=6 * s)
    w1 = circle(cx - 26 * s, cy + bh / 2, 9 * s, fill="white", stroke=color, sw=sw)
    w2 = circle(cx + 26 * s, cy + bh / 2, 9 * s, fill="white", stroke=color, sw=sw)
    return group(body + "\n" + cabin + "\n" + w1 + "\n" + w2)


def bubble(cx, cy, w, h, text, color="purple", fill="purple_f", tail=(-20, 24),
           tsize=22, weight="normal"):
    x, y = cx - w / 2, cy - h / 2
    tail_x, tail_y = x + w / 2 + tail[0], y + h / 2 + tail[1]
    tri = f'<polygon points="{x+w/2-16},{y+h/2-2} {x+w/2+8},{y+h/2-2} {tail_x},{tail_y}" fill="{C[fill]}" stroke="{C[color]}" stroke-width="2" stroke-linejoin="round"/>'
    r = box(x, y, w, h, fill=fill, stroke=color, sw=2, rx=12)
    t = txt(cx, cy + tsize * 0.34, text, size=tsize, color=color, weight=weight)
    return group(r + "\n" + tri + "\n" + t)


def route_strip(x, y, w, state="open", alternate=False, s=1.0):
    """Bottom map strip: hazard (left) -> main route -> destination (right)."""
    h = 86 * s
    r = box(x, y, w, h, fill="gray_f", stroke="gray", sw=2, rx=10)
    # hazard (left)
    hx, hy = x + 42 * s, y + h / 2
    hazard = (
        f'<polygon points="{hx},{hy-24*s} {hx+24*s},{hy-10*s} {hx+20*s},{hy+20*s} '
        f'{hx-20*s},{hy+20*s} {hx-24*s},{hy-10*s}" fill="{C["red_f"]}" '
        f'stroke="{C["red"]}" stroke-width="2" stroke-linejoin="round"/>'
        + "\n" + txt(hx, hy + 5 * s, "!", size=24 * s, color="red", weight="bold")
    )
    # destination (right)
    dx = x + w - 34 * s
    home = (
        f'<polygon points="{dx-16*s},{hy+18*s} {dx},{hy-14*s} {dx+16*s},{hy+18*s}" '
        f'fill="none" stroke="{C["gray"]}" stroke-width="2" stroke-linejoin="round"/>'
        + "\n" + txt(dx, hy - 22 * s, "safety", size=20 * s, color="gray")
    )
    # main route
    my = hy
    if state == "open":
        road = line(hx + 34 * s, my, dx - 34 * s, my, color="green", width=5,
                    marker="green")
        road_lbl = txt((hx + dx) / 2, my - 10 * s, "main route (open)",
                       size=20 * s, color="green")
    else:
        road = line(hx + 34 * s, my, dx - 34 * s, my, color="gray", width=5)
        # closure marker
        cx2 = (hx + dx) / 2
        barrier = (
            line(cx2 - 12 * s, my - 18 * s, cx2 + 12 * s, my + 18 * s, color="red",
                 width=4)
            + "\n" + line(cx2 - 12 * s, my + 18 * s, cx2 + 12 * s, my - 18 * s,
                          color="red", width=4)
            + "\n" + txt(cx2 + 26 * s, my - 14 * s, "CLOSED", size=20 * s,
                         color="red", weight="bold", anchor="start")
        )
        road_lbl = ""
        # alternate route arcing below
        if alternate:
            ay = my + 26 * s
            alt = poly([(hx + 40 * s, my), (hx + 70 * s, ay),
                        (dx - 70 * s, ay), (dx - 40 * s, my)],
                       color="green", width=4, dash="8,5", marker="green")
            alt_lbl = txt((hx + dx) / 2, ay + 24 * s, "alternate route",
                          size=20 * s, color="green")
        else:
            alt = alt_lbl = ""
        road = road + "\n" + barrier + "\n" + alt
        road_lbl += alt_lbl
    return group(r + "\n" + hazard + "\n" + home + "\n" + road + "\n" + road_lbl)


def _panel_label(x, y, text, color="ink"):
    return txt(x, y, text, size=26, anchor="start", color=color, weight="bold")


# ---------------------------------------------------------------------------
# Figure 1: motivated running example (3-stage household story)
# ---------------------------------------------------------------------------
def fig1() -> str:
    w, h = 1440, 600
    s = [svg_head(w, h)]

    PW, PH = 440, 568  # panel width, height

    def panel(px, title, title_color):
        s.append(box(px, 16, PW, PH, fill="white", stroke="line", sw=2, rx=14))
        s.append(_panel_label(px + 22, 56, title, title_color))

    def family(px):
        """Two decision adults + one dependent member + one shared vehicle."""
        out = []
        # adult A
        out.append(person(px + 110, 148, s=1.0, color="blue", fill="blue_f"))
        out.append(txt(px + 110, 204, "Resident A", size=22, color="blue"))
        # adult B
        out.append(person(px + 230, 148, s=1.0, color="blue", fill="blue_f"))
        out.append(txt(px + 230, 204, "Resident B", size=22, color="blue"))
        # dependent member
        out.append(person(px + 355, 150, s=0.8, color="muted", fill="gray_f"))
        out.append(txt(px + 355, 202, "dependent", size=19, color="muted"))
        out.append(txt(px + 355, 222, "member (care)", size=18, color="muted"))
        # shared vehicle
        out.append(vehicle(px + 180, 268, s=0.92))
        out.append(txt(px + 180, 312, "shared vehicle", size=20, color="orange"))
        return "\n".join(out)

    # ---- Panel A: asymmetric warning exposure -----------------------------
    panel(20, "A  Asymmetric warning exposure", "purple")
    a = []
    a.append(bubble(20 + 110, 88, 190, 52, "official warning", color="purple",
                    fill="purple_f", tail=(0, 28)))
    a.append(bubble(20 + 230, 88, 150, 52, "no warning yet", color="gray",
                    fill="gray_f", tail=(0, 28)))
    a.append(family(20))
    a.append(route_strip(20 + 30, 340, 380, state="open", s=1.0))
    a.append(txt(20 + 220, 474, "A is exposed; B is not yet informed",
                 size=21, color="muted"))
    s.append("\n".join(a))

    # ---- Panel B: household coordination ----------------------------------
    panel(500, "B  Household coordination", "orange")
    b = []
    b.append(bubble(500 + 110, 88, 170, 52, "leave? when?", color="purple",
                    fill="purple_f", tail=(0, 28)))
    b.append(bubble(500 + 230, 88, 150, 52, "car + care?", color="purple",
                    fill="purple_f", tail=(0, 28)))
    b.append(family(500))
    # negotiation connectors (bubble bottom -> plan card top)
    b.append(line(500 + 110, 118, 500 + 180, 356, color="purple", width=2, dash="5,4"))
    b.append(line(500 + 230, 118, 500 + 260, 356, color="purple", width=2, dash="5,4"))
    # household plan card (orange)
    b.append(box(500 + 60, 362, 320, 128, fill="orange_f", stroke="orange",
                 sw=2.5, rx=12))
    b.append(txt(500 + 220, 392, "Household plan", size=23, color="orange",
                 weight="bold"))
    b.append(txt(500 + 220, 420, "route · vehicle · companions · time",
                 size=17, color="ink"))
    b.append(txt(500 + 220, 448, "formed by negotiation", size=17, color="muted"))
    b.append(txt(500 + 220, 474, "not a single mind", size=16, color="muted"))
    s.append("\n".join(b))

    # ---- Panel C: disruption, feedback, adaptation ------------------------
    panel(980, "C  Disruption, feedback, adaptation", "red")
    c = []
    c.append(family(980))
    # world state: main route closed, alternate route appears
    c.append(route_strip(980 + 30, 330, 380, state="closed", alternate=True, s=1.0))
    # red execution feedback arrow back to the household plan
    c.append(txt(980 + 220, 444, "execution feedback", size=19, color="red",
                 weight="bold"))
    c.append(line(980 + 220, 452, 980 + 220, 478, color="red", width=3, marker="red"))
    # updated plan card (green) with constraint check
    c.append(box(980 + 60, 486, 320, 90, fill="green_f", stroke="green",
                 sw=2.5, rx=12))
    c.append(txt(980 + 220, 516, "Updated plan", size=22, color="green",
                 weight="bold"))
    c.append(txt(980 + 220, 542, "alternate route · same companions", size=18,
                 color="ink"))
    c.append(txt(980 + 220, 564, "✓ passed constraint check", size=19,
                 color="green", weight="bold"))
    s.append("\n".join(c))

    # time arrows between panels
    for x1, x2 in ((460, 500), (940, 980)):
        s.append(line(x1, 300, x2, 300, color="line", width=3, marker="line"))

    s.append("</svg>")
    return "\n".join(s)


# ---------------------------------------------------------------------------
# Figure 2: DisasterSociety system architecture
# ---------------------------------------------------------------------------
def fig2() -> str:
    w, h = 1500, 780
    s = [svg_head(w, h)]
    # outer boundary
    s.append(box(16, 16, 1468, 748, fill="white", stroke="gray", sw=2.5,
                 rx=16, dash="10,6"))
    s.append(txt(38, 52, "DisasterSociety", size=30, color="gray",
                 weight="bold", anchor="start"))

    def zone(x, y, ww, hh, title, tcolor, tfill, items):
        s.append(box(x, y, ww, hh, fill=tfill, stroke=tcolor, sw=2, rx=12))
        s.append(txt(x + ww / 2, y + 34, title, size=25, color=tcolor,
                     weight="bold"))
        return items

    # ---- Zone A: input -----------------------------------------------------
    ax = 34
    s.append(box(ax, 76, 300, 640, fill="gray_f", stroke="line", sw=2, rx=12))
    s.append(txt(ax + 150, 106, "A  Inputs", size=24, color="gray", weight="bold"))
    items_a = [
        ("EventPack manifest", "time-indexed events"),
        ("Population & whole-household donors", "members, vehicles, income"),
        ("Warning / hazard / road / resource events", "dynamic scenario"),
        ("Case-specific adapters", "Carr-informed controlled case"),
    ]
    yy = 130
    for title, sub in items_a:
        s.append(box(ax + 16, yy, 268, 118, fill="white", stroke="gray",
                     sw=2, rx=10))
        s.append(txt(ax + 150, yy + 44, title, size=21, color="ink",
                     weight="bold"))
        s.append(txt(ax + 150, yy + 74, sub, size=18, color="muted"))
        yy += 136

    # ---- Zone B: resident & household social state -------------------------
    bx = 360
    s.append(box(bx, 76, 460, 640, fill="white", stroke="line", sw=2, rx=12))
    s.append(txt(bx + 230, 106, "B  Resident & household social state",
                 size=24, color="ink", weight="bold"))
    # Resident boxes (3)
    rx_x = bx + 20
    for i, (nm, priv) in enumerate([
        ("Resident i", "private cognition and decision"),
        ("Resident j", "private cognition and decision"),
        ("Resident k", "private cognition and decision"),
    ]):
        rxx = rx_x + i * 108
        s.append(box(rxx, 128, 100, 180, fill="blue_f", stroke="blue", sw=2, rx=10))
        s.append(circle(rxx + 50, 168, 16, fill="blue_f", stroke="blue", sw=2))
        s.append(txt(rxx + 50, 208, nm, size=19, color="blue", weight="bold"))
        s.append(txt(rxx + 50, 232, "private", size=16, color="blue"))
        s.append(txt(rxx + 50, 252, "cognition", size=16, color="blue"))
        s.append(txt(rxx + 50, 272, "& decision", size=16, color="blue"))
    # Household box (does not fully enclose residents)
    s.append(box(bx + 20, 330, 420, 150, fill="orange_f", stroke="orange",
                 sw=2.5, rx=12))
    s.append(txt(bx + 230, 362, "Household", size=24, color="orange",
                 weight="bold"))
    s.append(txt(bx + 230, 392, "members  ·  vehicles  ·  care responsibilities",
                 size=19, color="ink"))
    s.append(txt(bx + 230, 418, "commitments", size=19, color="ink"))
    s.append(txt(bx + 230, 446, "shared constraints, not one shared mind",
                 size=17, color="muted"))
    # membership connectors
    for i in range(3):
        s.append(line(rx_x + i * 108 + 50, 308, bx + 230, 330, color="orange",
                      width=2, dash="4,4"))
    # Interaction box
    s.append(box(bx + 20, 510, 420, 130, fill="purple_f", stroke="purple",
                 sw=2.5, rx=12))
    s.append(txt(bx + 230, 546, "Interaction", size=24, color="purple",
                 weight="bold"))
    s.append(txt(bx + 230, 580, "message exchange and coordination",
                 size=20, color="ink"))
    s.append(txt(bx + 230, 610, "warning · household DM · community",
                 size=17, color="muted"))

    # ---- Zone C: kernel & shared world -------------------------------------
    cx = 850
    s.append(box(cx, 76, 340, 640, fill="white", stroke="line", sw=2, rx=12))
    s.append(txt(cx + 170, 106, "C  Runtime & shared world", size=24,
                 color="gray", weight="bold"))
    # Engine
    s.append(box(cx + 20, 130, 300, 150, fill="green_f", stroke="green",
                 sw=2.5, rx=12))
    s.append(txt(cx + 170, 170, "Event-driven Engine", size=24, color="green",
                 weight="bold"))
    s.append(txt(cx + 170, 204, "simulation kernel", size=20, color="ink"))
    s.append(txt(cx + 170, 234, "multi-step decision loop", size=17, color="muted"))
    # World
    s.append(box(cx + 20, 320, 300, 330, fill="gray_f", stroke="gray",
                 sw=2.5, rx=12))
    s.append(txt(cx + 170, 356, "World", size=24, color="gray", weight="bold"))
    for i, it in enumerate([
        "hazard state", "roads & closures", "locations",
        "vehicle / resource state", "action arbitration",
    ]):
        s.append(txt(cx + 170, 392 + i * 34, it, size=19, color="ink"))
    # bidirectional arrows Engine <-> World
    s.append(line(cx + 170, 280, cx + 170, 320, color="gray", width=2.5,
                  marker="gray"))
    s.append(line(cx + 196, 320, cx + 196, 280, color="gray", width=2.5,
                  marker="gray"))

    # ---- Zone D: evidence output ------------------------------------------
    dx = 1220
    s.append(box(dx, 76, 246, 640, fill="white", stroke="line", sw=2, rx=12))
    s.append(txt(dx + 123, 106, "D  Evidence", size=24, color="ink",
                 weight="bold"))
    ev_items = [
        "trajectory snapshots",
        "message & commitment records",
        "intent & execution outcomes",
        "model calls · tokens · cost",
        "failure / fallback",
        "config · data · code hashes",
        "run terminal status",
    ]
    yy = 130
    for it in ev_items:
        s.append(box(dx + 14, yy, 218, 62, fill="white", stroke="ink", sw=1.8,
                     rx=8))
        s.append(txt(dx + 123, yy + 37, it, size=18, color="ink"))
        yy += 76

    # ---- labeled arrows ----------------------------------------------------
    # EventPack -> Engine
    s.append(line(ax + 150, 216, cx + 20, 205, color="green", width=2.5,
                  marker="green"))
    s.append(txt((ax + 150 + cx + 20) / 2, 190, "time-indexed events",
                 size=17, color="green"))
    # Engine <-> Resident/Interaction
    s.append(line(cx + 20, 245, bx + 440, 200, color="blue", width=2.5,
                  marker="blue"))
    s.append(txt((cx + 20 + bx + 440) / 2, 226,
                 "decision & communication interface", size=17, color="blue"))
    s.append(line(bx + 440, 560, cx + 20, 520, color="purple", width=2.5,
                  marker="purple"))
    # World <-> Engine already drawn; label
    s.append(txt(cx + 230, 302, "state & execution\ninterface", size=16,
                 color="gray", anchor="start"))
    # all major components -> evidence
    s.append(line(bx + 440, 370, dx + 14, 300, color="ink", width=2, dash="5,4",
                  marker="ink"))
    s.append(line(cx + 320, 400, dx + 14, 380, color="ink", width=2, dash="5,4",
                  marker="ink"))
    s.append(txt((cx + 320 + dx + 14) / 2, 368, "trace records", size=17,
                 color="muted"))

    s.append("</svg>")
    return "\n".join(s)


# ---------------------------------------------------------------------------
# Figure 3: method mechanism loop + state contracts
# ---------------------------------------------------------------------------
def fig3() -> str:
    w, h = 1500, 920
    s = [svg_head(w, h)]

    # ---- upper: 6-stage loop ----------------------------------------------
    stages = [
        ("1  Dynamic events &\nlimited observation", "gray", "gray_f",
         ["EventPack / World emit", "warning · hazard · road", "events; Interaction emits",
          "social messages. Resident", "sees only channel / location /",
          "access-conditioned facts."], False),
        ("2  Memory", "blue", "blue_f",
         ["only processed info enters", "private memory; retrieve by",
          "recency, importance and", "relevance for the current step."], True),
        ("3  Feedback &\nbelief update", "red", "red_f",
         ["local observation + prior", "execution result revise route",
          "belief; World state is NOT", "auto-synced to every resident."], True),
        ("4  Planning", "green", "green_f",
         ["structured plan: route,", "vehicle, companions, departure",
          "time. Plan is intent only —", "no physical state change yet."], True),
        ("5  Interaction &\nhousehold commitment", "purple", "purple_f",
         ["send proposal / response;", "membership, vehicle, route, time",
          "checks form a versioned", "commitment; history preserved."], True),
        ("6  World arbitration\n& execution", "gray", "gray_f",
         ["batch-resolve all intents on", "one shared snapshot; check road,",
          "vehicle capacity, member", "location, care, time. Only",
          "executed changes state;", "rejected(reason) returns."], False),
    ]
    bw, bh, gap = 224, 250, 22
    x0 = 20
    y0 = 76
    centers = []
    for i, (title, col, fill, lines, toggle) in enumerate(stages):
        x = x0 + i * (bw + gap)
        s.append(box(x, y0, bw, bh, fill=fill, stroke=col, sw=2.5, rx=12))
        s.append(txt(x + bw / 2, y0 + 42, title, size=23, color=col,
                     weight="bold"))
        yy = y0 + 78
        for ln in lines:
            s.append(txt(x + bw / 2, yy, ln, size=17, color="ink"))
            yy += 24
        # toggle symbol for the four mechanisms (Memory/Feedback/Planning/Interaction)
        if toggle:
            s.append(circle(x + bw - 22, y0 + 22, 11, fill="white", stroke=col, sw=2))
            s.append(line(x + bw - 22, y0 + 12, x + bw - 22, y0 + 32,
                          color=col, width=3))
            s.append(txt(x + bw - 40, y0 - 6, "on/off", size=13, color="muted"))
        centers.append((x + bw / 2, y0 + bh / 2))

    # arrows between stages with labels
    edge_labels = [
        ("observable context", "blue", False),
        ("retrieved memory", "blue", False),
        ("updated cognition", "blue", False),
        ("structured plan / intent", "green", False),
        ("commitment-constrained intent", "purple", False),
    ]
    for i, (lab, col, _) in enumerate(edge_labels):
        x1 = centers[i][0] + bw / 2
        x2 = centers[i + 1][0] - bw / 2
        s.append(line(x1, centers[i][1], x2, centers[i + 1][1], color=col,
                      width=2.5, marker=col))
        s.append(txt((x1 + x2) / 2, centers[i][1] - 14, lab, size=15, color=col))
    # return arrow: stage 6 -> stage 1 (bend underneath)
    ry = y0 + bh + 60
    c6, c1 = centers[5], centers[0]
    s.append(poly([(c6[0], c6[1] + bh / 2), (c6[0], ry), (c1[0], ry),
                   (c1[0], c1[1] + bh / 2)], color="red", width=2.5,
                  marker="red"))
    s.append(txt((c6[0] + c1[0]) / 2, ry - 14, "execution outcome / feedback",
                 size=17, color="red"))

    # ---- lower: two state contracts ---------------------------------------
    # Band 1: message & commitment
    b1_y = 460
    s.append(txt(34, b1_y - 12, "Message and commitment",
                 size=22, color="purple", weight="bold", anchor="start"))
    steps1 = [("sent", "purple", "purple_f"), ("delivered", "purple", "purple_f"),
              ("processed", "purple", "purple_f"), ("accepted / rejected", "orange", "orange_f"),
              ("feasible commitment", "orange", "orange_f")]
    sx, sw, sh = 34, 260, 64
    for i, (lab, col, fill) in enumerate(steps1):
        x = sx + i * (sw + 22)
        s.append(box(x, b1_y, sw, sh, fill=fill, stroke=col, sw=2.2, rx=10))
        s.append(txt(x + sw / 2, b1_y + sh / 2 + 7, lab, size=19, color=col,
                     weight="bold"))
        if i < len(steps1) - 1:
            s.append(line(x + sw, b1_y + sh / 2, x + sw + 22, b1_y + sh / 2,
                          color=col, width=2.2, marker=col))

    # Band 2: action & world state
    b2_y = 600
    s.append(txt(34, b2_y - 12, "Action and world state",
                 size=22, color="gray", weight="bold", anchor="start"))
    steps2 = [("intention", "gray", "gray_f"),
              ("batched resolution", "gray", "gray_f"),
              ("executed / rejected", "green", "green_f"),
              ("state update / feedback", "gray", "gray_f")]
    for i, (lab, col, fill) in enumerate(steps2):
        x = sx + i * (sw + 22)
        s.append(box(x, b2_y, sw, sh, fill=fill, stroke=col, sw=2.2, rx=10))
        s.append(txt(x + sw / 2, b2_y + sh / 2 + 7, lab, size=19, color=col,
                     weight="bold"))
        if i < len(steps2) - 1:
            s.append(line(x + sw, b2_y + sh / 2, x + sw + 22, b2_y + sh / 2,
                          color=col, width=2.2, marker=col))

    # ---- dashed connectors: contracts <-> loop -----------------------------
    # processed (step1 idx 2) -> Memory (stage 2)
    p1 = (sx + 2 * (sw + 22) + sw / 2, b1_y)
    s.append(poly([p1, (centers[1][0], b1_y - 20), (centers[1][0], y0 + bh)],
                  color="blue", width=2, dash="6,5", marker="blue"))
    # feasible commitment (step1 idx 4) -> Planning/Intent (stage 4)
    p2 = (sx + 4 * (sw + 22) + sw / 2, b1_y)
    s.append(poly([p2, (centers[4][0] - 30, b1_y - 30), (centers[4][0] - 30, y0 + bh)],
                  color="orange", width=2, dash="6,5", marker="orange"))
    # rejected -> Feedback (stage 3)
    p3 = (sx + 2 * (sw + 22) + sw / 2, b2_y + sh)
    s.append(poly([p3, (centers[2][0] + 20, b2_y + sh + 50), (centers[2][0] + 20, y0 + bh)],
                  color="red", width=2, dash="6,5", marker="red"))

    # ---- small legend ------------------------------------------------------
    lg_y = 820
    s.append(txt(34, lg_y, "Mechanism color", size=18, color="muted",
                 anchor="start"))
    legend = [("Memory", "blue"), ("Feedback", "red"), ("Planning", "green"),
              ("Interaction / message", "purple"), ("Household commitment", "orange"),
              ("World / physical", "gray")]
    lx = 34
    for lab, col in legend:
        s.append(circle(lx + 8, lg_y + 18, 9, fill=col, stroke=col, sw=1))
        s.append(txt(lx + 24, lg_y + 25, lab, size=17, color="ink",
                     anchor="start"))
        lx += 170

    s.append("</svg>")
    return "\n".join(s)


def main() -> None:
    figures = [
        ("fig1_household_response.svg", fig1(),
         "Fig. 1 — Dynamic disaster household response (running example)"),
        ("fig2_system_architecture.svg", fig2(),
         "Fig. 2 — DisasterSociety system architecture"),
        ("fig3_method_mechanism.svg", fig3(),
         "Fig. 3 — Resident social-process method mechanism loop"),
    ]
    manifest = {"generated_at": datetime.now(timezone.utc).isoformat(),
                "width_in": WIDTH_IN, "figures": []}
    for fname, body, desc in figures:
        p = OUT / fname
        p.write_text(body + "\n", encoding="utf-8")
        manifest["figures"].append({
            "file": fname, "description": desc,
            "sha256": hashlib.sha256((body + "\n").encode()).hexdigest(),
            "viewBox": body.split('viewBox="')[1].split('"')[0],
        })
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(figures)} SVG(s) + manifest.json to {OUT}")


if __name__ == "__main__":
    main()
