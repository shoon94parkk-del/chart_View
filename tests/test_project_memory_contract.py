from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_durable_project_memory_files_exist_and_are_linked():
    for path in (
        "AGENTS.md",
        "docs/project-memory.md",
        "docs/regression-guardrails.md",
        "docs/decision-log.md",
    ):
        assert (ROOT / path).exists(), path

    agents = read("AGENTS.md")
    readme = read("README.md")
    handover = read("docs/handover.md")

    for path in (
        "docs/project-memory.md",
        "docs/regression-guardrails.md",
        "docs/decision-log.md",
    ):
        assert path in agents
        assert path in readme
        assert path in handover


def test_project_memory_locks_current_production_and_high_risk_decisions():
    memory = read("docs/project-memory.md")
    guardrails = read("docs/regression-guardrails.md")
    decisions = read("docs/decision-log.md")

    assert "https://chart-view-pkv8.onrender.com" in memory
    assert "https://chart-view-toss.onrender.com" in memory
    assert "chart-view-bsg6" in memory and "legacy" in memory.lower()

    # Bugs already experienced in production must stay represented as durable rules.
    for token in (
        "Clean root",
        "Adding one stock",
        "기준 종가",
        "LS ELECTRIC",
        "no-cache, max-age=0, must-revalidate",
        "build_frontend_bundle.py --check",
    ):
        assert token in memory, token

    for token in (
        "Clean root -> Home",
        "Adding one stock does not refetch the full watchlist",
        "기준 종가",
        "Exact tested SHA",
    ):
        assert token in guardrails, token

    assert "Watchlist add is incremental" in decisions
    assert "Repository memory is part of the engineering system" in decisions


def test_agent_rules_require_regression_test_memory_update_and_exact_deploy():
    agents = read("AGENTS.md")
    for token in (
        "Search for prior work",
        "Add or update a regression test",
        "docs/decision-log.md",
        "exact tested",
        "/health",
        "build_frontend_bundle.py --check",
    ):
        assert token in agents, token
