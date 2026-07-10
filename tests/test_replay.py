import pytest

from src.protocol.replay import ReplayWindow


def test_first_packet_accepted():
    w = ReplayWindow()
    assert w.check(0) is True
    assert w.check(0) is False


def test_increasing_accepted():
    w = ReplayWindow()
    assert all(w.check(i) for i in range(1, 100))


def test_duplicate_rejected():
    w = ReplayWindow()
    assert w.check(5) is True
    assert w.check(5) is False


def test_old_out_of_window_rejected():
    w = ReplayWindow()
    assert w.check(100) is True
    assert w.check(30) is False
    assert w.check(50) is True
    assert w.check(50) is False


def test_within_window_accepted_once():
    w = ReplayWindow()
    assert w.check(100) is True
    assert w.check(80) is True
    assert w.check(80) is False
    assert w.check(100) is False


def test_negative_rejected():
    w = ReplayWindow()
    assert w.check(-1) is False


def test_window_size_bounds():
    with pytest.raises(ValueError):
        ReplayWindow(0)
    with pytest.raises(ValueError):
        ReplayWindow(65)
    assert ReplayWindow(64).window_size == 64


def test_reset():
    w = ReplayWindow()
    assert w.check(10) is True
    w.reset()
    assert w.check(10) is True
