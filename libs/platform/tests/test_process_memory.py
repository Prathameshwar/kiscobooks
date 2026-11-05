from billing_platform.process_memory import peak_rss


def test_own_process_peak_memory_is_positive_bytes_and_monotonic():
    before = peak_rss()
    assert isinstance(before, int) and before > 0
    allocation = bytearray(1024 * 1024)
    assert peak_rss() >= before
    assert len(allocation) == 1024 * 1024
