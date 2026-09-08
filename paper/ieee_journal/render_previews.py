#!/usr/bin/env python3
"""Render 300-dpi PNG previews and PDF for the three DisasterSociety SVGs.

Uses headless Chrome. Output lands next to the SVG sources in figures/ and is
recorded back into figures/manifest.json (sha256 for png/pdf).
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from pathlib import Path

OUT = Path("/Users/linnuo/tmp/disastersociety/paper/ieee_journal/figures")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DPI = 300
WIDTH_IN = 7.16
TARGET_W = int(round(DPI * WIDTH_IN))  # 2148 px


def svg_viewbox(path: Path) -> tuple[int, int]:
    text = path.read_text(encoding="utf-8")
    m = re.search(r'viewBox="0 0 (\d+) (\d+)"', text)
    assert m, f"no viewBox in {path.name}"
    return int(m.group(1)), int(m.group(2))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def render(svg: Path) -> dict:
    w, h = svg_viewbox(svg)
    scale = TARGET_W / w
    tw, th = TARGET_W, int(round(h * scale))
    stem = svg.stem
    html = OUT / f"{stem}.html"
    png = OUT / f"{stem}.png"
    pdf = OUT / f"{stem}.pdf"
    html.write_text(
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>html,body{margin:0;padding:0;background:#fff}</style></head>"
        f"<body><img src='{svg.name}' style='width:{tw}px;height:{th}px'></body></html>",
        encoding="utf-8",
    )
    url = html.resolve().as_uri()
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--screenshot={png}", f"--window-size={tw},{th}", url],
        check=True, capture_output=True,
    )
    subprocess.run(
        [CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
         f"--print-to-pdf={pdf}", url],
        check=True, capture_output=True,
    )
    html.unlink(missing_ok=True)
    return {
        "file": png.name, "kind": "png_preview", "dpi": DPI,
        "pixel_size": f"{tw}x{th}", "sha256": sha256(png),
    }, {
        "file": pdf.name, "kind": "pdf", "sha256": sha256(pdf),
    }


def main() -> None:
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for fig in manifest["figures"]:
        svg = OUT / fig["file"]
        png_info, pdf_info = render(svg)
        fig["png_preview"] = png_info
        fig["pdf"] = pdf_info
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("rendered previews + updated manifest")


if __name__ == "__main__":
    main()
