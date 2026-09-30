"""The import-linter contracts in pyproject.toml list `app` packages by hand, and import-linter can't
tell that a list is incomplete: a package missing from a forbidden list is silently allowed. These
tests classify every top-level `app` module against the contracts, so a newly added package (or one
left out, as `app.version` was in PR #306's first version) fails here until it's placed.
"""

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
APP = REPO_ROOT / "app"

LEAVES = {"app.provenance", "app.intent", "app.graph_schema", "app.version"}
ADAPTERS = {"app.api", "app.mcp", "app.main", "app.deps", "app.answer_router"}
# The REST/UI natural-language query path: the only modules allowed to use the LLM layer.
LLM_USERS = {"app.ai", "app.api", "app.answer_router", "app.deps", "app.main"}


def _app_modules() -> set[str]:
    packages = {f"app.{path.parent.name}" for path in APP.glob("*/__init__.py")}
    modules = {f"app.{path.stem}" for path in APP.glob("*.py") if path.stem != "__init__"}
    return packages | modules


def _contract(name_prefix: str) -> dict:
    contracts = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["tool"]["importlinter"][
        "contracts"
    ]
    [contract] = [c for c in contracts if c["name"].startswith(name_prefix)]
    return contract


def _app_only(modules: list[str]) -> set[str]:
    return {module for module in modules if module.startswith("app.")}


def test_the_classification_names_only_real_modules():
    assert LEAVES | ADAPTERS | LLM_USERS <= _app_modules()


def test_the_qualification_kernel_is_forbidden_every_other_app_module():
    contract = _contract("The qualification kernel")
    assert contract["source_modules"] == ["app.qualification"]
    assert _app_only(contract["forbidden_modules"]) == _app_modules() - {"app.qualification"}


def test_every_non_adapter_module_is_forbidden_the_adapters():
    contract = _contract("Delivery adapters")
    assert set(contract["forbidden_modules"]) == ADAPTERS
    assert set(contract["source_modules"]) == _app_modules() - ADAPTERS


def test_every_module_outside_the_query_path_is_forbidden_the_llm_layer():
    contract = _contract("The LLM layer")
    assert set(contract["source_modules"]) == _app_modules() - LLM_USERS


def test_leaves_are_forbidden_every_non_leaf_and_each_other():
    outward = _contract("Leaf packages import no non-leaf")
    assert set(outward["source_modules"]) == LEAVES
    assert _app_only(outward["forbidden_modules"]) == _app_modules() - LEAVES
    independence = _contract("Leaf packages don't import each other")
    assert independence["type"] == "independence"
    assert set(independence["modules"]) == LEAVES


def test_the_shared_base_is_forbidden_every_other_app_module():
    contract = _contract("The shared base")
    assert contract["source_modules"] == ["app.common"]
    assert _app_only(contract["forbidden_modules"]) == _app_modules() - {"app.common"}
