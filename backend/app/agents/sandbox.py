"""Tool sandbox — workspace-confined file access, environment-isolated shell,
and a restricted calculator. Deep OS/WASM sandboxing lands with governance
(Stage 10); this enforces the Stage 3 boundary: no escape from the workspace,
no secrets in the environment, bounded runtime and output."""

from __future__ import annotations

import ast
import math
import os
import subprocess
from pathlib import Path

from ..config import settings


def workspace() -> Path:
    p = settings.data_dir / "workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _confine(path: str) -> Path:
    base = workspace().resolve()
    target = (base / path).resolve() if not os.path.isabs(path) else Path(path).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        raise PermissionError(f"path escapes the workspace: {path}") from None
    return target


def read_file(path: str) -> str:
    p = _confine(path)
    if not p.is_file():
        raise FileNotFoundError(f"not a file: {p}")
    return p.read_text(encoding="utf-8", errors="replace")[:40000]


def write_file(path: str, content: str) -> str:
    p = _confine(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    rel = p.relative_to(workspace())
    return f"wrote {len(content)} chars to {rel}"


def list_workspace(path: str = "") -> str:
    p = _confine(path) if path else workspace()
    if not p.is_dir():
        raise FileNotFoundError(f"not a directory: {p}")
    ents = sorted(p.iterdir())
    lines = []
    for e in ents[:300]:
        kind = "dir " if e.is_dir() else "file"
        lines.append(f"{kind} {e.name}")
    return "\n".join(lines) or "(empty)"


def run_shell(command: str, timeout: int = 15) -> str:
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"),
        "HOME": str(settings.data_dir),
        "TMPDIR": str(settings.data_dir / "tmp"),
    }
    # Windows subprocesses need the system shell vars; nothing sensitive is re-added.
    for key in ("SYSTEMROOT", "SystemRoot", "WINDIR", "ComSpec", "PATHEXT"):
        if key in os.environ:
            env[key] = os.environ[key]
    (settings.data_dir / "tmp").mkdir(parents=True, exist_ok=True)
    kwargs: dict = {"stdin": subprocess.DEVNULL}  # never wait on an unattended stdin pipe
    if os.name == "nt":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        r = subprocess.run(
            command,
            shell=True,
            cwd=str(workspace()),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
            **kwargs,
        )
        out = r.stdout or ""
        if r.stderr:
            out += "\n[stderr]\n" + r.stderr
        return (out or "(no output)")[:4000]
    except subprocess.TimeoutExpired:
        return f"[timeout after {timeout}s]"
    except Exception as exc:  # noqa: BLE001
        return f"[shell error] {exc}"


# ------------------------------------------------------------------ calculator
_ALLOWED_NODES = (
    ast.Expression,
    ast.Constant,
    ast.BinOp,
    ast.UnaryOp,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.USub,
    ast.UAdd,
    ast.Name,
    ast.Call,
    ast.Compare,
    ast.Eq,
    ast.NotEq,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.And,
    ast.Or,
    ast.BoolOp,
)

_FUNCS: dict[str, object] = {"min": min, "max": max, "abs": abs, "round": round, "sqrt": math.sqrt, "pi": math.pi}


def _apply(op: ast.operator, a: float, b: float):
    return {
        ast.Add: lambda: a + b,
        ast.Sub: lambda: a - b,
        ast.Mult: lambda: a * b,
        ast.Div: lambda: a / b,
        ast.FloorDiv: lambda: a // b,
        ast.Mod: lambda: a % b,
        ast.Pow: lambda: a ** b,
    }.get(type(op), lambda: (_ for _ in ()).throw(ValueError("unsupported op")))()


def _compare(cmp: ast.Compare) -> bool:
    value = _eval(cmp.left)
    for op, right in zip(cmp.ops, cmp.comparators):
        rhs = _eval(right)
        if isinstance(op, ast.Eq) and value != rhs:
            return False
        if isinstance(op, ast.NotEq) and value == rhs:
            return False
        if isinstance(op, ast.Lt) and not (value < rhs):
            return False
        if isinstance(op, ast.LtE) and not (value <= rhs):
            return False
        if isinstance(op, ast.Gt) and not (value > rhs):
            return False
        if isinstance(op, ast.GtE) and not (value >= rhs):
            return False
        value = rhs
    return True


def _eval(node: ast.AST) -> object:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.BinOp):
        return _apply(node.op, _eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp):
        return -_eval(node.operand) if isinstance(node.op, ast.USub) else +_eval(node.operand)
    if isinstance(node, ast.BoolOp):
        vals = [_eval(v) for v in node.values]
        return all(vals) if isinstance(node.op, ast.And) else any(vals)
    if isinstance(node, ast.Compare):
        return _compare(node)
    if isinstance(node, ast.Name):
        if node.id not in _FUNCS:
            raise ValueError("unknown identifier")
        return _FUNCS[node.id]
    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name) or node.func.id not in _FUNCS:
            raise ValueError("calls are limited to safe functions")
        return _FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("unsupported expression")


def safe_calc(expression: str) -> str:
    expr = expression.strip()
    if not expr:
        raise ValueError("empty expression")
    if len(expr) > 300:
        raise ValueError("expression too long")
    tree = ast.parse(expr, mode="eval")
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise ValueError("unsupported syntax")
    try:
        return str(_eval(tree.body))
    except ZeroDivisionError:
        raise ValueError("division by zero")