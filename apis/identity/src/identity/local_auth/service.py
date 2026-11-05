"""The local provider's behaviour: OIDC grants, sign-in, sign-up, password change and recovery.

Every method takes the caller's ``AsyncSession`` and never commits: the HTTP layer commits after
an *expected* outcome (a refused password still has to persist its failure count) and rolls back
on anything else. Nothing here logs, audits or returns a password, a code or a token's value.
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Callable, Mapping
from typing import Any, cast
from urllib.parse import urlencode

from billing_platform.db import tenant_scope, unfiltered
from billing_platform.db.types import utcnow
from billing_platform.errors import ValidationFailedError
from billing_platform.ids import uuid7
from sqlalchemy import CursorResult, Result, delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.config import LocalAuthSettings, LocalClient
from identity.local_auth import domain, offload
from identity.local_auth.errors import (
    AccountDisabledError,
    AccountLockedError,
    AccountPendingError,
    AuthorizationRequestInvalidError,
    AuthorizeError,
    InvalidCredentialsError,
    OAuthError,
    RecoveryInvalidError,
    RegistrationUnavailableError,
)
from identity.local_auth.keys import SigningKeys
from identity.models import User
from identity.models.local_auth import (
    PATH_PENDING,
    PATH_PLATFORM,
    LocalAuthorization,
    LocalCredential,
    LocalIdentity,
    LocalRecoveryToken,
    LocalRefreshToken,
)

SCOPES = ("openid", "profile", "email", "offline_access", "billing.api")
_INVALID = "Username, email or password is incorrect."
_PURGE_AFTER = dt.timedelta(days=1)


def _ts(moment: dt.datetime) -> int:
    return int(moment.timestamp())


def _affected(result: Result[Any]) -> int:
    """Rows changed by an UPDATE: the atomic claim that makes a code or token single use."""
    return int(cast("CursorResult[Any]", result).rowcount)


class LocalAuth:
    def __init__(self, settings: LocalAuthSettings) -> None:
        self.settings = settings
        self.keys = SigningKeys(settings)
        self._policy = domain.LockoutPolicy(settings.max_failed_attempts, settings.lockout_seconds)
        self._base = settings.issuer.rstrip("/")
        self._ui = settings.auth_ui_url.rstrip("/")

    # ------------------------------------------------------------------ clients and discovery

    def _client(self, client_id: str | None) -> LocalClient | None:
        return next((c for c in self.settings.clients if c.client_id == client_id), None)

    def authenticate_client(self, client_id: str | None, secret: str | None) -> LocalClient:
        client = self._client(client_id)
        presented = domain.token_digest(secret or "")
        # One comparison whether or not the client exists, so existence is not a timing signal.
        expected = client.secret_sha256 if client else domain.token_digest("no such client")
        if not domain.same(presented, expected) or client is None:
            raise OAuthError("invalid_client", "Client authentication failed.", 401)
        return client

    def discovery(self) -> dict[str, Any]:
        methods = ["client_secret_post", "client_secret_basic"]
        return {
            "issuer": self.settings.issuer,
            "authorization_endpoint": f"{self._base}/authorize",
            "token_endpoint": f"{self._base}/token",
            "jwks_uri": f"{self._base}/jwks",
            "revocation_endpoint": f"{self._base}/revoke",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code", "refresh_token"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": ["RS256"],
            "scopes_supported": list(SCOPES),
            "token_endpoint_auth_methods_supported": methods,
            "revocation_endpoint_auth_methods_supported": methods,
            "code_challenge_methods_supported": ["S256"],
            "claims_supported": [
                "sub",
                "iss",
                "aud",
                "exp",
                "iat",
                "auth_time",
                "nonce",
                "email",
                "email_verified",
                "name",
                "billing_registration_region",
            ],
        }

    # ------------------------------------------------------------------ authorization

    async def authorize(self, db: AsyncSession, query: Mapping[str, str]) -> str:
        """Validate the request and return where the browser goes next (the sign-in page)."""
        client = self._client(query.get("client_id"))
        redirect = query.get("redirect_uri")
        if client is None or redirect is None or redirect not in client.redirect_uris:
            # Nothing is redirected until the URI is proven to be this client's own.
            raise AuthorizeError("invalid_request", "The client or redirect URI is not recognised.")
        state = query.get("state", "")

        def fail(error: str, description: str) -> AuthorizeError:
            return AuthorizeError(error, description, redirect_uri=redirect, state=state or None)

        if query.get("response_type") != "code":
            raise fail(
                "unsupported_response_type", "Only the authorization code flow is supported."
            )
        scopes = query.get("scope", "").split()
        if "openid" not in scopes or "billing.api" not in scopes or set(scopes) - set(SCOPES):
            raise fail("invalid_scope", "The scope must include openid and billing.api.")
        nonce = query.get("nonce", "")
        if not 1 <= len(state) <= 512 or not 1 <= len(nonce) <= 255:
            raise fail("invalid_request", "A state and a nonce are required.")
        challenge = query.get("code_challenge")
        if not domain.valid_challenge(challenge) or query.get("code_challenge_method") != "S256":
            raise fail("invalid_request", "A PKCE S256 code challenge is required.")
        max_age: int | None = None
        if "max_age" in query:
            raw = query["max_age"]
            if not (raw.isascii() and raw.isdecimal() and len(raw) <= 9):
                raise fail("invalid_request", "max_age must be a number of seconds.")
            max_age = int(raw)
        if query.get("prompt") == "none":
            # There is no remembered session: every request asks for the password.
            raise fail("login_required", "Signing in is required.")

        now = utcnow()
        request_id = domain.new_token()
        db.add(
            LocalAuthorization(
                request_hash=domain.token_digest(request_id),
                client_id=client.client_id,
                redirect_uri=redirect,
                scope=" ".join(scopes),
                state=state,
                nonce=nonce,
                code_challenge=str(challenge),
                max_age=max_age,
                expires_at=now + dt.timedelta(seconds=self.settings.request_seconds),
            )
        )
        await db.execute(
            delete(LocalAuthorization).where(LocalAuthorization.expires_at < now - _PURGE_AFTER)
        )
        await db.flush()
        return f"{self._ui}/signin?{urlencode({'request': request_id})}"

    async def _live_request(self, db: AsyncSession, request_id: str) -> LocalAuthorization:
        row = (
            await db.get(LocalAuthorization, domain.token_digest(request_id))
            if domain.well_formed_token(request_id)
            else None
        )
        if (
            row is None
            or row.code_hash is not None
            or row.consumed_at is not None
            or row.expires_at <= utcnow()
        ):
            raise AuthorizationRequestInvalidError("This sign-in request has expired. Start again.")
        return row

    async def request_expiry(self, db: AsyncSession, request_id: str) -> dt.datetime:
        return (await self._live_request(db, request_id)).expires_at

    # ------------------------------------------------------------------ sign-in

    async def login(
        self,
        db: AsyncSession,
        request_id: str,
        identifier: str,
        password: str,
        *,
        throttle_identity: Callable[[str], None] | None = None,
    ) -> str:
        """Check the password for one authorization request; return the client callback URL."""
        request = await self._live_request(db, request_id)
        now = utcnow()
        value = domain.clean_login(identifier)
        identity = None
        if value is not None:
            column = LocalIdentity.email if "@" in value else LocalIdentity.username
            identity = await db.scalar(select(LocalIdentity).where(column == value))
        if identity is not None and throttle_identity is not None:
            # Both identifiers resolve to one budget, including MySQL collation aliases.
            throttle_identity(str(identity.seq))
        # Row-locked, so simultaneous guesses at one account are counted one after another: the
        # failure counter is read and written under the lock, never from a stale copy.
        credential = (
            await db.get(LocalCredential, identity.seq, with_for_update=True) if identity else None
        )
        if identity is None or credential is None:
            await offload.burn_verification(password)
            raise InvalidCredentialsError(_INVALID)
        remaining = domain.locked_for(credential.lock_ends_at, now)
        if remaining:
            await offload.burn_verification(password)
            raise AccountLockedError(remaining)
        if not await offload.verify_password(credential.password_hash, password):
            credential.failed_attempts, credential.lock_ends_at = domain.after_failure(
                credential.failed_attempts, now, self._policy
            )
            await db.flush()
            if credential.lock_ends_at is not None:
                await self._audit(db, identity.sub, "user.account_locked")
            raise InvalidCredentialsError(_INVALID)
        if domain.needs_rehash(credential.password_hash):
            credential.password_hash = await offload.hash_password(password)
        credential.failed_attempts, credential.lock_ends_at = 0, None
        if identity.status == "pending":
            raise AccountPendingError("Your account is waiting for approval.")
        if identity.status != "active":
            raise AccountDisabledError("This account cannot sign in. Contact your administrator.")
        identity.last_login_at = now
        code = domain.new_token()
        request.identity_seq = identity.seq
        request.code_hash = domain.token_digest(code)
        request.authenticated_at = now
        request.expires_at = now + dt.timedelta(seconds=self.settings.code_seconds)
        await db.flush()
        await self._audit(db, identity.sub, "user.sign_in")
        return f"{request.redirect_uri}?{urlencode({'code': code, 'state': request.state})}"

    # ------------------------------------------------------------------ token endpoint

    async def token(
        self, db: AsyncSession, params: Mapping[str, str], *, basic: tuple[str, str] | None
    ) -> dict[str, Any]:
        client_id = basic[0] if basic else params.get("client_id")
        secret = basic[1] if basic else params.get("client_secret")
        client = self.authenticate_client(client_id, secret)
        grant = params.get("grant_type")
        if grant == "authorization_code":
            return await self._code_grant(db, client, params)
        if grant == "refresh_token":
            return await self._refresh_grant(db, client, params)
        raise OAuthError("unsupported_grant_type", "That grant type is not supported.")

    async def _code_grant(
        self, db: AsyncSession, client: LocalClient, params: Mapping[str, str]
    ) -> dict[str, Any]:
        code = params.get("code")
        row = (
            await db.scalar(
                select(LocalAuthorization).where(
                    LocalAuthorization.code_hash == domain.token_digest(code)
                )
            )
            if domain.well_formed_token(code)
            else None
        )
        grant_error = OAuthError("invalid_grant", "The authorization code is not valid.")
        if row is None or row.client_id != client.client_id or row.identity_seq is None:
            raise grant_error
        now = utcnow()
        if row.consumed_at is not None:
            # A code is single use: seeing it twice means someone else holds a copy. Revoke what
            # the first redemption started.
            if row.family_id is not None:
                await self._revoke_family(db, row.family_id)
                identity = await db.get(LocalIdentity, row.identity_seq)
                if identity is not None:
                    await self._audit(db, identity.sub, "user.refresh_reuse_detected")
            raise grant_error
        if (
            row.expires_at <= now
            or row.redirect_uri != params.get("redirect_uri")
            or not domain.pkce_matches(row.code_challenge, params.get("code_verifier"))
        ):
            # Whoever got this far with a wrong redirect or verifier must not get a second try.
            row.consumed_at = now
            await db.flush()
            raise grant_error
        claimed = await db.execute(
            update(LocalAuthorization)
            .where(
                LocalAuthorization.request_hash == row.request_hash,
                LocalAuthorization.consumed_at.is_(None),
            )
            .values(consumed_at=now)
        )
        if _affected(claimed) != 1:
            raise grant_error
        identity = await db.get(LocalIdentity, row.identity_seq)
        if identity is None or identity.status != "active":
            raise grant_error
        valid_after = await self._valid_after(db, identity.sub)
        if valid_after is not None and (row.authenticated_at or now) <= valid_after:
            # The password was changed (or the session ended) after this sign-in: a code from before
            # that must not turn into a session, however recently the token would be stamped.
            raise grant_error
        family = uuid7()
        row.family_id = family
        scopes = row.scope.split()
        return await self._issue(
            db,
            identity,
            client,
            scope=row.scope,
            authenticated_at=row.authenticated_at or now,
            nonce=row.nonce,
            family_id=family,
            id_token="openid" in scopes,
            refresh="offline_access" in scopes,
        )

    async def _refresh_grant(
        self, db: AsyncSession, client: LocalClient, params: Mapping[str, str]
    ) -> dict[str, Any]:
        raw = params.get("refresh_token")
        row = (
            await db.scalar(
                select(LocalRefreshToken).where(
                    LocalRefreshToken.token_hash == domain.token_digest(raw)
                )
            )
            if domain.well_formed_token(raw)
            else None
        )
        grant_error = OAuthError("invalid_grant", "The refresh token is not valid.")
        if row is None or row.client_id != client.client_id or row.revoked_at is not None:
            raise grant_error
        now = utcnow()
        reused = row.rotated_at is not None
        if not reused and row.expires_at > now:
            claimed = await db.execute(
                update(LocalRefreshToken)
                .where(
                    LocalRefreshToken.id == row.id,
                    LocalRefreshToken.rotated_at.is_(None),
                    LocalRefreshToken.revoked_at.is_(None),
                )
                .values(rotated_at=now)
            )
            reused = _affected(claimed) != 1
        elif not reused:
            raise grant_error
        identity = await db.get(LocalIdentity, row.identity_seq)
        if reused:
            # The same token twice: the family is compromised, so none of it may refresh again.
            await self._revoke_family(db, row.family_id)
            if identity is not None:
                await self._audit(db, identity.sub, "user.refresh_reuse_detected")
            raise grant_error
        valid_after = await self._valid_after(db, identity.sub) if identity else None
        if (
            identity is None
            or identity.status != "active"
            or (valid_after is not None and row.authenticated_at <= valid_after)
            # Refreshing slides the idle window, never the session: an absolute cap bounds how long
            # one sign-in (or one stolen refresh token) can be renewed.
            or (now - row.authenticated_at).total_seconds() > self.settings.session_seconds
        ):
            await self._revoke_family(db, row.family_id)
            raise grant_error
        requested = params.get("scope")
        scope = row.scope
        if requested is not None:
            if not set(requested.split()) <= set(row.scope.split()):
                raise OAuthError("invalid_scope", "The scope exceeds what was granted.")
            scope = " ".join(requested.split())
        return await self._issue(
            db,
            identity,
            client,
            scope=scope,
            authenticated_at=row.authenticated_at,
            nonce=None,
            family_id=row.family_id,
            id_token=False,
            refresh=True,
            grant_scope=row.scope,
        )

    async def revoke(
        self, db: AsyncSession, client_id: str | None, secret: str | None, token: str | None
    ) -> None:
        """RFC 7009: the answer never says whether the token existed."""
        client = self.authenticate_client(client_id, secret)
        if not domain.well_formed_token(token):
            return
        row = await db.scalar(
            select(LocalRefreshToken).where(
                LocalRefreshToken.token_hash == domain.token_digest(token)
            )
        )
        if row is not None and row.client_id == client.client_id:
            await self._revoke_family(db, row.family_id)

    async def _revoke_family(self, db: AsyncSession, family_id: uuid.UUID) -> None:
        await db.execute(
            update(LocalRefreshToken)
            .where(LocalRefreshToken.family_id == family_id, LocalRefreshToken.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )

    async def _issue(
        self,
        db: AsyncSession,
        identity: LocalIdentity,
        client: LocalClient,
        *,
        scope: str,
        authenticated_at: dt.datetime,
        nonce: str | None,
        family_id: uuid.UUID,
        id_token: bool,
        refresh: bool,
        grant_scope: str | None = None,
    ) -> dict[str, Any]:
        now = utcnow()
        # A session revoked at T must never be followed by a token that claims to predate T, and a
        # sign-in a moment later must not be refused for sharing T's second.
        floor = 0
        valid_after = await self._valid_after(db, identity.sub)
        if valid_after is not None:
            floor = _ts(valid_after) + 1
        issued = max(_ts(now), floor)
        authenticated = max(_ts(authenticated_at), floor)
        kid, key = await self.keys.signer(db)
        verified = identity.email_verified_at is not None
        access = self.keys.sign(
            kid,
            key,
            {
                "iss": self.settings.issuer,
                "aud": self.settings.audience,
                "sub": identity.sub,
                "iat": issued,
                "exp": issued + self.settings.access_token_seconds,
                "jti": uuid.uuid4().hex,
                "auth_time": authenticated,
                "scope": scope,
                "client_id": client.client_id,
                "email": identity.email,
                "email_verified": verified,
            },
            typ="at+jwt",
        )
        response: dict[str, Any] = {
            "access_token": access,
            "token_type": "Bearer",
            "expires_in": self.settings.access_token_seconds,
            "scope": scope,
        }
        if id_token:
            claims: dict[str, Any] = {
                "iss": self.settings.issuer,
                "aud": client.client_id,
                "sub": identity.sub,
                "iat": issued,
                "exp": issued + self.settings.access_token_seconds,
                "auth_time": authenticated,
                "nonce": nonce,
                "email": identity.email,
                "email_verified": verified,
                "name": identity.name,
            }
            if identity.country_code:
                claims["billing_registration_region"] = {
                    "country_code": identity.country_code,
                    "state_code": identity.state_code,
                }
            response["id_token"] = self.keys.sign(kid, key, claims, typ="JWT")
        if refresh:
            token = domain.new_token()
            db.add(
                LocalRefreshToken(
                    family_id=family_id,
                    token_hash=domain.token_digest(token),
                    identity_seq=identity.seq,
                    client_id=client.client_id,
                    scope=grant_scope or scope,
                    authenticated_at=authenticated_at,
                    expires_at=now + dt.timedelta(seconds=self.settings.refresh_token_seconds),
                )
            )
            response["refresh_token"] = token
        await db.flush()
        return response

    # ------------------------------------------------------------------ registration

    async def register(
        self,
        db: AsyncSession,
        *,
        name: str,
        username: str,
        email: str,
        password: str,
        country_code: str,
        state_code: str,
        workspace_name: str | None,
    ) -> None:
        if not self.settings.registration_enabled:
            raise RegistrationUnavailableError("Registration is not available.")
        fields: dict[str, str] = {}
        clean_name, clean_username, clean_email = (
            domain.clean_name(name),
            domain.clean_username(username),
            domain.clean_email(email),
        )
        if clean_name is None:
            fields["name"] = "Enter your full name (up to 100 characters)."
        if clean_username is None:
            fields["username"] = (
                "Use 3 to 64 lowercase letters, numbers, dots, hyphens or underscores."
            )
        if clean_email is None:
            fields["email"] = "Enter a valid email address."
        problem = domain.password_problem(password)
        if problem:
            fields["password"] = problem
        region = domain.clean_region(country_code, state_code)
        if region is None:
            fields["country_code"] = "Choose a country."
        try:
            workspace = domain.clean_workspace(workspace_name)
        except ValueError:
            workspace = None
            fields["workspace_name"] = "Enter a workspace name with up to 200 characters."
        if fields:
            raise ValidationFailedError("Please check the highlighted fields.", fields=fields)
        assert clean_name and clean_username and clean_email and region  # narrowed by `fields`
        try:
            await self.create_account(
                db,
                name=clean_name,
                username=clean_username,
                email=clean_email,
                password=password,
                region=region,
                workspace_name=workspace,
                path=PATH_PENDING,
                status="pending",
                verified=False,
            )
        except IntegrityError:
            await db.rollback()
            # An existing email or username: the same answer as any other refusal, at the same cost.
            await offload.burn_verification(password)
            raise RegistrationUnavailableError(
                "These account details cannot be used. "
                "Check the fields or contact your administrator."
            ) from None

    async def create_account(
        self,
        db: AsyncSession,
        *,
        name: str,
        username: str,
        email: str,
        password: str,
        region: tuple[str, str],
        workspace_name: str | None,
        path: str,
        status: str,
        verified: bool,
        provision_command: str | None = None,
    ) -> LocalIdentity:
        now = utcnow()
        identity = LocalIdentity(
            uid=uuid7(),
            sub=domain.new_subject(),
            email=email,
            name=name,
            username=username,
            country_code=region[0],
            state_code=region[1],
            workspace_name=workspace_name,
            path=path,
            status=status,
            email_verified_at=now if verified else None,
            provision_command=provision_command,
        )
        db.add(identity)
        await db.flush()
        db.add(
            LocalCredential(
                identity_seq=identity.seq,
                password_hash=await offload.hash_password(password),
                failed_attempts=0,
            )
        )
        await db.flush()
        return identity

    async def create_administrator(
        self,
        db: AsyncSession,
        *,
        name: str,
        email: str,
        password: str,
        path: str,
        active: bool = True,
        provision_command: str | None = None,
        username: str | None = None,
    ) -> LocalIdentity:
        """An administrator account created already verified (setup, tenant provisioning)."""
        fields: dict[str, str] = {}
        clean_name, clean_email = domain.clean_name(name), domain.clean_email(email)
        if clean_name is None:
            fields["name"] = "Enter the administrator's full name."
        if clean_email is None:
            fields["email"] = "Enter a valid email address."
        problem = domain.password_problem(password)
        if problem:
            fields["password"] = problem
        if fields:
            raise ValidationFailedError("Please check the highlighted fields.", fields=fields)
        assert clean_name and clean_email
        username = username or "admin-" + domain.token_digest(clean_email)[:32]
        try:
            return await self.create_account(
                db,
                name=clean_name,
                username=username,
                email=clean_email,
                password=password,
                region=("", ""),
                workspace_name=None,
                path=path,
                status="active" if active else "pending",
                verified=True,
                provision_command=provision_command,
            )
        except IntegrityError:
            await db.rollback()
            raise RegistrationUnavailableError(
                "An account already uses this email address."
            ) from None

    async def administrator_exists(self, db: AsyncSession) -> bool:
        return (
            await db.scalar(
                select(LocalIdentity.seq).where(LocalIdentity.path == PATH_PLATFORM).limit(1)
            )
            is not None
        )

    # ------------------------------------------------------------------ password change

    async def change_password(self, db: AsyncSession, sub: str, current: str, new: str) -> None:
        identity = await self._by_sub(db, sub)
        credential = (
            await db.get(LocalCredential, identity.seq, with_for_update=True) if identity else None
        )
        if identity is None or credential is None or identity.status != "active":
            raise InvalidCredentialsError(_INVALID)
        now = utcnow()
        remaining = domain.locked_for(credential.lock_ends_at, now)
        if remaining:
            raise AccountLockedError(remaining)
        if not await offload.verify_password(credential.password_hash, current):
            credential.failed_attempts, credential.lock_ends_at = domain.after_failure(
                credential.failed_attempts, now, self._policy
            )
            await db.flush()
            if credential.lock_ends_at is not None:
                await self._audit(db, identity.sub, "user.account_locked")
            raise ValidationFailedError(
                "The current password is incorrect.",
                fields={"current_password": "The current password is incorrect."},
            )
        problem = domain.password_problem(new)
        if problem:
            raise ValidationFailedError(problem, fields={"new_password": problem})
        if await offload.verify_password(credential.password_hash, new):
            message = "Choose a password you have not just used."
            raise ValidationFailedError(message, fields={"new_password": message})
        await self._set_password(db, identity, credential, new)
        await self._audit(db, identity.sub, "user.password_changed")

    async def _set_password(
        self, db: AsyncSession, identity: LocalIdentity, credential: LocalCredential, password: str
    ) -> None:
        """New hash, clean counters, and every existing session and refresh family ended."""
        now = utcnow()
        credential.password_hash = await offload.hash_password(password)
        credential.password_changed_at = now
        credential.failed_attempts, credential.lock_ends_at = 0, None
        await db.execute(
            update(LocalRefreshToken)
            .where(
                LocalRefreshToken.identity_seq == identity.seq,
                LocalRefreshToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        # A link issued before the change (or left over from it) is no longer a way in.
        await db.execute(
            update(LocalRecoveryToken)
            .where(
                LocalRecoveryToken.identity_seq == identity.seq,
                LocalRecoveryToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        with unfiltered():
            user = await db.scalar(select(User).where(User.authentik_sub == identity.sub))
        if user is not None:
            with tenant_scope(user.tenant_id):
                user.tokens_valid_after_at = now
                await db.flush()
        await db.flush()

    # ------------------------------------------------------------------ recovery

    async def issue_recovery(
        self, db: AsyncSession, identity: LocalIdentity, *, issued_by: uuid.UUID | None
    ) -> tuple[str, dt.datetime]:
        """A one-time link token. Only an active account is recoverable, and only one link lives."""
        if identity.status != "active":
            raise RecoveryInvalidError("This account cannot use password recovery.")
        now = utcnow()
        await db.execute(
            update(LocalRecoveryToken)
            .where(
                LocalRecoveryToken.identity_seq == identity.seq,
                LocalRecoveryToken.used_at.is_(None),
            )
            .values(used_at=now)
        )
        token = domain.new_token()
        expires = now + dt.timedelta(seconds=self.settings.recovery_token_seconds)
        db.add(
            LocalRecoveryToken(
                identity_seq=identity.seq,
                token_hash=domain.token_digest(token),
                issued_by=issued_by,
                expires_at=expires,
            )
        )
        await db.flush()
        return token, expires

    def recovery_url(self, token: str) -> str:
        return f"{self._ui}/reset?{urlencode({'token': token})}"

    async def _live_recovery(self, db: AsyncSession, token: str) -> LocalRecoveryToken:
        row: LocalRecoveryToken | None = (
            await db.scalar(
                select(LocalRecoveryToken).where(
                    LocalRecoveryToken.token_hash == domain.token_digest(token)
                )
            )
            if domain.well_formed_token(token)
            else None
        )
        if row is None or row.used_at is not None or row.expires_at <= utcnow():
            raise RecoveryInvalidError("This recovery link is invalid or has expired.")
        return row

    async def inspect_recovery(self, db: AsyncSession, token: str) -> None:
        await self._live_recovery(db, token)

    async def redeem_recovery(self, db: AsyncSession, token: str, new_password: str) -> None:
        row = await self._live_recovery(db, token)
        problem = domain.password_problem(new_password)
        if problem:
            raise ValidationFailedError(problem, fields={"new_password": problem})
        identity = await db.get(LocalIdentity, row.identity_seq)
        credential = await db.get(LocalCredential, row.identity_seq)
        if identity is None or credential is None or identity.status != "active":
            raise RecoveryInvalidError("This recovery link is invalid or has expired.")
        claimed = await db.execute(
            update(LocalRecoveryToken)
            .where(LocalRecoveryToken.id == row.id, LocalRecoveryToken.used_at.is_(None))
            .values(used_at=utcnow())
        )
        if _affected(claimed) != 1:
            raise RecoveryInvalidError("This recovery link is invalid or has expired.")
        await self._set_password(db, identity, credential, new_password)
        # The person who redeemed it is the target; who issued the link is recorded beside it.
        issued = f"recovery link issued by user {row.issued_by}" if row.issued_by else None
        await self._audit(db, identity.sub, "user.password_recovery_completed", reason=issued)

    # ------------------------------------------------------------------ lookups

    async def _by_email(self, db: AsyncSession, email: str) -> LocalIdentity | None:
        found: LocalIdentity | None = await db.scalar(
            select(LocalIdentity).where(LocalIdentity.email == email)
        )
        return found

    async def _by_sub(self, db: AsyncSession, sub: str) -> LocalIdentity | None:
        found: LocalIdentity | None = await db.scalar(
            select(LocalIdentity).where(LocalIdentity.sub == sub)
        )
        return found

    async def identity_for_user(self, db: AsyncSession, user: User) -> LocalIdentity | None:
        return await self._by_sub(db, user.authentik_sub) if user.authentik_sub else None

    async def _valid_after(self, db: AsyncSession, sub: str) -> dt.datetime | None:
        with unfiltered():
            return await db.scalar(
                select(User.tokens_valid_after_at).where(User.authentik_sub == sub)
            )

    async def _audit(
        self, db: AsyncSession, sub: str, action: str, *, reason: str | None = None
    ) -> None:
        """Recorded against the linked user and tenant; an unlinked sign-up has no tenant yet."""
        from identity.api.auth import Actor
        from identity.services.audit import record

        with unfiltered():
            user = await db.scalar(select(User).where(User.authentik_sub == sub))
        if user is not None:
            record(
                db,
                Actor(user.tenant_id, user.id),
                action=action,
                entity="user",
                entity_id=user.id,
                reason=reason,
            )
            await db.flush()
