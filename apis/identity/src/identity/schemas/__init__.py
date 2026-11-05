"""Pydantic request and response models.

``extra="forbid"`` on every one, and an ORM object is never constructed from
unvalidated request data (CLAUDE.md §5.6).
"""
