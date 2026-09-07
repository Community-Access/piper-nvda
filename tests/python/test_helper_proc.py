"""Restart handling in the helper process manager.

The watchdog (on a hang) and the dead process's reader thread (on the EOF
the watchdog's kill causes) both report the same death. These tests pin the
guarantees: one report wins and the other is a no-op, the reported process
is always killed, and giving up leaves nothing to write into.
"""

import time

import pytest

from synthDrivers.piper import _helperProc


class FakeProc:
    def __init__(self):
        self.killed = 0
        self.stdin = None
        self.stdout = None

    def kill(self):
        self.killed += 1


@pytest.fixture
def hp(monkeypatch):
    hp = _helperProc.HelperProcess("piper-helper.exe", [],
                                   on_frame=lambda *a: None)
    monkeypatch.setattr(_helperProc.time, "sleep", lambda s: None)
    spawned = []

    def fake_spawn():
        hp._proc = FakeProc()
        hp._alive = True
        spawned.append(hp._proc)

    monkeypatch.setattr(hp, "_spawn", fake_spawn)
    hp.spawned = spawned
    return hp


def test_death_restarts_once_and_kills_the_dead_process(hp):
    old = FakeProc()
    hp._proc = old
    hp._handle_death(old)
    assert old.killed == 1
    assert len(hp.spawned) == 1
    assert hp._proc is hp.spawned[0]


def test_second_report_of_the_same_death_is_a_noop(hp):
    """After the watchdog restarts, the old reader thread reports the same
    process again; it must not kill the replacement or restart again."""
    old = FakeProc()
    hp._proc = old
    hp._handle_death(old)
    replacement = hp._proc
    hp._handle_death(old)
    assert len(hp.spawned) == 1
    assert hp._proc is replacement
    assert replacement.killed == 0
    # And the restart budget was charged once, not twice.
    assert len(hp._restart_times) == 1


def test_giving_up_kills_the_hung_process_and_fails_sends_fast(hp):
    hung = FakeProc()
    hp._proc = hung
    now = time.monotonic()
    hp._restart_times = [now, now, now]
    hp._handle_death(hung)
    assert hung.killed == 1, "a hung helper must not be left running"
    assert hp._proc is None
    assert hp._gave_up
    assert hp.spawned == []
    with pytest.raises(IOError):
        hp.send(0x05, {})


def test_on_restart_fires_after_a_restart(monkeypatch):
    calls = []
    hp = _helperProc.HelperProcess("piper-helper.exe", [],
                                   on_frame=lambda *a: None,
                                   on_restart=lambda: calls.append(1))
    monkeypatch.setattr(_helperProc.time, "sleep", lambda s: None)
    monkeypatch.setattr(hp, "_spawn",
                        lambda: setattr(hp, "_proc", FakeProc()))
    old = FakeProc()
    hp._proc = old
    hp._handle_death(old)
    assert calls == [1]
