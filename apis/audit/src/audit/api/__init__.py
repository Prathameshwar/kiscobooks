"""HTTP surface for `audit`: the read trail, activity feed, security surface, and export.

Routes stay thin (CLAUDE.md §4) — verify the actor, resolve object-level scope, run the
lean list query, project. There is no write route: events arrive over the broker only
(docs/audit.md §7 decision).
"""
