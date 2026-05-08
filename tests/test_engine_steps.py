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
    """Scratch queue in tmp_path."""
    return Queue(db_path=tmp_path / "queue.db")


def _make_vault(tmp_path: Path) -> Vault:
    """Scratch vault in tmp_path."""
    return Vault(root=tmp_path / "vault")


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
    def setup(self, tmp_path: Path) -> None:
        self.queue = _make_queue(tmp_path)
        self.vault = _make_vault(tmp_path)

    def _put_bootstrap_done(self, listing_jsonl: str) -> str:
        """Store a listing in the vault, mark bootstrap done, return the listing_uri."""
        listing_uri = self.vault.store("_bootstrap", "bootstrap", "listing", "jsonl", listing_jsonl.encode())
        self.queue.put("_bootstrap", "bootstrap", "v2", {"profile_hash": "abc"})
        uid = list(self.queue.pending("bootstrap"))[0].uid
        self.queue.mark_done(uid, "bootstrap", "_bootstrap", {"listing_uri": listing_uri, "count": 1})
        return listing_uri

    def test_empty_when_no_bootstrap(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        assert FetchDdgStep().scan(self.queue, self.vault) == []

    def test_bootstrap_not_done_returns_empty(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        self.queue.put("_bootstrap", "bootstrap", "v2", {"profile_hash": "abc"})
        assert FetchDdgStep().scan(self.queue, self.vault) == []

    def test_listing_emits_candidate(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        listing_uri = self._put_bootstrap_done('{"nom_complet": "Acme SA", "siren": "123456789"}\n')

        candidates = FetchDdgStep().scan(self.queue, self.vault)
        assert len(candidates) == 1
        assert candidates[0].args["target"] == "Acme SA"
        assert candidates[0].args["listing_uri"] == listing_uri

    def test_already_done_not_a_candidate(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        from anpe.prospect.seed import node_id_for
        self._put_bootstrap_done('{"nom_complet": "Acme SA", "siren": "123456789"}\n')

        step = FetchDdgStep()
        candidates = FetchDdgStep().scan(self.queue, self.vault)
        assert len(candidates) == 1

        # simulate a completed fetch_ddg run
        c = candidates[0]
        self.queue.put(c.node_id, step.name, step.version, c.args)
        uid = list(self.queue.pending(step.name))[0].uid
        self.queue.mark_done(uid, step.name, c.node_id, {"raw_uri": "some/uri"})

        assert FetchDdgStep().scan(self.queue, self.vault) == []

    def test_count_caps_candidates(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        lines = "\n".join(
            json.dumps({"nom_complet": f"Co {i}", "siren": f"10000000{i}"})
            for i in range(5)
        )
        self._put_bootstrap_done(lines + "\n")

        candidates = FetchDdgStep().scan(self.queue, self.vault, count=3)
        assert len(candidates) == 3

    def test_multiple_companies_all_emitted(self) -> None:
        from anpe.engine.steps.fetch_ddg import FetchDdgStep
        lines = "\n".join(
            json.dumps({"nom_complet": f"Co {i}", "siren": f"10000000{i}"})
            for i in range(3)
        )
        self._put_bootstrap_done(lines + "\n")

        assert len(FetchDdgStep().scan(self.queue, self.vault)) == 3


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
        self.vault = _make_vault(tmp_path)

    def _fetch_done(self, node: Path, uid: str = "u1") -> None:
        _append_fetch_event(node, {"event": "put", "uid": uid, "tool": "ddg", "target": "t", "ts": _now()})
        _append_fetch_event(node, {"event": "fetch_done", "uid": uid, "raw_file": f"raw_ddg_t.json", "ts": _now()})

    def test_empty_when_no_nodes(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        assert SummarizeDdgStep().scan(self.queue, self.vault) == []

    def test_fetch_done_without_summary_is_candidate(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        self._fetch_done(node)

        candidates = SummarizeDdgStep().scan(self.queue, self.vault)
        assert len(candidates) == 1
        assert candidates[0].node_id == "node_1"
        assert "raw_uri" in candidates[0].args

    def test_siren_fetch_done_ignored(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        _append_fetch_event(node, {"event": "put", "uid": "u1", "tool": "siren", "target": "123456789", "ts": _now()})
        _append_fetch_event(node, {"event": "fetch_done", "uid": "u1", "raw_file": "raw_siren.json", "ts": _now()})

        assert SummarizeDdgStep().scan(self.queue, self.vault) == []

    def test_already_summarized_not_a_candidate(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        from anpe.prospect.summarize import SUMMARIZE_VERSION
        node = _make_node(self.nodes_dir, "node_1")
        self._fetch_done(node)
        _write_sum_file(node, "sum_ddg_t_ok_20260508.json", "u1", SUMMARIZE_VERSION)

        assert SummarizeDdgStep().scan(self.queue, self.vault) == []

    def test_stale_summarize_version_is_candidate(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        self._fetch_done(node)
        _write_sum_file(node, "sum_ddg_t_ok_20260508.json", "u1", "old_version")

        assert len(SummarizeDdgStep().scan(self.queue, self.vault)) == 1

    def test_pending_target_not_a_candidate(self) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        _append_fetch_event(node, {"event": "put", "uid": "u1", "tool": "ddg", "target": "t", "ts": _now()})
        # no fetch_done event → fetch not finished yet

        assert SummarizeDdgStep().scan(self.queue, self.vault) == []

    def test_naf_prefix_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from anpe.engine.steps.summarize_ddg import SummarizeDdgStep
        node = _make_node(self.nodes_dir, "node_1")
        self._fetch_done(node)
        monkeypatch.setattr("anpe.node_dir.NodeDir.get_siren_meta", lambda self: {"naf": "62.01Z"})

        assert len(SummarizeDdgStep().scan(self.queue, self.vault, naf_prefix="62")) == 1
        assert SummarizeDdgStep().scan(self.queue, self.vault, naf_prefix="85") == []


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
        self.vault = _make_vault(tmp_path)

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
        assert EvalStep().scan(self.queue, self.vault) == []

    def test_node_with_summary_is_candidate(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        self._with_summary("node_1")
        candidates = EvalStep().scan(self.queue, self.vault)
        assert len(candidates) == 1
        assert candidates[0].node_id == "node_1"

    def test_node_without_summary_not_a_candidate(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        _make_node(self.nodes_dir, "node_1")
        assert EvalStep().scan(self.queue, self.vault) == []

    def test_already_evaled_not_a_candidate(self) -> None:
        from anpe.engine.steps.eval import EvalStep, EVAL_VERSION
        node = self._with_summary("node_1")
        sum_file = "sum_ddg_t_ok_20260508_u1.json"
        profile_uri = str(self.profile)
        _write_eval_file(node, "eval_20260508_node_1.json", sum_file, profile_uri, EVAL_VERSION)
        assert EvalStep().scan(self.queue, self.vault) == []

    def test_stale_eval_version_is_candidate(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        node = self._with_summary("node_1")
        sum_file = "sum_ddg_t_ok_20260508_u1.json"
        _write_eval_file(node, "eval_20260508_node_1.json", sum_file, str(self.profile), "old_version")
        assert len(EvalStep().scan(self.queue, self.vault)) == 1

    def test_exclude_reaction_filter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from anpe.engine.steps.eval import EvalStep
        self._with_summary("node_1")
        monkeypatch.setattr(
            "anpe.node_dir.NodeDir.get_latest_review",
            lambda self: {"reaction": "discard"},
        )
        assert EvalStep().scan(self.queue, self.vault, exclude_reaction="discard") == []
        assert len(EvalStep().scan(self.queue, self.vault, exclude_reaction="good")) == 1

    def test_min_score_filter_skips_low_score(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        node = self._with_summary("node_1")
        sum_file = "sum_ddg_t_ok_20260508_u1.json"
        _write_eval_file(node, "eval_20260508_node_1.json", sum_file, str(self.profile), "old_version", score="discard")
        assert EvalStep().scan(self.queue, self.vault, min_score="maybe") == []

    def test_min_score_filter_keeps_high_score(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        node = self._with_summary("node_1")
        sum_file = "sum_ddg_t_ok_20260508_u1.json"
        _write_eval_file(node, "eval_20260508_node_1.json", sum_file, str(self.profile), "old_version", score="good")
        assert len(EvalStep().scan(self.queue, self.vault, min_score="maybe")) == 1

    def test_no_prior_eval_passes_min_score(self) -> None:
        from anpe.engine.steps.eval import EvalStep
        self._with_summary("node_1")
        assert len(EvalStep().scan(self.queue, self.vault, min_score="good")) == 1

    def test_context_carries_score_and_reaction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from anpe.engine.steps.eval import EvalStep
        node = self._with_summary("node_1")
        sum_file = "sum_ddg_t_ok_20260508_u1.json"
        _write_eval_file(node, "eval_old.json", sum_file, str(self.profile), "old_version", score="maybe")
        monkeypatch.setattr(
            "anpe.node_dir.NodeDir.get_latest_review",
            lambda self: {"reaction": "good"},
        )
        candidates = EvalStep().scan(self.queue, self.vault)
        assert candidates[0].context["score"] == "maybe"
        assert candidates[0].context["reaction"] == "good"
