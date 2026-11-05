"""Event payloads published by `identity`, and the consumers it subscribes to.

Publishing goes through the outbox in the same transaction as the state change,
never directly after commit (CLAUDE.md invariant 10).
"""
