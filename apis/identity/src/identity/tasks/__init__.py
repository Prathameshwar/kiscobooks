"""Celery tasks: the outbox poller, licence-expiry sweep, impersonation sweeper.

CPU-bound or long-running work goes here, never inline in a request (rule 4.10).
"""
