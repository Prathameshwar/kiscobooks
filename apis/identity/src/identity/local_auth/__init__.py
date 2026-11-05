"""The local authentication provider (docs/local-auth.md): Identity as the OpenID Connect provider.

`domain` is pure rules with no I/O; `keys`, `service` and `adapters` hold the database work; the
HTTP surface lives in `identity.api.oidc` and `identity.api.local_auth`.
"""
