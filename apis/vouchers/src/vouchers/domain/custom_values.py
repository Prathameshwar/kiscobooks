"""Canonical text search follows the shared uniqueness contract on every database."""

import unicodedata


def search_text(value: str, *, case_sensitive: bool) -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    return normalized if case_sensitive else normalized.casefold()
