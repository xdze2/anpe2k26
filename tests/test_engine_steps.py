"""Tests for engine Step scan() implementations.

No real LLM or network calls. work() tests use a fake Vault and monkeypatching.
All node fixtures are created in tmp_path so nothing touches user_data/.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from anpe.engine.queue import Queue
from anpe.engine.base import Candidate
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
# FetchSirenStep.scan()
# ---------------------------------------------------------------------------

_SIREN_RAW = json.dumps({
    "nom_complet": "Acme SA",
    "siren": "123456789",
    "activite_principale": "62.01Z",
    "section_activite_principale": "J",
    "siege": {"nom_commercial": "Acme", "libelle_commune": "Paris"},
})


class TestFetchSirenStepScan:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        self.queue = _make_queue(tmp_path)
        self.vault = _make_vault(tmp_path)

    def _put_bootstrap_done(self, listing_jsonl: str) -> str:
        listing_uri = self.vault.store("_bootstrap", "bootstrap", "listing", "jsonl", listing_jsonl.encode())
        self.queue.put("_bootstrap", "bootstrap", "v2", {"profile_hash": "abc"})
        uid = list(self.queue.pending("bootstrap"))[0].uid
        self.queue.mark_done(uid, "bootstrap", "_bootstrap", {"listing_uri": listing_uri, "count": 1})
        return listing_uri

    def test_empty_when_no_bootstrap(self) -> None:
        from anpe.steps.fetch_siren_step import FetchSirenStep
        assert FetchSirenStep().scan(self.queue, self.vault) == []

    def test_bootstrap_not_done_returns_empty(self) -> None:
        from anpe.steps.fetch_siren_step import FetchSirenStep
        self.queue.put("_bootstrap", "bootstrap", "v2", {"profile_hash": "abc"})
        assert FetchSirenStep().scan(self.queue, self.vault) == []

    def test_listing_emits_candidate(self) -> None:
        from anpe.steps.fetch_siren_step import FetchSirenStep
        listing_uri = self._put_bootstrap_done('{"nom_complet": "Acme SA", "siren": "123456789"}\n')

        candidates = FetchSirenStep().scan(self.queue, self.vault)
        assert len(candidates) == 1
        assert candidates[0].args["target"] == "123456789"
        assert candidates[0].args["listing_uri"] == listing_uri

    def test_already_done_not_a_candidate(self) -> None:
        from anpe.steps.fetch_siren_step import FetchSirenStep
        self._put_bootstrap_done('{"nom_complet": "Acme SA", "siren": "123456789"}\n')

        step = FetchSirenStep()
        candidates = step.scan(self.queue, self.vault)
        assert len(candidates) == 1

        c = candidates[0]
        self.queue.put(c.node_id, step.name, step.version, c.args)
        uid = list(self.queue.pending(step.name))[0].uid
        self.queue.mark_done(uid, step.name, c.node_id, {"raw_uri": "some/uri", "siren": "123456789"})

        assert step.scan(self.queue, self.vault) == []

    def test_count_caps_candidates(self) -> None:
        from anpe.steps.fetch_siren_step import FetchSirenStep
        lines = "\n".join(
            json.dumps({"nom_complet": f"Co {i}", "siren": f"10000000{i}"})
            for i in range(5)
        )
        self._put_bootstrap_done(lines + "\n")
        assert len(FetchSirenStep().scan(self.queue, self.vault, count=3)) == 3

    def test_multiple_companies_all_emitted(self) -> None:
        from anpe.steps.fetch_siren_step import FetchSirenStep
        lines = "\n".join(
            json.dumps({"nom_complet": f"Co {i}", "siren": f"10000000{i}"})
            for i in range(3)
        )
        self._put_bootstrap_done(lines + "\n")
        assert len(FetchSirenStep().scan(self.queue, self.vault)) == 3


# ---------------------------------------------------------------------------
# FetchDdgStep.scan()
# ---------------------------------------------------------------------------

class TestFetchDdgStepScan:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        self.queue = _make_queue(tmp_path)
        self.vault = _make_vault(tmp_path)

    def _put_siren_done(self, node_id: str = "acme_sa_123456789", siren: str = "123456789") -> str:
        """Store siren raw JSON in vault, mark fetch_siren done, return the siren_uri."""
        siren_uri = self.vault.store(node_id, "fetch_siren", node_id[:8], "json", _SIREN_RAW.encode())
        args = {"node_id": node_id, "tool": "siren", "target": siren, "listing_uri": "bootstrap/listing.jsonl"}
        self.queue.put(node_id, "fetch_siren", "v1", args)
        uid = list(self.queue.pending("fetch_siren"))[0].uid
        self.queue.mark_done(uid, "fetch_siren", node_id, {"raw_uri": siren_uri, "siren": siren})
        return siren_uri

    def test_empty_when_no_siren_done(self) -> None:
        from anpe.steps.fetch_ddg_step import FetchDdgStep
        assert FetchDdgStep().scan(self.queue, self.vault) == []

    def test_siren_done_emits_candidate(self) -> None:
        from anpe.steps.fetch_ddg_step import FetchDdgStep
        siren_uri = self._put_siren_done()

        candidates = FetchDdgStep().scan(self.queue, self.vault)
        assert len(candidates) == 1
        assert candidates[0].args["siren_uri"] == siren_uri
        assert candidates[0].args["target"] == "Acme entreprise informatique"

    def test_already_done_not_a_candidate(self) -> None:
        from anpe.steps.fetch_ddg_step import FetchDdgStep
        self._put_siren_done()

        step = FetchDdgStep()
        candidates = step.scan(self.queue, self.vault)
        assert len(candidates) == 1

        c = candidates[0]
        self.queue.put(c.node_id, step.name, step.version, c.args)
        uid = list(self.queue.pending(step.name))[0].uid
        self.queue.mark_done(uid, step.name, c.node_id, {"raw_uri": "some/raw_ddg.json"})

        assert step.scan(self.queue, self.vault) == []

    def test_count_caps_candidates(self) -> None:
        from anpe.steps.fetch_ddg_step import FetchDdgStep
        for i in range(5):
            self._put_siren_done(node_id=f"co_{i}_10000000{i}", siren=f"10000000{i}")
        assert len(FetchDdgStep().scan(self.queue, self.vault, count=3)) == 3

    def test_multiple_companies_all_emitted(self) -> None:
        from anpe.steps.fetch_ddg_step import FetchDdgStep
        for i in range(3):
            self._put_siren_done(node_id=f"co_{i}_10000000{i}", siren=f"10000000{i}")
        assert len(FetchDdgStep().scan(self.queue, self.vault)) == 3


# ---------------------------------------------------------------------------
# SummarizeDdgStep.scan()
# ---------------------------------------------------------------------------

class TestSummarizeDdgStepScan:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        self.queue = _make_queue(tmp_path)
        self.vault = _make_vault(tmp_path)

    def _put_fetch_ddg_done(self, node_id: str = "acme_sa_123456789") -> tuple[str, str]:
        """Set up a completed fetch_siren + fetch_ddg chain. Returns (siren_uri, raw_ddg_uri)."""
        siren_uri = self.vault.store(node_id, "fetch_siren", node_id[:8], "json", _SIREN_RAW.encode())
        raw_ddg_uri = self.vault.store(node_id, "fetch_ddg", node_id[:8], "json", b'{"results": []}')

        ddg_args = {"node_id": node_id, "tool": "ddg", "target": "Acme entreprise informatique", "siren_uri": siren_uri}
        self.queue.put(node_id, "fetch_ddg", "v1", ddg_args)
        uid = list(self.queue.pending("fetch_ddg"))[0].uid
        self.queue.mark_done(uid, "fetch_ddg", node_id, {"raw_uri": raw_ddg_uri, "tool": "ddg", "siren_uri": siren_uri})
        return siren_uri, raw_ddg_uri

    def test_empty_when_no_fetch_ddg_done(self) -> None:
        from anpe.steps.summarize_ddg_step import SummarizeDdgStep
        assert SummarizeDdgStep().scan(self.queue, self.vault) == []

    def test_fetch_ddg_done_emits_candidate(self) -> None:
        from anpe.steps.summarize_ddg_step import SummarizeDdgStep
        siren_uri, raw_ddg_uri = self._put_fetch_ddg_done()

        candidates = SummarizeDdgStep().scan(self.queue, self.vault)
        assert len(candidates) == 1
        assert candidates[0].node_id == "acme_sa_123456789"
        assert candidates[0].args["raw_ddg_uri"] == raw_ddg_uri
        assert candidates[0].args["siren_uri"] == siren_uri

    def test_already_done_not_a_candidate(self) -> None:
        from anpe.steps.summarize_ddg_step import SummarizeDdgStep
        self._put_fetch_ddg_done()

        step = SummarizeDdgStep()
        candidates = step.scan(self.queue, self.vault)
        assert len(candidates) == 1

        c = candidates[0]
        self.queue.put(c.node_id, step.name, step.version, c.args)
        uid = list(self.queue.pending(step.name))[0].uid
        self.queue.mark_done(uid, step.name, c.node_id, {"status": "ok"})

        assert step.scan(self.queue, self.vault) == []

    def test_multiple_nodes_all_emitted(self) -> None:
        from anpe.steps.summarize_ddg_step import SummarizeDdgStep
        for i in range(3):
            self._put_fetch_ddg_done(node_id=f"co_{i}")
        assert len(SummarizeDdgStep().scan(self.queue, self.vault)) == 3


# ---------------------------------------------------------------------------
# EvalStep.scan()
# ---------------------------------------------------------------------------

class TestEvalStepScan:
    @pytest.fixture(autouse=True)
    def setup(self, tmp_path: Path) -> None:
        self.queue = _make_queue(tmp_path)
        self.vault = _make_vault(tmp_path)

    def _seed_profile(self) -> None:
        """Write user_preference.md into the scratch vault root."""
        self.vault.root.mkdir(parents=True, exist_ok=True)
        (self.vault.root / "user_preference.md").write_bytes(b"I want X")

    def _put_summarize_ddg_done(self, node_id: str = "acme_sa_123456789", summary: str = "ok summary") -> str:
        """Store a summary in the vault and record a summarize_ddg done event. Returns summary_uri."""
        summary_uri = self.vault.store(
            node_id, "summarize_ddg", node_id[:8], "json",
            json.dumps({"summary": summary, "status": "ok"}).encode(),
        )
        args = {"node_id": node_id, "raw_ddg_uri": "x/fetch_ddg/raw.json", "siren_uri": "x/fetch_siren/s.json"}
        self.queue.put(node_id, "summarize_ddg", "v_test", args)
        uid = list(self.queue.pending("summarize_ddg"))[0].uid
        self.queue.mark_done(uid, "summarize_ddg", node_id, {"summary_uri": summary_uri})
        return summary_uri

    def test_no_profile_returns_empty(self) -> None:
        from anpe.steps.eval_step import EvalStep
        self._put_summarize_ddg_done()
        assert EvalStep().scan(self.queue, self.vault) == []

    def test_summarize_done_is_candidate(self) -> None:
        from anpe.steps.eval_step import EvalStep
        self._seed_profile()
        summary_uri = self._put_summarize_ddg_done()
        candidates = EvalStep().scan(self.queue, self.vault)
        assert len(candidates) == 1
        assert candidates[0].node_id == "acme_sa_123456789"
        assert candidates[0].args["summary_uri"] == summary_uri
        assert candidates[0].args["profile_uri"] == "user_preference.md"

    def test_no_summarize_done_returns_empty(self) -> None:
        from anpe.steps.eval_step import EvalStep
        self._seed_profile()
        assert EvalStep().scan(self.queue, self.vault) == []

    def test_summarize_done_missing_summary_uri_skipped(self) -> None:
        from anpe.steps.eval_step import EvalStep
        self._seed_profile()
        args = {"node_id": "acme_sa_123456789", "raw_ddg_uri": "x", "siren_uri": "y"}
        self.queue.put("acme_sa_123456789", "summarize_ddg", "v_test", args)
        uid = list(self.queue.pending("summarize_ddg"))[0].uid
        self.queue.mark_done(uid, "summarize_ddg", "acme_sa_123456789", {"status": "ok"})
        assert EvalStep().scan(self.queue, self.vault) == []

    def test_already_evaled_not_a_candidate(self) -> None:
        from anpe.steps.eval_step import EvalStep
        self._seed_profile()
        summary_uri = self._put_summarize_ddg_done()

        step = EvalStep()
        candidates = step.scan(self.queue, self.vault)
        assert len(candidates) == 1

        c = candidates[0]
        self.queue.put(c.node_id, step.name, step.version, c.args)
        uid = list(self.queue.pending(step.name))[0].uid
        self.queue.mark_done(uid, step.name, c.node_id, {"score": "good"})

        assert step.scan(self.queue, self.vault) == []

    def test_multiple_nodes_all_emitted(self) -> None:
        from anpe.steps.eval_step import EvalStep
        self._seed_profile()
        for i in range(3):
            self._put_summarize_ddg_done(node_id=f"co_{i}")
        assert len(EvalStep().scan(self.queue, self.vault)) == 3
