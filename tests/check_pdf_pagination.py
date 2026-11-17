# -*- coding: utf-8 -*-
"""Compare layout estimates with Chromium's actual printed PDF page counts.

Run: python tests/check_pdf_pagination.py
Requires: playwright, pypdf, and Playwright Chromium.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent.parent
CASES = [
    ("short_poem", "静夜思", "床前明月光，疑是地上霜。\n举头望明月，低头思故乡。", {}),
    ("long_poem", "长诗", "春江潮水连海平，海上明月共潮生。\n" * 9, {}),
    ("one_page_target", "长诗一页", "春江潮水连海平，海上明月共潮生。\n" * 9, {"target_pages": 1}),
    ("landscape", "横向古诗", "春江潮水连海平，海上明月共潮生。\n" * 9, {"landscape": True}),
    ("two_columns", "双栏古诗", "春江潮水连海平，海上明月共潮生。\n" * 9, {"columns": 2}),
    ("unreachable_target", "长文页数下限", "春江潮水连海平，海上明月共潮生。\n" * 60, {"target_pages": 1}),
]

def main():
    mismatches = []
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        work = Path(tmp)
        browser = p.chromium.launch()
        page = browser.new_page()
        for name, title, body, opts in CASES:
            spec = {"title": title, "text": body.rstrip(), "template": "poem", **opts}
            spec_path = work / (name + ".json")
            html_path = work / (name + ".html")
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts/generate.py"),
                 "--spec", str(spec_path), "--out", str(html_path)],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            )
            if proc.returncode:
                raise RuntimeError(f"{name}: {proc.stderr}\n{proc.stdout}")
            result = json.loads(proc.stdout)
            if not result["ok"]:
                raise RuntimeError(f"{name}: {result}")
            estimated = result["layout"]["pages_est"]
            page.goto(html_path.resolve().as_uri())
            page.emulate_media(media="print")
            if name == "two_columns":
                details = page.evaluate("""() => {
                    const main = document.querySelector('main');
                    const sheet = document.querySelector('.sheet');
                    const header = document.querySelector('header.hd');
                    const stanzas = [...document.querySelectorAll('.stanza')];
                    const cs = getComputedStyle(main);
                    return {
                        columns: cs.columnCount,
                        columnFill: cs.columnFill,
                        columnGap: cs.columnGap,
                        sheetHeight: sheet?.getBoundingClientRect().height,
                        mainHeight: main?.getBoundingClientRect().height,
                        mainScrollHeight: main?.scrollHeight,
                        headerHeight: header?.getBoundingClientRect().height,
                        stanzas: stanzas.map(el => ({
                            className: el.className,
                            height: el.getBoundingClientRect().height,
                            rows: el.querySelectorAll('.v').length,
                            breakInside: getComputedStyle(el).breakInside
                        }))
                    };
                }""")
                print("two_columns DOM diagnostics: " +
                      json.dumps(details, ensure_ascii=False), flush=True)
                print("two_columns layout diagnostics: " +
                      json.dumps(result["layout"], ensure_ascii=False), flush=True)
            pdf = page.pdf(prefer_css_page_size=True, print_background=True)
            pdf_path = work / (name + ".pdf")
            pdf_path.write_bytes(pdf)
            actual = len(PdfReader(str(pdf_path)).pages)
            print(f"{name}: estimated={estimated}, actual={actual}, "
                  f"target={opts.get('target_pages', '-')}", flush=True)
            if estimated != actual:
                mismatches.append((name, estimated, actual))
        browser.close()
    if mismatches:
        print("\nEstimate vs actual PDF mismatches:")
        for name, estimated, actual in mismatches:
            print(f"  {name}: estimated {estimated}, actual {actual}")
        return 1
    print("\nAll sampled PDF page counts match their estimates.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
