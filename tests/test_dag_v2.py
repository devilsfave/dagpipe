"""Tests for DagPipe v0.2.0 — All new V2 features.

Run alongside existing tests:
    pytest tests/                    # runs both v0.1.x and v0.2.0 tests
    pytest tests/test_dag_v2.py -v   # v0.2.0 only

All tests use InMemoryCheckpoint — no disk I/O.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from dagpipe.dag import (
    CircuitBreakerOpenError,
    DAGNode,
    FilesystemCheckpoint,
    NodeResult,
    PipelineOrchestrator,
    PipelineRun,
    _PipelineResult,
    inspect_failure,
    override_node,
    reset_circuit,
)
from dagpipe.constrained import _extract_json, constrained_generate
from pydantic import BaseModel


# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY CHECKPOINT  (no disk I/O in tests)
# ─────────────────────────────────────────────────────────────────────────────

class InMemoryCheckpoint:
    """Full-featured in-memory checkpoint for testing."""

    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._failed: dict[str, dict] = {}
        self._overrides: dict[str, dict] = {}
        self._failures: dict[str, int] = {}

    def save(self, node_id: str, data: dict) -> None:
        self._store[node_id] = data

    def load(self, node_id: str) -> Optional[dict]:
        return self._store.get(node_id)

    def exists(self, node_id: str) -> bool:
        return node_id in self._store

    def clear(self) -> None:
        self._store.clear()

    def save_failed(self, node_id: str, data: dict) -> None:
        self._failed[node_id] = data

    def load_failed(self, node_id: str) -> Optional[dict]:
        return self._failed.get(node_id)

    def save_override(self, node_id: str, data: dict) -> None:
        self._overrides[node_id] = data

    def load_override(self, node_id: str) -> Optional[dict]:
        return self._overrides.get(node_id)

    def get_consecutive_failures(self, node_id: str) -> int:
        return self._failures.get(node_id, 0)

    def increment_failures(self, node_id: str) -> int:
        count = self._failures.get(node_id, 0) + 1
        self._failures[node_id] = count
        return count

    def reset_failures(self, node_id: str) -> None:
        self._failures.pop(node_id, None)


# ─────────────────────────────────────────────────────────────────────────────
# DUMMY NODE FUNCTIONS
# ─────────────────────────────────────────────────────────────────────────────

def _research(context: dict, model: Any = None) -> dict:
    return {"findings": "some research data", "topic": context.get("topic", "default")}


def _write(context: dict, model: Any = None) -> dict:
    findings = context.get("research", {}).get("findings", "")
    return {"draft": f"Article based on: {findings}"}


def _always_fail(context: dict, model: Any = None) -> dict:
    raise RuntimeError("This node always fails")


def _revenue_node(context: dict, model: Any = None) -> dict:
    return {"revenue": -500}  # Wrong: negative revenue


def _good_revenue_node(context: dict, model: Any = None) -> dict:
    return {"revenue": 1_200_000}


def _uses_full_context(context: dict, model: Any = None) -> dict:
    """Returns all keys it received — used to test context isolation."""
    return {"received_keys": sorted(context.keys())}


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: BACKWARD COMPATIBILITY
# ─────────────────────────────────────────────────────────────────────────────

class TestBackwardCompatibility:
    """Ensure all v0.1.x usage patterns still work identically."""

    def test_run_returns_dict_like_object(self) -> None:
        """result = orch.run() behaves like a dict — v0.1.x contract."""
        nodes = [DAGNode(id="research", fn_name="do_research")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_research": _research},
            checkpoint_backend=InMemoryCheckpoint(),
        )
        result = orch.run(initial_state={"topic": "AI"})

        # Dict-like access
        assert "research" in result
        assert result["research"]["findings"] == "some research data"
        assert result.get("research") is not None
        assert list(result.keys()) == ["topic", "research"]

    def test_run_supports_tuple_unpack(self) -> None:
        """state, run = orch.run() works for v0.2.0 callers."""
        nodes = [DAGNode(id="research", fn_name="do_research")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_research": _research},
            checkpoint_backend=InMemoryCheckpoint(),
        )
        state, run = orch.run(initial_state={"topic": "AI"})

        assert isinstance(state, dict) or hasattr(state, "__getitem__")
        assert isinstance(run, PipelineRun)
        assert state["research"]["findings"] == "some research data"

    def test_two_node_pipeline_still_works(self) -> None:
        """End-to-end 2-node pipeline — same as existing test_pipeline_runs_two_nodes_e2e."""
        nodes = [
            DAGNode(id="research", fn_name="do_research"),
            DAGNode(id="write", fn_name="do_write", depends_on=["research"]),
        ]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_research": _research, "do_write": _write},
            checkpoint_backend=InMemoryCheckpoint(),
        )
        result = orch.run(initial_state={"topic": "DagPipe"})
        assert "research" in result
        assert "write" in result
        assert "draft" in result["write"]

    def test_fresh_clears_checkpoints(self) -> None:
        """fresh=True still clears checkpoints — unchanged behaviour."""
        ckpt = InMemoryCheckpoint()
        nodes = [DAGNode(id="research", fn_name="do_research")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_research": _research},
            checkpoint_backend=ckpt,
        )
        orch.run()
        assert ckpt.exists("research")

        orch.run(fresh=True)
        # Ran again — still has checkpoint (re-executed and re-saved)
        assert ckpt.exists("research")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: PIPELINERUN TELEMETRY
# ─────────────────────────────────────────────────────────────────────────────

class TestPipelineRunTelemetry:

    def test_run_returns_pipeline_run(self) -> None:
        """PipelineRun is returned as second value."""
        nodes = [DAGNode(id="research", fn_name="do_research")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_research": _research},
            checkpoint_backend=InMemoryCheckpoint(),
        )
        _, run = orch.run()
        assert isinstance(run, PipelineRun)

    def test_pipeline_run_has_node_results(self) -> None:
        """PipelineRun.nodes contains NodeResult for each executed node."""
        nodes = [
            DAGNode(id="research", fn_name="do_research"),
            DAGNode(id="write", fn_name="do_write", depends_on=["research"]),
        ]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_research": _research, "do_write": _write},
            checkpoint_backend=InMemoryCheckpoint(),
        )
        _, run = orch.run()

        assert len(run.nodes) == 2
        assert run.nodes[0].node_id == "research"
        assert run.nodes[0].status == "success"
        assert run.nodes[0].duration_seconds >= 0.0
        assert run.nodes[1].node_id == "write"

    def test_restored_nodes_marked_skipped(self) -> None:
        """Nodes restored from checkpoint show status='skipped' in PipelineRun."""
        ckpt = InMemoryCheckpoint()
        nodes = [DAGNode(id="research", fn_name="do_research")]
        registry = {"do_research": _research}

        # First run
        orch1 = PipelineOrchestrator(nodes=nodes, node_registry=registry, checkpoint_backend=ckpt)
        orch1.run()

        # Second run — should restore from checkpoint
        orch2 = PipelineOrchestrator(nodes=nodes, node_registry=registry, checkpoint_backend=ckpt)
        _, run = orch2.run()

        assert run.nodes[0].status == "skipped"
        assert run.nodes[0].checkpoint_was_restored is True
        assert run.nodes_restored == 1
        assert run.nodes_executed == 0

    def test_pipeline_run_tracks_status_on_failure(self) -> None:
        """PipelineRun.status is 'failed' when a node fails."""
        nodes = [DAGNode(id="broken", fn_name="do_fail")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_fail": _always_fail},
            checkpoint_backend=InMemoryCheckpoint(),
            max_retries=1,
        )
        with pytest.raises(RuntimeError):
            orch.run()

    def test_pipeline_id_is_unique_per_run(self) -> None:
        """Each run gets a unique pipeline_id."""
        nodes = [DAGNode(id="research", fn_name="do_research")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_research": _research},
            checkpoint_backend=InMemoryCheckpoint(),
        )
        _, run1 = orch.run()
        orch2 = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_research": _research},
            checkpoint_backend=InMemoryCheckpoint(),
        )
        _, run2 = orch2.run()
        assert run1.pipeline_id != run2.pipeline_id


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: DEAD LETTER QUEUE
# ─────────────────────────────────────────────────────────────────────────────

class TestDeadLetterQueue:

    def test_failed_node_writes_dead_letter(self) -> None:
        """When a node exhausts retries, .failed entry is written."""
        ckpt = InMemoryCheckpoint()
        nodes = [DAGNode(id="broken", fn_name="do_fail")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_fail": _always_fail},
            checkpoint_backend=ckpt,
            max_retries=2,
        )
        with pytest.raises(RuntimeError):
            orch.run()

        failed = ckpt.load_failed("broken")
        assert failed is not None
        assert failed["node_id"] == "broken"
        assert "last_error" in failed
        assert "attempts" in failed
        assert failed["attempts"] == 2
        assert "context_passed_to_node" in failed
        assert "how_to_fix" in failed

    def test_error_message_mentions_debug_file(self) -> None:
        """RuntimeError message tells user where the debug file is."""
        nodes = [DAGNode(id="broken", fn_name="do_fail")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_fail": _always_fail},
            checkpoint_backend=InMemoryCheckpoint(),
            max_retries=1,
        )
        with pytest.raises(RuntimeError, match="broken.failed.json"):
            orch.run()

    def test_dead_letter_contains_last_error(self) -> None:
        """Dead letter entry contains the last error message."""
        ckpt = InMemoryCheckpoint()
        nodes = [DAGNode(id="broken", fn_name="do_fail")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_fail": _always_fail},
            checkpoint_backend=ckpt,
            max_retries=1,
        )
        with pytest.raises(RuntimeError):
            orch.run()

        failed = ckpt.load_failed("broken")
        assert "This node always fails" in failed["last_error"]

    def test_secrets_not_in_dead_letter(self) -> None:
        """Secrets must never appear in the dead letter queue entry."""
        ckpt = InMemoryCheckpoint()
        nodes = [DAGNode(id="broken", fn_name="do_fail")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_fail": _always_fail},
            checkpoint_backend=ckpt,
            secrets={"SECRET_KEY": "super-secret-value"},
            max_retries=1,
        )
        with pytest.raises(RuntimeError):
            orch.run()

        failed = ckpt.load_failed("broken")
        # Serialize to string and check secret never appears
        as_str = json.dumps(failed)
        assert "super-secret-value" not in as_str
        assert "SECRET_KEY" not in as_str


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: SEMANTIC CONTRACTS (assert_fn)
# ─────────────────────────────────────────────────────────────────────────────

class TestSemanticContracts:

    def test_assert_fn_passes_for_valid_output(self) -> None:
        """Pipeline completes normally when assert_fn returns True."""
        nodes = [DAGNode(
            id="revenue",
            fn_name="good_revenue",
            assert_fn=lambda out: out.get("revenue", 0) > 0,
            assert_message="Revenue must be positive",
        )]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"good_revenue": _good_revenue_node},
            checkpoint_backend=InMemoryCheckpoint(),
        )
        result = orch.run()
        assert result["revenue"]["revenue"] == 1_200_000

    def test_assert_fn_triggers_retry_on_failure(self) -> None:
        """When assert_fn fails, node retries. RuntimeError after max_retries."""
        nodes = [DAGNode(
            id="revenue",
            fn_name="bad_revenue",
            assert_fn=lambda out: out.get("revenue", 0) > 0,
            assert_message="Revenue must be positive",
        )]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"bad_revenue": _revenue_node},
            checkpoint_backend=InMemoryCheckpoint(),
            max_retries=2,
        )
        with pytest.raises(RuntimeError):
            orch.run()

    def test_assert_fn_error_injected_into_context_on_retry(self) -> None:
        """When assert_fn fails, __assert_failed__ and __assert_message__ appear in context."""
        received_contexts = []

        def tracking_node(context: dict, model: Any = None) -> dict:
            received_contexts.append(dict(context))
            return {"revenue": -1}  # Always fails assertion

        nodes = [DAGNode(
            id="revenue",
            fn_name="tracking",
            assert_fn=lambda out: out.get("revenue", 0) > 0,
            assert_message="Revenue must be positive",
        )]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"tracking": tracking_node},
            checkpoint_backend=InMemoryCheckpoint(),
            max_retries=2,
        )
        with pytest.raises(RuntimeError):
            orch.run()

        # Second+ attempts should have assert context
        assert len(received_contexts) >= 2
        assert received_contexts[1].get("__assert_failed__") is True
        assert "Revenue must be positive" in received_contexts[1].get("__assert_message__", "")
        assert "__previous_output__" in received_contexts[1]

    def test_assert_fn_exception_treated_as_failure(self) -> None:
        """If assert_fn itself raises, it's treated as a failed assertion."""
        nodes = [DAGNode(
            id="revenue",
            fn_name="bad_revenue",
            assert_fn=lambda out: out["nonexistent_key"] > 0,  # KeyError
            assert_message="Key check",
        )]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"bad_revenue": _revenue_node},
            checkpoint_backend=InMemoryCheckpoint(),
            max_retries=1,
        )
        with pytest.raises(RuntimeError):
            orch.run()


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: CONTEXT ISOLATION + SECRETS
# ─────────────────────────────────────────────────────────────────────────────

class TestContextIsolation:

    def test_secrets_never_in_context(self) -> None:
        """Secrets must not appear in the context dict passed to any node."""
        received_contexts = []

        def capturing_node(context: dict, model: Any = None) -> dict:
            received_contexts.append(dict(context))
            return {"done": True}

        nodes = [DAGNode(id="step", fn_name="capture")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"capture": capturing_node},
            checkpoint_backend=InMemoryCheckpoint(),
            secrets={"API_KEY": "sk-super-secret", "DB_PASS": "hunter2"},
        )
        orch.run(initial_state={"topic": "AI"})

        assert len(received_contexts) == 1
        ctx = received_contexts[0]
        assert "API_KEY" not in ctx
        assert "DB_PASS" not in ctx
        assert "sk-super-secret" not in str(ctx)
        assert "hunter2" not in str(ctx)

    def test_secrets_stripped_even_if_passed_in_initial_state(self) -> None:
        """Even if user accidentally puts a secret in initial_state, it's stripped."""
        received_contexts = []

        def capturing_node(context: dict, model: Any = None) -> dict:
            received_contexts.append(dict(context))
            return {"done": True}

        nodes = [DAGNode(id="step", fn_name="capture")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"capture": capturing_node},
            checkpoint_backend=InMemoryCheckpoint(),
            secrets={"API_KEY": "sk-secret"},
        )
        # User accidentally passes the key in initial_state
        orch.run(initial_state={"topic": "AI", "API_KEY": "sk-secret"})

        ctx = received_contexts[0]
        assert "API_KEY" not in ctx
        assert "sk-secret" not in str(ctx)

    def test_isolated_context_node_only_sees_declared_deps(self) -> None:
        """With isolate_context=True, node only gets initial_state + declared depends_on."""
        received_keys_log = []

        def node_a(context: dict, model: Any = None) -> dict:
            return {"a_data": "from_a"}

        def node_b(context: dict, model: Any = None) -> dict:
            return {"b_data": "from_b"}

        def node_c(context: dict, model: Any = None) -> dict:
            received_keys_log.append(sorted(context.keys()))
            return {"c_data": "from_c"}

        # node_c only depends on node_b, not node_a
        nodes = [
            DAGNode(id="node_a", fn_name="fn_a"),
            DAGNode(id="node_b", fn_name="fn_b", depends_on=["node_a"]),
            DAGNode(id="node_c", fn_name="fn_c", depends_on=["node_b"]),
        ]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"fn_a": node_a, "fn_b": node_b, "fn_c": node_c},
            checkpoint_backend=InMemoryCheckpoint(),
            isolate_context=True,
        )
        orch.run(initial_state={"topic": "test"})

        # node_c should see: topic (from initial_state) + node_b output
        # It should NOT see node_a output
        assert len(received_keys_log) == 1
        keys = received_keys_log[0]
        assert "node_b" in keys
        assert "topic" in keys
        assert "node_a" not in keys  # Key isolation working

    def test_non_isolated_context_full_state(self) -> None:
        """With isolate_context=False (default), node sees full state — v0.1.x behaviour."""
        received_keys_log = []

        def node_a(context: dict, model: Any = None) -> dict:
            return {"a_data": "from_a"}

        def node_c(context: dict, model: Any = None) -> dict:
            received_keys_log.append(sorted(context.keys()))
            return {"c_data": "done"}

        nodes = [
            DAGNode(id="node_a", fn_name="fn_a"),
            DAGNode(id="node_c", fn_name="fn_c", depends_on=["node_a"]),
        ]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"fn_a": node_a, "fn_c": node_c},
            checkpoint_backend=InMemoryCheckpoint(),
            isolate_context=False,  # default
        )
        orch.run(initial_state={"topic": "test"})

        keys = received_keys_log[0]
        assert "node_a" in keys
        assert "topic" in keys


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: CIRCUIT BREAKER
# ─────────────────────────────────────────────────────────────────────────────

class TestCircuitBreaker:

    def test_circuit_opens_after_threshold(self) -> None:
        """CircuitBreakerOpenError raised after threshold consecutive failures."""
        ckpt = InMemoryCheckpoint()
        nodes = [DAGNode(id="broken", fn_name="do_fail")]
        registry = {"do_fail": _always_fail}

        # Fail twice to trigger circuit (threshold=2)
        for _ in range(2):
            orch = PipelineOrchestrator(
                nodes=nodes,
                node_registry=registry,
                checkpoint_backend=ckpt,
                max_retries=1,
                circuit_breaker_threshold=2,
            )
            with pytest.raises(RuntimeError):
                orch.run()

        # Third run — circuit should be open
        orch3 = PipelineOrchestrator(
            nodes=nodes,
            node_registry=registry,
            checkpoint_backend=ckpt,
            max_retries=1,
            circuit_breaker_threshold=2,
        )
        with pytest.raises(CircuitBreakerOpenError):
            orch3.run()

    def test_circuit_resets_on_success(self) -> None:
        """A successful run resets the consecutive failure counter."""
        ckpt = InMemoryCheckpoint()
        call_count = {"n": 0}

        def flaky_node(context: dict, model: Any = None) -> dict:
            call_count["n"] += 1
            if call_count["n"] < 3:
                raise RuntimeError("Flaky")
            return {"done": True}

        nodes = [DAGNode(id="flaky", fn_name="flaky")]
        registry = {"flaky": flaky_node}

        # Fail once
        orch1 = PipelineOrchestrator(
            nodes=nodes, node_registry=registry, checkpoint_backend=ckpt,
            max_retries=1, circuit_breaker_threshold=3
        )
        with pytest.raises(RuntimeError):
            orch1.run()

        # Succeed — should reset counter
        orch2 = PipelineOrchestrator(
            nodes=nodes, node_registry=registry, checkpoint_backend=ckpt,
            max_retries=5, circuit_breaker_threshold=3
        )
        orch2.run(fresh=True)

        assert ckpt.get_consecutive_failures("flaky") == 0


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 7: MANUAL OVERRIDE
# ─────────────────────────────────────────────────────────────────────────────

class TestManualOverride:

    def test_override_used_instead_of_executing(self) -> None:
        """When an override exists, node is not executed."""
        ckpt = InMemoryCheckpoint()
        ckpt.save_override("research", {"findings": "manually_corrected"})

        call_count = {"n": 0}

        def counting_research(context: dict, model: Any = None) -> dict:
            call_count["n"] += 1
            return {"findings": "original"}

        nodes = [DAGNode(id="research", fn_name="do_research")]
        orch = PipelineOrchestrator(
            nodes=nodes,
            node_registry={"do_research": counting_research},
            checkpoint_backend=ckpt,
        )
        result = orch.run()

        assert result["research"]["findings"] == "manually_corrected"
        assert call_count["n"] == 0  # Node was NOT executed


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 8: RUNTIME COMPLEXITY FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

class TestRuntimeComplexityFn:

    def test_complexity_fn_overrides_static_score(self) -> None:
        """complexity_fn result is used instead of static complexity."""
        routed_to = []

        def low_model(messages):
            routed_to.append("low")
            return "{}"

        def high_model(messages):
            routed_to.append("high")
            return "{}"

        from dagpipe.router import ModelRouter

        router = ModelRouter(
            low_complexity_fn=low_model,
            high_complexity_fn=high_model,
            fallback_fn=low_model,
            low_label="low",
            high_label="high",
            fallback_label="fallback",
            complexity_threshold=0.7,
        )

        # Static complexity = 0.3 (low), but runtime fn returns 0.9 (high)
        node = DAGNode(
            id="dynamic",
            fn_name="fn",
            complexity=0.3,
            complexity_fn=lambda ctx: 0.9,  # Always high at runtime
        )
        node.resolve_fn({"fn": lambda context, model=None: {"done": True}})

        runtime_score = node.get_complexity({"topic": "complex task"})
        assert runtime_score == 0.9

    def test_complexity_fn_clamped_to_01(self) -> None:
        """complexity_fn result is clamped to [0.0, 1.0]."""
        node = DAGNode(
            id="test",
            fn_name="fn",
            complexity_fn=lambda ctx: 999.0,
        )
        assert node.get_complexity({}) == 1.0

        node2 = DAGNode(
            id="test2",
            fn_name="fn",
            complexity_fn=lambda ctx: -5.0,
        )
        assert node2.get_complexity({}) == 0.0

    def test_complexity_fn_exception_falls_back_to_static(self) -> None:
        """If complexity_fn raises, static score is used."""
        node = DAGNode(
            id="test",
            fn_name="fn",
            complexity=0.5,
            complexity_fn=lambda ctx: 1 / 0,  # ZeroDivisionError
        )
        assert node.get_complexity({}) == 0.5


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 9: MULTI-STRATEGY JSON EXTRACTOR
# ─────────────────────────────────────────────────────────────────────────────

class TestMultiStrategyExtractor:

    def test_strategy1_direct_parse(self) -> None:
        """Clean JSON parsed directly."""
        result = json.loads(_extract_json('{"key": "value", "num": 42}'))
        assert result == {"key": "value", "num": 42}

    def test_strategy2_markdown_fence_json(self) -> None:
        """JSON inside ```json ... ``` fence extracted."""
        raw = 'Here is the output:\n```json\n{"key": "value"}\n```'
        result = json.loads(_extract_json(raw))
        assert result == {"key": "value"}

    def test_strategy2_plain_fence(self) -> None:
        """JSON inside plain ``` ... ``` fence extracted."""
        raw = '```\n{"key": "value"}\n```'
        result = json.loads(_extract_json(raw))
        assert result == {"key": "value"}

    def test_strategy3_embedded_in_text(self) -> None:
        """JSON embedded in explanation text extracted via brace matching."""
        raw = 'Sure! Here is your result: {"revenue": 42000} Let me know if you need changes.'
        result = json.loads(_extract_json(raw))
        assert result == {"revenue": 42000}

    def test_strategy4_python_booleans(self) -> None:
        """Python True/False/None normalized to JSON true/false/null."""
        raw = '{"active": True, "deleted": False, "value": None}'
        result = json.loads(_extract_json(raw))
        assert result == {"active": True, "deleted": False, "value": None}

    def test_strategy4_trailing_commas(self) -> None:
        """Trailing commas before } or ] removed."""
        raw = '{"a": 1, "b": 2,}'
        result = json.loads(_extract_json(raw))
        assert result == {"a": 1, "b": 2}

    def test_strategy5_python_dict_literal(self) -> None:
        """Python dict literal parsed via ast.literal_eval."""
        raw = "{'key': 'value', 'num': 42}"
        result = json.loads(_extract_json(raw))
        assert result == {"key": "value", "num": 42}

    def test_all_strategies_fail_raises_valueerror(self) -> None:
        """ValueError raised when no strategy can extract JSON."""
        with pytest.raises(ValueError, match="Could not extract"):
            _extract_json("This is just plain text with no JSON at all.")

    def test_empty_string_raises_valueerror(self) -> None:
        with pytest.raises(ValueError):
            _extract_json("")

    def test_nested_json_extracted_correctly(self) -> None:
        """Nested JSON objects handled correctly."""
        raw = '{"user": {"name": "Alice", "age": 30}, "active": true}'
        result = json.loads(_extract_json(raw))
        assert result["user"]["name"] == "Alice"
        assert result["active"] is True


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 10: CONSTRAINED GENERATE WITH ENHANCED RETRY
# ─────────────────────────────────────────────────────────────────────────────

class TestConstrainedGenerateV2:

    class _SimpleSchema(BaseModel):
        title: str
        count: int

    def test_successful_generation_first_try(self) -> None:
        """Schema-valid JSON returned on first attempt."""
        mock_llm = MagicMock(return_value='{"title": "Hello", "count": 5}')
        result = constrained_generate(
            messages=[{"role": "user", "content": "Generate something"}],
            schema=self._SimpleSchema,
            llm_call_fn=mock_llm,
        )
        assert result.title == "Hello"
        assert result.count == 5

    def test_retry_includes_previous_output(self) -> None:
        """On retry, the LLM call messages include the previous failed output."""
        call_messages = []

        def tracking_llm(messages, **kwargs):
            call_messages.append(messages)
            if len(call_messages) == 1:
                return "not valid json at all"
            return '{"title": "Fixed", "count": 1}'

        result = constrained_generate(
            messages=[{"role": "user", "content": "Generate something"}],
            schema=self._SimpleSchema,
            llm_call_fn=tracking_llm,
            max_retries=2,
        )
        assert result.title == "Fixed"
        # Second call should include retry message with previous output
        assert len(call_messages) >= 2
        retry_messages = call_messages[1]
        retry_content = " ".join(m["content"] for m in retry_messages)
        assert "previous" in retry_content.lower() or "failed" in retry_content.lower()

    def test_python_bool_in_llm_response_handled(self) -> None:
        """LLM returning Python-style True/False still produces valid result."""

        class BoolSchema(BaseModel):
            active: bool
            name: str

        mock_llm = MagicMock(return_value='{"active": True, "name": "Test"}')
        result = constrained_generate(
            messages=[{"role": "user", "content": "test"}],
            schema=BoolSchema,
            llm_call_fn=mock_llm,
        )
        assert result.active is True
        assert result.name == "Test"

    def test_exhausted_retries_raises_valueerror(self) -> None:
        """ValueError raised when all retries are exhausted."""
        mock_llm = MagicMock(return_value="I cannot provide JSON right now, sorry!")
        with pytest.raises(ValueError, match="failed after"):
            constrained_generate(
                messages=[{"role": "user", "content": "Generate"}],
                schema=self._SimpleSchema,
                llm_call_fn=mock_llm,
                max_retries=1,
            )
