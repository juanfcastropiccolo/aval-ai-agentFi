"""Tarea 19: E2E del agente de ejemplo — 4 escenarios y verificación del audit trail."""

from pathlib import Path

from aval import AutoApproveReviewer, Verdict
from aval.core.audit import JsonlAuditStore
from examples.example_agent import build_demo, run_scenarios


def test_four_scenarios_end_to_end(tmp_path: Path) -> None:
    audit_path = tmp_path / "demo.aval.jsonl"
    # ConsoleHumanReviewer mockeado por uno automático que aprueba.
    engine, mandate = build_demo(audit_path, reviewer=AutoApproveReviewer(Verdict.ALLOW))
    results = run_scenarios(engine, mandate)

    assert results["allow"].verdict is Verdict.ALLOW
    assert results["deny_limit"].verdict is Verdict.DENY
    assert "límite por transacción" in results["deny_limit"].reason
    assert results["deny_recipient"].verdict is Verdict.DENY
    assert "destino no permitido" in results["deny_recipient"].reason
    # escalado y aprobado por el reviewer automático
    assert results["escalate"].verdict is Verdict.ALLOW
    assert "aprobado por humano" in results["escalate"].reason

    # El audit trail registró los 4 veredictos y está íntegro.
    entries = JsonlAuditStore(audit_path).entries()
    assert len(entries) == 4
    assert JsonlAuditStore(audit_path).verify() is True


def test_escalation_rejected_blocks(tmp_path: Path) -> None:
    audit_path = tmp_path / "demo.aval.jsonl"
    engine, mandate = build_demo(audit_path, reviewer=AutoApproveReviewer(Verdict.DENY))
    results = run_scenarios(engine, mandate)
    assert results["escalate"].verdict is Verdict.DENY
    assert "rechazado por humano" in results["escalate"].reason
