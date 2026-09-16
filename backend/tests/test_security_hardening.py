"""Repo-wide structural guarantees (spec section 16: security hardening).

These consolidate what would otherwise be one-off manual greps into
permanent, CI-enforced regression tests: no module anywhere may shell out
or eval arbitrary code, no table anywhere may be deleted from by
application code, and no future route can be added to the Local API
without authentication by accident.
"""

from __future__ import annotations

import ast
from pathlib import Path

from broker_sakuma.api.app import create_app
from broker_sakuma.api.deps import require_api_key
from broker_sakuma.config import Settings

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "broker_sakuma"


def _all_source_files() -> list[Path]:
    return sorted(SRC_ROOT.rglob("*.py"))


def test_no_module_anywhere_shells_out_or_evals():
    forbidden_imports = {"subprocess", "os"}
    forbidden_calls = {"eval", "exec"}

    violations: list[str] = []
    for path in _all_source_files():
        tree = ast.parse(path.read_text(), filename=str(path))

        imported_names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module.split(".")[0])

        bad_imports = imported_names & forbidden_imports
        if bad_imports:
            violations.append(f"{path.relative_to(SRC_ROOT)}: imports {bad_imports}")

        call_names = {
            node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        bad_calls = call_names & forbidden_calls
        if bad_calls:
            violations.append(f"{path.relative_to(SRC_ROOT)}: calls {bad_calls}")

    assert not violations, "\n".join(violations)


def test_no_module_anywhere_deletes_a_database_row():
    """audit_logs and post_mortems must stay append-only, and nothing else
    in this codebase should be silently discarding history either — the
    spec's append-only requirement (sections 13, 47) is enforced here as
    "no code path deletes anything," not just those two tables specifically.
    """

    violations: list[str] = []
    for path in _all_source_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "delete":
                violations.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno}: calls .delete(...)")

    assert not violations, "\n".join(violations)


def test_no_hardcoded_secret_assignment_anywhere():
    """Catches the shape of a hardcoded credential (`api_key = "..."`,
    `password = "..."`) — not a substitute for a real secret scanner, but
    a cheap guard against the most obvious mistake.
    """

    suspicious_names = {"password", "api_key", "secret", "private_key", "seed_phrase", "mnemonic"}
    violations: list[str] = []

    for path in _all_source_files():
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign):
                continue
            if not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and node.value.value):
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.lower() in suspicious_names:
                    violations.append(f"{path.relative_to(SRC_ROOT)}:{node.lineno}: hardcoded {target.id}")

    assert not violations, "\n".join(violations)


def test_every_local_api_route_requires_authentication():
    """Guards against a future route being added to a new router and the
    router forgetting `dependencies=[Depends(require_api_key)]` — walks
    the actual, live FastAPI app rather than re-reading source files.

    FastAPI wraps each `include_router()` call in an internal router
    object; ``original_router`` is the plain ``APIRouter`` as it was
    constructed (e.g. ``dashboard_routes.router``), before the `/api`
    prefix from `app.py` is applied — its routes still carry whatever
    router-level `dependencies=[...]` were declared, which is exactly
    what this test needs to check. Only routers actually mounted under
    `/api` are in scope: `web.py`'s dashboard page is deliberately public
    (it serves static markup with no data — see its module docstring),
    not an oversight this test should flag.
    """

    app = create_app(settings=Settings(database={"url": "sqlite:///:memory:"}, local_api={"api_key": "test-key"}))

    api_routes = []
    for route in app.routes:
        original_router = getattr(route, "original_router", None)
        include_context = getattr(route, "include_context", None)
        prefix = getattr(include_context, "prefix", "") if include_context is not None else ""
        if original_router is not None and prefix == "/api":
            api_routes.extend(original_router.routes)

    assert api_routes, "expected to find at least one included /api route"

    for route in api_routes:
        dependant = getattr(route, "dependant", None)
        assert dependant is not None, f"route {route.path} has no dependant"

        dependency_calls = {dep.call for dep in dependant.dependencies}
        assert require_api_key in dependency_calls, f"route {route.path} does not require an API key"
