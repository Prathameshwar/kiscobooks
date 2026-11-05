from billing_platform.rate_limit import WindowLimiter
import pytest


def test_window_is_bounded_and_recovers_without_growing_memory():
    now = [0.0]
    limiter = WindowLimiter(capacity=2, clock=lambda: now[0])
    assert limiter.allow("a", limit=2)
    assert limiter.allow("a", limit=2)
    assert not limiter.allow("a", limit=2)
    assert limiter.allow("b", limit=2)
    assert not limiter.allow("c", limit=2)
    now[0] = 60
    assert limiter.allow("c", limit=2)
    assert len(limiter._windows) == 1
    with pytest.raises(ValueError):
        limiter.allow("a", limit=0)
