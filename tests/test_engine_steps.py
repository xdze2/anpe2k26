"""Tests for engine Step scan() implementations.

No real LLM or network calls. work() tests use a fake Vault and monkeypatching.
All node fixtures are created in tmp_path so nothing touches user_data/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anpe.engine.queue import Queue
from anpe.engine.steps.base import Candidate
from anpe.engine.vault import Vault


def _make_queue(tmp_path: Path) -> Queue:
    """Scratch queue in tmp_path — satisfies scan(queue, ...) for steps that don't need it."""
    return Queue(db_path=tmp_path / "queue.db")


# ---------------------------------------------------------------------------
# Helpers to build fixture node directories
# ---------------------------------------------------------------------------

def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _make_node(nodes_dir: Path, node_id: str) -> Path:
    p = nodes_dir / node_id
    (p / "raw_data").mkdir(parents=True)
    (p / "summarize").mkdir()
    (p / "eval_results").mkdir()
    return p


def _append_fetch_event(node_path: Path, event: dict) -> None:
    with (node_path / "fetch.jsonl").open("a") as f:
        f.write(json.dumps(event) + "\n")


def _write_sum_file(node_path: Path, filename: str, fetch_uid: str, version: str, summary: str = "summary text") -> None:
    data = {
        "fetch_uid": fetch_uid,
        "summarize_version": version,
        "status": "ok",
        "summary": summary,
        "new_targets": [],
    }
    (node_path / "summarize" / filename).write_text(json.dumps(data), encoding="utf-8")


def _write_eval_file(node_path: Path, filename: str, sum_file: str, profile_file: str, version: str, score: str = "good") -> None:
    data = {
        "sum_file": f"summarize/{sum_file}",
        "profile_file": profile_file,
        "eval_version": version,
        "score": score,
        "fit": "fits well",
        "dealbreakers": [],
        "uncertainty": "low",
    }
    (node_path / "eval_results" / filename).write_text(json.dumps(data), encoding="utf-8")
    # Mirror the eval_queue.jsonl entry the real pipeline would write so
    # NodeDir.get_latest_eval_result() can find this result.
    with (node_path / "eval_queue.jsonl").open("a") as f:
        f.write(json.dumps({"event": "eval_done", "result_file": filename, "ts": _now()}) + "\n")


# ---------------------------------------------------------------------------
# FetchDdgStep.scan()
# ---------------------------------------------------------------------------

class TestFetchDdgStepScan:
    @pytest.fixture(autouse=True)
    def patch_nodes_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        nodes_dir = tmp_path / "nodes"
        nodes_dir.mkdir()
        monkeypatch.setattr("anpe.engine.steps.fetch_ddg.NODES_DIR", nodes_dir)
        self.nodes_dir = nodes_dir
        self.queue = _make_queue(tmp_path)

    def test_empty_when_no_nodes(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        assert FetchDdgStep().scan(self.queue) == []

    def test_pending_ddg_put_is_a_candidate(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        _append_fetch_event(node, {"event": "put", "uid": "u1", "tool": "ddg", "target": "acme corp", "ts": _now()})

        candidates = FetchDdgStep().scan(self.queue)
        assert len(candidates) == 1
        assert candidates[0].node_id == "node_1"
        assert candidates[0].args["tool"] == "ddg"
        assert candidates[0].args["target"] == "acme corp"

    def test_siren_target_ignored(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        _append_fetch_event(node, {"event": "put", "uid": "u1", "tool": "siren", "target": "123456789", "ts": _now()})

        assert FetchDdgStep().scan(self.queue) == []

    def test_fetch_done_not_a_candidate(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        _append_fetch_event(node, {"event": "put", "uid": "u1", "tool": "ddg", "target": "acme", "ts": _now()})
        _append_fetch_event(node, {"event": "fetch_done", "uid": "u1", "raw_file": "raw_ddg_acme.json", "ts": _now()})

        assert FetchDdgStep().scan(self.queue) == []

    def test_summarize_error_is_a_candidate(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        _append_fetch_event(node, {"event": "put", "uid": "u1", "tool": "ddg", "target": "acme", "ts": _now()})
        _append_fetch_event(node, {"event": "fetch_done", "uid": "u1", "raw_file": "r.json", "ts": _now()})
        _append_fetch_event(node, {"event": "summarize_error", "uid": "u1", "detail": "oops", "ts": _now()})

        assert len(FetchDdgStep().scan(self.queue)) == 1

    def test_multiple_nodes_multiple_candidates(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        for name in ("node_a", "node_b"):
            node = _make_node(self.nodes_dir, name)
            _append_fetch_event(node, {"event": "put", "uid": "u1", "tool": "ddg", "target": "t", "ts": _now()})

        assert len(FetchDdgStep().scan(self.queue)) == 2

    def test_listing_from_queue_emits_candidates(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        from anpe.engine.vault import USER_VAULT_DIR

        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        monkeypatch.setattr("anpe.engine.steps.fetch_ddg.USER_VAULT_DIR", vault_dir)

        listing_uri = "_bootstrap/bootstrap/20260508_listing.jsonl"
        listing_path = vault_dir / listing_uri
        listing_path.parent.mkdir(parents=True)
        listing_path.write_text(
            '{"nom_complet": "Acme SA", "siren": "123456789"}\n',
            encoding="utf-8",
        )

        self.queue.put("_bootstrap", "bootstrap", "v2", {"profile_hash": "abc"})
        uid = list(self.queue.pending("bootstrap"))[0].uid
        self.queue.mark_done(uid, "bootstrap", "_bootstrap", {"listing_uri": listing_uri, "count": 1})

        candidates = FetchDdgStep().scan(self.queue)
        assert len(candidates) == 1
        assert candidates[0].args["target"] == "Acme SA"
        assert candidates[0].args["listing_uri"] == listing_uri

    def test_no_listing_when_bootstrap_not_done(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep

        vault_dir = tmp_path / "vault"
        vault_dir.mkdir()
        monkeypatch.setattr("anpe.engine.steps.fetch_ddg.USER_VAULT_DIR", vault_dir)

        self.queue.put("_bootstrap", "bootstrap", "v2", {"profile_hash": "abc"})
        # bootstrap is only put, not done yet

        assert FetchDdgStep().scan(self.queue) == []


# ---------------------------------------------------------------------------
# SummarizeDdgStep.scan()
# ---------------------------------------------------------------------------

class TestSummarizeDdgStepScan:
    @pytest.fixture(autouse=True)
    def patch_nodes_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        nodes_dir = tmp_path / "nodes"
        nodes_dir.mkdir()
        monkeypatch.setattr("anpe.engine.steps.summarize_ddg.NODES_DIR", nodes_dir)
        monkeypatch.setattr("anpe.node_dir.NODES_DIR", nodes_dir)
        self.nodes_dir = nodes_dir
        self.queue = _make_queue(tmp_path)

    def _fetch_done(self, node: Path, uid: str = "u1") -> None:
        _append_fetch_event(node, {"event": "put", "uid": uid, "tool": "ddg", "target": "t", "ts": _now()})
        _append_fetch_event(node, {"event": "fetch_done", "uid": uid, "raw_file": f"raw_ddg_t.json", "ts": _now()})

    def test_empty_when_no_nodes(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        assert SummarizeDdgStep().scan(self.queue) == []

    def test_fetch_done_without_summary_is_candidate(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        self._fetch_done(node)

        candidates = SummarizeDdgStep().scan(self.queue)
        assert len(candidates) == 1
        assert candidates[0].node_id == "node_1"
        assert "raw_uri" in candidates[0].args

    def test_siren_fetch_done_ignored(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        _append_fetch_event(node, {"event": "put", "uid": "u1", "tool": "siren", "target": "123456789", "ts": _now()})
        _append_fetch_event(node, {"event": "fetch_done", "uid": "u1", "raw_file": "raw_siren.json", "ts": _now()})

        assert SummarizeDdgStep().scan(self.queue) == []

    def test_already_summarized_not_a_candidate(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        from anpe.prospect.summarize import SUMMARIZE_VERSION
        node = _make_node(self.nodes_dir, "node_1")
        self._fetch_done(node)
        _write_sum_file(node, "sum_ddg_t_ok_20260508.json", "u1", SUMMARIZE_VERSION)

        assert SummarizeDdgStep().scan(self.queue) == []

    def test_stale_summarize_version_is_candidate(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        self._fetch_done(node)
        _write_sum_file(node, "sum_ddg_t_ok_20260508.json", "u1", "old_version")

        assert len(SummarizeDdgStep().scan(self.queue)) == 1

    def test_pending_target_not_a_candidate(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        _append_fetch_event(node, {"event": "put", "uid": "u1", "tool": "ddg", "target": "t", "ts": _now()})
        # no fetch_done event → fetch not finished yet

        assert SummarizeDdgStep().scan(self.queue) == []

    def test_naf_prefix_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        self._fetch_done(node)
        monkeypatch.setattr("anpe.node_dir.NodeDir.get_siren_meta", lambda self: {"naf": "62.01Z"})

        assert len(SummarizeDdgStep().scan(self.queue, naf_prefix="62")) == 1
        assert SummarizeDdgStep().scan(self.queue, naf_prefix="85") == []


# ---------------------------------------------------------------------------
# EvalStep.scan()
# ---------------------------------------------------------------------------

class TestEvalStepScan:
    @pytest.fixture(autouse=True)
    def patch_nodes_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        nodes_dir = tmp_path / "nodes"
        nodes_dir.mkdir()
        monkeypatch.setattr("anpe.engine.steps.eval.NODES_DIR", nodes_dir)
        monkeypatch.setattr("anpe.node_dir.NODES_DIR", nodes_dir)
        self.nodes_dir = nodes_dir
        self.profile = tmp_path / "profile.md"
        self.profile.write_text("I want X", encoding="utf-8")
        monkeypatch.setattr("anpe.engine.steps.eval.active_profile_file", lambda: self.profile)
        self.queue = _make_queue(tmp_path)

    def _with_summary(self, node_id: str, uid: str = "u1") -> Path:
        from anpe.prospect.registry import FETCH_TOOLS
        version = FETCH_TOOLS["ddg"].version
        node = _make_node(self.nodes_dir, node_id)
        _append_fetch_event(node, {"event": "put", "uid": uid, "tool": "ddg", "target": "t", "ts": _now()})
        _append_fetch_event(node, {"event": "fetch_done", "uid": uid, "raw_file": "r.json", "ts": _now()})
        fname = f"sum_ddg_t_ok_20260508_{uid}.json"
        _write_sum_file(node, fname, uid, version)
        _append_fetch_event(node, {"event": "summarize_done", "uid": uid, "result_file": fname, "ts": _now()})
        return node

    def test_no_profile_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from anpe.engine.steps.eval import EvalStep
        monkeypatch.setattr("anpe.engine.steps.eval.active_profile_file", lambda: None)
        self._with_summary("node_1")
        assert EvalStep().scan(self.queue) == []

    def test_node_with_summary_is_candidate(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        self._with_summary("node_1")
        candidates = EvalStep().scan(self.queue)
        assert len(candidates) == 1
        assert candidates[0].node_id == "node_1"

    def test_node_without_summary_not_a_candidate(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        _make_node(self.nodes_dir, "node_1")
        assert EvalStep().scan(self.queue) == []

    def test_already_evaled_not_a_candidate(self) -> None:
        from anpe.engine.steps.eval import EvalStep, EVAL_VERSION
        node = self._with_summary("node_1")
        sum_file = "sum_ddg_t_ok_20260508_u1.json"
        profile_uri = str(self.profile)
        _write_eval_file(node, "eval_20260508_node_1.json", sum_file, profile_uri, EVAL_VERSION)
        assert EvalStep().scan(self.queue) == []

    def test_stale_eval_version_is_candidate(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        node = self._with_summary("node_1")
        sum_file = "sum_ddg_t_ok_20260508_u1.json"
        _write_eval_file(node, "eval_20260508_node_1.json", sum_file, str(self.profile), "old_version")
        assert len(EvalStep().scan(self.queue)) == 1

    def test_exclude_reaction_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from anpe.engine.steps.eval import EvalStep
        self._with_summary("node_1")
        monkeypatch.setattr(
            "anpe.node_dir.NodeDir.get_latest_review",
            lambda self: {"reaction": "discard"},
        )
        assert EvalStep().scan(self.queue, exclude_reaction="discard") == []
        assert len(EvalStep().scan(self.queue, exclude_reaction="good")) == 1

    def test_min_score_filter_skips_low_score(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        node = self._with_summary("node_1")
        sum_file = "sum_ddg_t_ok_20260508_u1.json"
        _write_eval_file(node, "eval_20260508_node_1.json", sum_file, str(self.profile), "old_version", score="discard")
        assert EvalStep().scan(self.queue, min_score="maybe") == []

    def test_min_score_filter_keeps_high_score(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        node = self._with_summary("node_1")
        sum_file = "sum_ddg_t_ok_20260508_u1.json"
        _write_eval_file(node, "eval_20260508_node_1.json", sum_file, str(self.profile), "old_version", score="good")
        assert len(EvalStep().scan(self.queue, min_score="maybe")) == 1

    def test_no_prior_eval_passes_min_score(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        self._with_summary("node_1")
        assert len(EvalStep().scan(self.queue, min_score="good")) == 1

    def test_context_carries_score_and_reaction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from anpe.engine.steps.eval import EvalStep
        node = self._with_summary("node_1")
        sum_file = "sum_ddg_t_ok_20260508_u1.json"
        _write_eval_file(node, "eval_old.json", sum_file, str(self.profile), "old_version", score="maybe")
        monkeypatch.setattr(
            "anpe.node_dir.NodeDir.get_latest_review",
            lambda self: {"reaction": "good"},
        )
        candidates = EvalStep().scan(self.queue)
        assert candidates[0].context["score"] == "maybe"
        assert candidates[0].context["reaction"] == "good"
