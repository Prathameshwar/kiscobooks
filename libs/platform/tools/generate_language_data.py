"""Generate ISO 639-1 languages using pinned pycountry and CLDR/Babel.

Language codes identify languages, not regional locale/date/number formatting.
Only alpha-2 languages are in this explicit initial materialization. Missing CLDR
native names remain null. Existing services opt in after adding their migration.
"""
import json
from pathlib import Path

import pycountry
from babel import Locale, UnknownLocaleError


def main() -> None:
    rows = []
    for language in pycountry.languages:
        code = getattr(language, "alpha_2", None)
        if code is None:
            continue
        try:
            native = Locale.parse(code).languages.get(code)
        except UnknownLocaleError:
            native = None
        assert len(language.name) <= 128 and (native is None or len(native) <= 128)
        rows.append({"code": code, "iso3": language.alpha_3, "name": language.name,
                     "native_name": native, "is_active": True})
    rows.sort(key=lambda row: row["code"])
    path = Path(__file__).resolve().parents[1] / "src/billing_platform/reference/data/language.json"
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
