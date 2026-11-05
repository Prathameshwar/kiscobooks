"""Re-runnable seed data for the ``identity`` database.

Seeds live outside migrations (CLAUDE.md §2): a migration carrying content runs once,
in one environment, and cannot be corrected. The thin CLI shims under the repo's
``seeds/`` directory call into here, where the mechanism can be imported and tested.
"""
