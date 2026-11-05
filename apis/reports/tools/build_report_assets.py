"""Build a deterministic offline presentation bundle from the shared UI tokens."""

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
ASSETS = ROOT / "apis/reports/src/reports/rendering/assets"
FONT_REVISION = "ffebf8c1ee449e544955a7e813c54f9b73848eac"


def bundle() -> dict:
    source = ROOT / "mfes/packages/ui/src/styles"
    names = ("tokens.css", "theme-light.css", "report.css")
    texts = {name: (source / name).read_text("utf-8") for name in names}
    css = "\n".join(texts.values())
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)
    css = re.sub(r"@import[^;]+;", "", css)
    if re.search(r"url\s*\(|@import|</style", css, re.IGNORECASE):
        raise ValueError("report styles cannot fetch external assets")
    tokens = dict(re.findall(r"(--[a-z0-9-]+)\s*:\s*([^;{}]+);", css))
    fonts = {
        file.name: hashlib.sha256(file.read_bytes()).hexdigest()
        for file in sorted((ASSETS / "fonts").iterdir())
        if file.is_file()
    }
    return {
        "version": 1,
        "css": css.strip(),
        "tokens": tokens,
        "source_hashes": {
            name: hashlib.sha256(text.encode()).hexdigest() for name, text in texts.items()
        },
        "font_source": f"https://github.com/notofonts/noto-fonts/tree/{FONT_REVISION}",
        "fonts": fonts,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    target = ASSETS / "presentation-v1.json"
    content = json.dumps(bundle(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.check:
        if target.read_text("utf-8") != content:
            raise SystemExit("report presentation bundle is stale")
    else:
        target.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
