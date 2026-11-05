"""The `identity` service: tenants, companies, users, roles, permissions.

Owns the organisation model (docs/org-model.md) and is the only service that
writes it. Every other service holds read replicas of the few fields it needs.
"""

__version__ = "0.1.0"
