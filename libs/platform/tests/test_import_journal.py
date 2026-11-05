import pytest

from billing_platform.import_journal import StepBudget


def test_steps_checkpoint_before_count_or_time_budget_expires(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr("billing_platform.import_journal.time.monotonic", lambda: clock[0])
    step = StepBudget(2, 10)
    assert step.take() and step.take() and not step.take()
    next_step = StepBudget(20, 10)
    assert next_step.take()
    clock[0] = 111.0
    assert not next_step.alive() and not next_step.take()


@pytest.mark.parametrize("count,seconds", [(0, 30), (201, 30), (20, 0), (20, 46)])
def test_step_limits_cannot_be_bypassed(count, seconds):
    with pytest.raises(ValueError):
        StepBudget(count, seconds)
