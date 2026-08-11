from __future__ import annotations

from threading import Event

import pytest

from inspection_platform.worker.heartbeat import LeaseHeartbeat, LeaseLostError


def test_lease_heartbeat_renews_in_a_separate_thread() -> None:
    renewed = Event()

    with LeaseHeartbeat(lambda: renewed.set() or True, interval_seconds=0.01) as heartbeat:
        assert renewed.wait(0.5)
        heartbeat.assert_owned()


def test_lease_heartbeat_fails_closed_after_ownership_loss() -> None:
    attempted = Event()

    def lose_lease() -> bool:
        attempted.set()
        return False

    with LeaseHeartbeat(lose_lease, interval_seconds=0.01) as heartbeat:
        assert attempted.wait(0.5)
        assert heartbeat.wait_until_lost(0.5)
        with pytest.raises(LeaseLostError):
            heartbeat.assert_owned()
