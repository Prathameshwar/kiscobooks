"""Local authentication rules that need no database (docs/local-auth.md §6).

Each test names the way the rule could quietly fail: a boundary off by one, a comparison that
leaks by timing, a PKCE method that is not S256, a lock that never releases.
"""

from __future__ import annotations

import datetime as dt
import unicodedata
from collections.abc import Iterator

import pytest

from identity.local_auth import domain
from identity.local_auth.domain import HashParameters, LockoutPolicy

NOW = dt.datetime(2026, 10, 31, 12, 0, tzinfo=dt.UTC)
POLICY = LockoutPolicy(max_failed_attempts=3, lockout_seconds=600)


@pytest.fixture(autouse=True)
def cheap_hashing() -> Iterator[None]:
    domain.configure_hashing(HashParameters(time_cost=1, memory_kib=8, parallelism=1))
    yield
    domain.configure_hashing(HashParameters())


class TestPasswordPolicy:
    @pytest.mark.parametrize("password", ["a" * 6, "a" * 128, "pässwörd", "密码密码密码", "🔑" * 6])
    def test_accepts_six_to_128_code_points(self, password: str) -> None:
        assert domain.password_problem(password) is None

    @pytest.mark.parametrize("password", ["", "a" * 5, "a" * 129, "🔑" * 5, "🔑" * 129])
    def test_refuses_outside_the_range_counting_code_points_not_bytes(self, password: str) -> None:
        assert "6 to 128 characters" in (domain.password_problem(password) or "")

    @pytest.mark.parametrize("password", ["abc\x00def", "abc\ndef", "abc\x7fdef", "abc\tdef"])
    def test_refuses_control_characters(self, password: str) -> None:
        assert domain.password_problem(password) is not None


class TestHashing:
    def test_hashes_with_argon2id_and_a_fresh_salt_each_time(self) -> None:
        first, second = domain.hash_password("correct horse"), domain.hash_password("correct horse")
        assert first.startswith("$argon2id$") and first != second

    def test_verifies_the_right_password_only(self) -> None:
        stored = domain.hash_password("correct horse")
        assert domain.verify_password(stored, "correct horse")
        assert not domain.verify_password(stored, "correct horse ")
        assert not domain.verify_password(stored, "Correct horse")

    def test_treats_equivalent_unicode_forms_as_the_same_password(self) -> None:
        composed = unicodedata.normalize("NFC", "é-passphrase")
        decomposed = unicodedata.normalize("NFD", "é-passphrase")
        assert composed != decomposed
        assert domain.verify_password(domain.hash_password(composed), decomposed)

    @pytest.mark.parametrize(
        "stored", ["", "plaintext", "$argon2id$garbage", "$2b$12$abc", "x" * 400]
    )
    def test_an_unreadable_hash_is_a_wrong_password_not_an_exception(self, stored: str) -> None:
        assert domain.verify_password(stored, "anything") is False

    def test_flags_a_hash_made_with_weaker_parameters_for_upgrade(self) -> None:
        stored = domain.hash_password("correct horse")
        assert domain.needs_rehash(stored) is False
        domain.configure_hashing(HashParameters(time_cost=2, memory_kib=16, parallelism=1))
        assert domain.needs_rehash(stored) is True
        assert domain.needs_rehash("not a hash") is True

    def test_burning_a_verification_never_raises_and_never_matches(self) -> None:
        domain.burn_verification("whatever")
        assert domain.dummy_hash().startswith("$argon2id$")
        assert domain.verify_password(domain.dummy_hash(), "whatever") is False

    def test_production_parameters_are_memory_hard(self) -> None:
        domain.configure_hashing(HashParameters())
        stored = domain.hash_password("correct horse")
        assert "m=65536" in stored and "t=3" in stored and "p=2" in stored


class TestTokens:
    def test_tokens_are_256_bits_url_safe_and_never_repeat(self) -> None:
        tokens = {domain.new_token() for _ in range(200)}
        assert len(tokens) == 200
        assert all(domain.well_formed_token(token) for token in tokens)

    def test_the_digest_is_stable_hex_and_does_not_contain_the_token(self) -> None:
        token = domain.new_token()
        digest = domain.token_digest(token)
        assert digest == domain.token_digest(token) and len(digest) == 64
        assert token not in digest and digest != domain.token_digest(token + "x")

    @pytest.mark.parametrize(
        "value", [None, 5, "", "short", "a" * 42, "a" * 44, "a" * 42 + "!", "a b" + "c" * 40]
    )
    def test_rejects_anything_that_is_not_a_43_character_token(self, value: object) -> None:
        assert domain.well_formed_token(value) is False

    def test_subjects_are_64_hex_characters(self) -> None:
        subject = domain.new_subject()
        assert len(subject) == 64 and int(subject, 16) >= 0 and subject != domain.new_subject()

    def test_same_compares_whole_values(self) -> None:
        assert domain.same("abc", "abc")
        assert not domain.same("abc", "abd")
        assert not domain.same("abc", "abcd")
        assert not domain.same("", "a")


class TestPkce:
    # RFC 7636 appendix B.
    VERIFIER = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    CHALLENGE = "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"

    def test_matches_the_rfc_vector(self) -> None:
        assert domain.s256(self.VERIFIER) == self.CHALLENGE
        assert domain.pkce_matches(self.CHALLENGE, self.VERIFIER)

    def test_refuses_a_different_verifier(self) -> None:
        assert not domain.pkce_matches(self.CHALLENGE, self.VERIFIER[:-1] + "A")

    def test_refuses_the_plain_method_because_the_challenge_is_never_the_verifier(self) -> None:
        assert not domain.pkce_matches(self.VERIFIER, self.VERIFIER)

    @pytest.mark.parametrize(
        "verifier", [None, 7, "", "short", "a" * 42, "a" * 129, "é" * 50, "a b" * 20]
    )
    def test_refuses_a_malformed_verifier(self, verifier: object) -> None:
        assert not domain.pkce_matches(self.CHALLENGE, verifier)

    @pytest.mark.parametrize("value", [None, "", "short", "a" * 44, "a" * 42 + "=", "a" * 42 + "+"])
    def test_refuses_a_malformed_challenge(self, value: object) -> None:
        assert not domain.valid_challenge(value)

    def test_accepts_a_real_challenge(self) -> None:
        assert domain.valid_challenge(self.CHALLENGE)


class TestLockout:
    def test_counts_failures_below_the_limit_without_locking(self) -> None:
        assert domain.after_failure(0, NOW, POLICY) == (1, None)
        assert domain.after_failure(1, NOW, POLICY) == (2, None)

    def test_the_failure_that_reaches_the_limit_locks_and_restarts_the_count(self) -> None:
        attempts, until = domain.after_failure(2, NOW, POLICY)
        assert attempts == 0 and until == NOW + dt.timedelta(seconds=600)

    def test_reports_the_seconds_left_and_releases_at_the_deadline(self) -> None:
        until = NOW + dt.timedelta(seconds=90)
        assert domain.locked_for(until, NOW) == 90
        assert domain.locked_for(until, NOW + dt.timedelta(seconds=89, milliseconds=500)) == 1
        assert domain.locked_for(until, until) == 0
        assert domain.locked_for(until, until + dt.timedelta(seconds=1)) == 0
        assert domain.locked_for(None, NOW) == 0


class TestInput:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (" Tenant1 ", "tenant1"),
            ("Tenant1@Example.Test ", "tenant1@example.test"),
            ("bill-admin-" + "a" * 32, "bill-admin-" + "a" * 32),
            ("admin-" + "b" * 32, "admin-" + "b" * 32),
            ("a" * 64, "a" * 64),
            ("", None),
            ("ab", None),
            ("has space", None),
            ("bad/name", None),
            ("bad@address", None),
            ("a" * 65, None),
            ("has\x00control", None),
        ],
    )
    def test_login_accepts_usernames_and_emails(self, value: str, expected: str | None) -> None:
        assert domain.clean_login(value) == expected

    def test_names(self) -> None:
        assert domain.clean_name("  Asha Rao ") == "Asha Rao"
        assert domain.clean_name("") is None and domain.clean_name("   ") is None
        assert domain.clean_name("x" * 101) is None and domain.clean_name("a\nb") is None
        assert domain.clean_name("x" * 100) == "x" * 100

    def test_usernames_are_lowercased_and_shaped(self) -> None:
        assert domain.clean_username(" Asha.Rao ") == "asha.rao"
        for bad in ("ab", "-abc", ".abc", "a b c", "ü" * 5, "a" * 65, ""):
            assert domain.clean_username(bad) is None, bad
        assert domain.clean_username("a" * 64) == "a" * 64

    def test_the_names_derived_for_provisioned_accounts_are_not_available_at_sign_up(self) -> None:
        for reserved in ("bill-admin-" + "0" * 32, "admin-" + "ab12" * 8, " Admin-" + "F" * 32):
            assert domain.clean_username(reserved) is None, reserved
        # Close, but not the derived shape, so ordinary people called "admin" are unaffected.
        for fine in ("admin", "admin-ops", "admin-" + "0" * 31, "admin-" + "0" * 33, "bill-admin"):
            assert domain.clean_username(fine) == fine, fine

    def test_one_throttle_key_for_every_spelling_the_database_folds_together(self) -> None:
        assert (
            domain.throttle_key("Asha@Alpha.Example")
            == domain.throttle_key(" ásha@alpha.example ")
            == domain.throttle_key("ASHA@ALPHA.EXAMPLE")
            == domain.throttle_key("ásha@alpha.example")
            == "asha@alpha.example"
        )
        assert domain.throttle_key("asha@alpha.example") != domain.throttle_key(
            "ravi@alpha.example"
        )
        assert len(domain.throttle_key("a" * 400)) == 320

    def test_regions(self) -> None:
        assert domain.clean_region("IN", "IN-KA") == ("IN", "IN-KA")
        assert domain.clean_region("IN", "") == ("IN", "")
        for country, state in (
            ("in", ""),
            ("IND", ""),
            ("IN", "KA"),
            ("IN", "IN-TOOLONG"),
            ("", ""),
        ):
            assert domain.clean_region(country, state) is None, (country, state)

    def test_workspace_names(self) -> None:
        assert domain.clean_workspace(None) is None
        assert domain.clean_workspace("  Acme  ") == "Acme" and domain.clean_workspace("") == ""
        with pytest.raises(ValueError):
            domain.clean_workspace("x" * 201)
        with pytest.raises(ValueError):
            domain.clean_workspace("a\x00b")
