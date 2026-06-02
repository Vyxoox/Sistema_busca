from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

ROUTE_DECORATORS = {"route", "get", "post", "put", "patch", "delete"}
AUDIT_DECORATOR = "audit_event"

EXCEPTIONS = {
    "healthz",
    "readyz",
    "criar_admin",
    "resetar_senha_admin",
    "editar_acesso_admin",
}


@dataclass
class MissingAudit:
    file: Path
    line: int
    function: str
    route: str
    methods: str


def _decorator_name(decorator: ast.AST) -> str:
    node = decorator.func if isinstance(decorator, ast.Call) else decorator
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _extract_route_data(decorator: ast.AST) -> tuple[str, str]:
    route = "<dynamic>"
    methods = "GET"

    if not isinstance(decorator, ast.Call):
        return route, methods

    if decorator.args:
        first = decorator.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            route = first.value

    for keyword in decorator.keywords:
        if keyword.arg != "methods":
            continue

        value = keyword.value
        if isinstance(value, (ast.List, ast.Tuple, ast.Set)):
            collected: list[str] = []
            for item in value.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    collected.append(item.value.upper())
            if collected:
                methods = ", ".join(collected)

    return route, methods


def _scan_file(path: Path) -> list[MissingAudit]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    missing: list[MissingAudit] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        route_decorators: list[ast.AST] = []
        has_audit = False

        for decorator in node.decorator_list:
            name = _decorator_name(decorator)
            if name in ROUTE_DECORATORS:
                route_decorators.append(decorator)
            if name == AUDIT_DECORATOR:
                has_audit = True

        if not route_decorators or has_audit:
            continue

        if node.name in EXCEPTIONS:
            continue

        for route_decorator in route_decorators:
            route, methods = _extract_route_data(route_decorator)
            missing.append(
                MissingAudit(
                    file=path,
                    line=node.lineno,
                    function=node.name,
                    route=route,
                    methods=methods,
                )
            )

    return missing


def main() -> int:
    files = [Path("app.py"), *sorted(Path("routes").glob("*.py"))]
    missing: list[MissingAudit] = []

    for file in files:
        if file.exists():
            missing.extend(_scan_file(file))

    if missing:
        print("ERRO: rotas sem @audit_event:")
        for item in missing:
            print(
                f"- {item.file.as_posix()}:{item.line} "
                f"{item.function} [{item.methods}] {item.route}"
            )
        return 1

    print("OK: 100% das rotas possuem @audit_event.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
