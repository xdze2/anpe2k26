import pytest
from pathlib import Path
from anpe.engine.queue import Queue


@pytest.fixture
def queue(tmp_path: Path) -> Queue:
    q = Queue(db_path=tmp_path / "queue.db")
    yield q
    q.close()


# --- put / idempotency ---

def test_put_returns_uid(queue: Queue) -> None:
    uid = queue.put("node_1", "eval", "v1", {"sum_uri": "a/b/c.json"})
    assert uid and isinstance(uid, str)


def test_put_idempotent(queue: Queue) -> None:
    args = {"sum_uri": "a/b/c.json"}
    uid1 = queue.put("node_1", "eval", "v1", args)
    uid2 = queue.put("node_1", "eval", "v1", args)
    assert uid1 == uid2
    assert len(queue.pending("eval")) == 1


def test_put_force_creates_distinct_item(queue: Queue) -> None:
    args = {"sum_uri": "a/b/c.json"}
    uid1 = queue.put("node_1", "eval", "v1", args)
    uid2 = queue.put("node_1", "eval", "v1", args, force=True)
    assert uid1 != uid2
    assert len(queue.pending("eval")) == 2


def test_different_args_produce_different_uid(queue: Queue) -> None:
    uid1 = queue.put("node_1", "eval", "v1", {"sum_uri": "a.json"})
    uid2 = queue.put("node_1", "eval", "v1", {"sum_uri": "b.json"})
    assert uid1 != uid2


# --- pending / claim ---

def test_pending_empty_at_start(queue: Queue) -> None:
    assert queue.pending("eval") == []


def test_pending_after_put(queue: Queue) -> None:
    queue.put("node_1", "eval", "v1", {"k": "v"})
    items = queue.pending("eval")
    assert len(items) == 1
    assert items[0].node_id == "node_1"
    assert items[0].step == "eval"
    assert items[0].args == {"k": "v"}


def test_claim_returns_item(queue: Queue) -> None:
    queue.put("node_1", "eval", "v1", {"k": "v"})
    item = queue.claim("eval", worker_id="w1")
    assert item is not None
    assert item.node_id == "node_1"


def test_claim_removes_from_pending(queue: Queue) -> None:
    queue.put("node_1", "eval", "v1", {"k": "v"})
    queue.claim("eval", worker_id="w1")
    assert queue.pending("eval") == []


def test_claim_empty_returns_none(queue: Queue) -> None:
    assert queue.claim("eval", worker_id="w1") is None


def test_two_claims_only_one_wins(queue: Queue) -> None:
    queue.put("node_1", "eval", "v1", {"k": "v"})
    item1 = queue.claim("eval", worker_id="w1")
    item2 = queue.claim("eval", worker_id="w2")
    assert item1 is not None
    assert item2 is None


# --- mark_done / mark_error ---

def test_mark_done_removes_from_pending(queue: Queue) -> None:
    uid = queue.put("node_1", "eval", "v1", {"k": "v"})
    item = queue.claim("eval", worker_id="w1")
    assert item is not None
    queue.mark_done(item.uid, item.step, item.node_id, {"score": 8})
    assert queue.pending("eval") == []


def test_mark_error_retry_re_appears_in_pending(queue: Queue) -> None:
    uid = queue.put("node_1", "eval", "v1", {"k": "v"})
    item = queue.claim("eval", worker_id="w1")
    assert item is not None
    queue.mark_error(item.uid, item.step, item.node_id, "timeout", retryable=True)
    items = queue.pending("eval")
    assert len(items) == 1
    assert items[0].uid == uid


def test_mark_error_abort_not_in_pending(queue: Queue) -> None:
    queue.put("node_1", "eval", "v1", {"k": "v"})
    item = queue.claim("eval", worker_id="w1")
    assert item is not None
    queue.mark_error(item.uid, item.step, item.node_id, "fatal", retryable=False)
    assert queue.pending("eval") == []


# --- stale_claims ---

def test_stale_claims_empty_when_fresh(queue: Queue) -> None:
    queue.put("node_1", "eval", "v1", {"k": "v"})
    queue.claim("eval", worker_id="w1")
    # claimed right now — not stale yet
    assert queue.stale_claims("eval", older_than_s=300) == []


def test_stale_claims_detected_with_zero_threshold(queue: Queue) -> None:
    queue.put("node_1", "eval", "v1", {"k": "v"})
    item = queue.claim("eval", worker_id="w1")
    assert item is not None
    stale = queue.stale_claims("eval", older_than_s=0)
    assert len(stale) == 1
    assert stale[0].uid == item.uid


# --- step isolation ---

def test_pending_is_step_scoped(queue: Queue) -> None:
    queue.put("node_1", "eval", "v1", {"k": "v"})
    queue.put("node_2", "summarize", "v1", {"raw_uri": "x"})
    assert len(queue.pending("eval")) == 1
    assert len(queue.pending("summarize")) == 1
    assert queue.claim("eval", "w") is not None
    assert queue.claim("summarize", "w") is not None
