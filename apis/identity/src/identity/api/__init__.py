"""HTTP routes. Thin by rule: validate, call ``domain``, return.

Every route declares a required permission. A route without one carries an
explicit public marker and a comment saying why (CLAUDE.md §5.1).
"""
