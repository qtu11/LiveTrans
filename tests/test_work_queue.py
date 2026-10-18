import threading
import time

import numpy as np

from livetrans.segmenter import Final, Partial
from livetrans.work_queue import WorkQueue

A = np.zeros(10, dtype=np.float32)


def test_final_before_partial():
    q = WorkQueue()
    q.put(Partial("mic", 1, A))
    q.put(Final("loopback", 5, A))
    first = q.get(0)
    assert isinstance(first, Final) and first.seg_id == 5
    assert isinstance(q.get(0), Partial)
    assert q.get(0) is None


def test_finals_fifo():
    q = WorkQueue()
    q.put(Final("mic", 1, A))
    q.put(Final("mic", 2, A))
    assert [q.get(0).seg_id, q.get(0).seg_id] == [1, 2]


def test_partial_replaced_by_newer_same_source():
    q = WorkQueue()
    q.put(Partial("mic", 1, A))
    newer = Partial("mic", 1, A)
    q.put(newer)
    q.put(Partial("loopback", 7, A))
    got = [q.get(0), q.get(0), q.get(0)]
    assert got[0] is newer
    assert got[1].source == "loopback"
    assert got[2] is None


def test_partial_dropped_after_final_same_segment():
    q = WorkQueue()
    q.put(Partial("mic", 3, A))
    q.put(Final("mic", 3, A))
    q.put(Partial("mic", 3, A))  # đến muộn
    assert isinstance(q.get(0), Final)
    assert q.get(0) is None


def test_final_removes_older_pending_partial():
    q = WorkQueue()
    q.put(Partial("mic", 2, A))
    q.put(Final("mic", 3, A))
    assert isinstance(q.get(0), Final)
    assert q.get(0) is None


def test_get_timeout_returns_none():
    q = WorkQueue()
    t0 = time.monotonic()
    assert q.get(0.1) is None
    assert time.monotonic() - t0 >= 0.09


def test_close_unblocks_get():
    q = WorkQueue()
    result = []
    t = threading.Thread(target=lambda: result.append(q.get(None)))
    t.start()
    time.sleep(0.05)
    q.close()
    t.join(1)
    assert not t.is_alive() and result == [None]


def test_clear_partials_only():
    q = WorkQueue()
    q.put(Final("mic", 1, A))
    q.put(Partial("loopback", 1, A))
    q.clear(partials_only=True)
    assert isinstance(q.get(0), Final)
    assert q.get(0) is None
