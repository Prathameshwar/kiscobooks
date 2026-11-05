"""Pure rules for local authentication: passwords, tokens, PKCE, lockout and input checks.

No database, no framework, no clock: every time is passed in, so each rule is testable on its
own (CLAUDE.md §7). Nothing here ever logs or returns a password or a token.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import re
import secrets
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import TypeGuard

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

#: docs/local-auth.md §6 — kept from the 2026-10-20 registration decision: 6 to 128 code points.
PASSWORD_MIN = 6
PASSWORD_MAX = 128

EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
#: Names the platform derives for the accounts it provisions (a hash of the email). Nobody can
#: sign up with one, or pre-register the name an administrator will be given.
RESERVED_USERNAME = re.compile(r"^(?:bill-admin|admin)-[0-9a-f]{32}$")
COUNTRY = re.compile(r"^[A-Z]{2}$")
STATE = re.compile(r"^[A-Z]{2}-[A-Z0-9]{1,3}$")
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_VERIFIER = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")
_CHALLENGE = re.compile(r"^[A-Za-z0-9_-]{43}$")
_TOKEN = re.compile(r"^[A-Za-z0-9_-]{43}$")


@dataclass(frozen=True, slots=True)
class HashParameters:
    """argon2id cost. Stored inside every hash, so raising it later upgrades users on sign-in."""

    time_cost: int = 3
    memory_kib: int = 65_536
    parallelism: int = 2


#: Production cost. Tests lower it through ``configure_hashing`` — never in a service.
_PARAMETERS = HashParameters()


def configure_hashing(parameters: HashParameters) -> None:
    """Replace the hashing cost (a test seam, and the place an operator tuning would land)."""
    global _PARAMETERS
    _PARAMETERS = parameters
    _hasher.cache_clear()
    dummy_hash.cache_clear()


@lru_cache(maxsize=1)
def _hasher() -> PasswordHasher:
    return PasswordHasher(
        time_cost=_PARAMETERS.time_cost,
        memory_cost=_PARAMETERS.memory_kib,
        parallelism=_PARAMETERS.parallelism,
    )


def normalise_password(value: str) -> str:
    """NFKC, so visually identical passphrases typed on different systems verify equal."""
    return unicodedata.normalize("NFKC", value)


def password_problem(value: str) -> str | None:
    """A reason the password is unacceptable, or ``None``. Counts Unicode code points."""
    length = len(value)
    if length < PASSWORD_MIN or length > PASSWORD_MAX or _CONTROL.search(value):
        return (
            f"Use {PASSWORD_MIN} to {PASSWORD_MAX} characters. "
            "A long, unique passphrase works well."
        )
    return None


def hash_password(password: str) -> str:
    return _hasher().hash(normalise_password(password))


def verify_password(stored: str, password: str) -> bool:
    """``False`` for a wrong password *and* for a hash that cannot be read — never an exception."""
    try:
        return bool(_hasher().verify(stored, normalise_password(password)))
    except (VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    try:
        return bool(_hasher().check_needs_rehash(stored))
    except InvalidHashError:
        return True


@lru_cache(maxsize=1)
def dummy_hash() -> str:
    """A real hash of a random value, verified when no account exists so timing matches."""
    return _hasher().hash(secrets.token_urlsafe(24))


def burn_verification(password: str) -> None:
    """Spend one verification's time on an unknown account (no account enumeration by timing)."""
    verify_password(dummy_hash(), password)


# ---------------------------------------------------------------------------- tokens


def new_token() -> str:
    """256 random bits, URL-safe, 43 characters. The only form that is ever shown to a person."""
    return secrets.token_urlsafe(32)


def token_digest(token: str) -> str:
    """What is stored: SHA-256 hex. Tokens are high entropy, so a fast digest is sufficient."""
    return hashlib.sha256(token.encode()).hexdigest()


def well_formed_token(value: object) -> TypeGuard[str]:
    return isinstance(value, str) and _TOKEN.fullmatch(value) is not None


def same(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode(), right.encode())


def new_subject() -> str:
    """The token ``sub``: 256 random bits as 64 hex characters (opaque, fits the 64-char column)."""
    return secrets.token_hex(32)


# ---------------------------------------------------------------------------- PKCE


def s256(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def valid_challenge(value: object) -> bool:
    return isinstance(value, str) and _CHALLENGE.fullmatch(value) is not None


def pkce_matches(challenge: str, verifier: object) -> bool:
    """RFC 7636 S256 only. ``plain`` is not accepted anywhere in this provider."""
    if not isinstance(verifier, str) or _VERIFIER.fullmatch(verifier) is None:
        return False
    return same(challenge, s256(verifier))


# ---------------------------------------------------------------------------- lockout


@dataclass(frozen=True, slots=True)
class LockoutPolicy:
    max_failed_attempts: int
    lockout_seconds: int


def locked_for(locked_until: dt.datetime | None, now: dt.datetime) -> int:
    """Seconds still locked (0 when not locked)."""
    if locked_until is None or locked_until <= now:
        return 0
    return max(1, int((locked_until - now).total_seconds()))


def after_failure(
    failed_attempts: int, now: dt.datetime, policy: LockoutPolicy
) -> tuple[int, dt.datetime | None]:
    """The new counter and lock. Reaching the limit locks and restarts the count."""
    attempts = failed_attempts + 1
    if attempts >= policy.max_failed_attempts:
        return 0, now + dt.timedelta(seconds=policy.lockout_seconds)
    return attempts, None


# ---------------------------------------------------------------------------- input


def throttle_key(email: str) -> str:
    """A key that every spelling the database treats as one account shares.

    The email column compares accent- and case-insensitively, so ``ásha@x`` signs in as
    ``asha@x``; a throttle keyed on the raw text would give each spelling its own budget.
    """
    decomposed = unicodedata.normalize("NFKD", email.strip().casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))[:320]


def clean_email(value: str) -> str | None:
    """Lower-cased, or ``None`` when it is not a plausible address (≤ 254 characters)."""
    email = value.strip().lower()
    if len(email) > 254 or _CONTROL.search(email) or EMAIL.fullmatch(email) is None:
        return None
    return email


def clean_name(value: str) -> str | None:
    name = value.strip()
    return name if 0 < len(name) <= 100 and not _CONTROL.search(name) else None


def clean_username(value: str) -> str | None:
    """A username a person may choose at sign-up; the derived provisioning names are not."""
    username = value.strip().lower()
    if not USERNAME.fullmatch(username) or RESERVED_USERNAME.fullmatch(username):
        return None
    return username


def clean_login(value: str) -> str | None:
    """Email or username; provisioning names are valid here, but not at registration."""
    identifier = value.strip().lower()
    if "@" in identifier:
        return clean_email(identifier)
    return identifier if USERNAME.fullmatch(identifier) else None


def clean_region(country: str, state: str) -> tuple[str, str] | None:
    if not COUNTRY.fullmatch(country) or (state and not STATE.fullmatch(state)):
        return None
    return country, state


def clean_workspace(value: str | None) -> str | None:
    """``None`` means "no workspace requested"; invalid text raises ``ValueError``."""
    if value is None:
        return None
    text = value.strip()
    if len(text) > 200 or _CONTROL.search(text):
        raise ValueError("invalid workspace name")
    return text
