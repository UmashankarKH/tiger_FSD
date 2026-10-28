#!/usr/bin/env python3
"""Deterministic bloat checks: the cheap, no-LLM half of bloat control.

It catches the mechanical kinds of bloat that AI-generated code tends to leave behind:

  unused-import      imported but never used
  unused-code        function, method or class that nothing references
  single-impl-abc    abstract base class with at most one implementation
  swallowed-error    broad `except` that never re-raises
  impossible-check   `is None` / isinstance / `len() < 0` on a value the function
                     itself just built, so the check can never fire

What it cannot see (the LLM judge covers these): needless layers that ARE used,
clamps like `if pct > 100`, duplicated logic, over-general parameters.

Usage:
    python tools/bloat_check.py src/procurement_legacy.py --also-scan tests
    python tools/bloat_check.py src/procurement_fixed.py --also-scan tests --max-findings 0
"""
import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path

SAFE_CALLS = {"len", "float", "int", "round", "list", "dict", "set", "tuple", "sum", "str", "sorted", "abs", "bool"}
SKIP_NAMES = {"main"}


@dataclass(frozen=True)
class Finding:
    kind: str
    line: int
    message: str


def _parse(path):
    return ast.parse(Path(path).read_text(), filename=str(path))


def _python_files(directory):
    return sorted(Path(directory).rglob("*.py"))


def _referenced_names(trees):
    names = set()
    for tree in trees:
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
    return names


def _unused_imports(tree):
    used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound = (alias.asname or alias.name).split(".")[0]
                if bound not in used:
                    yield Finding("unused-import", node.lineno, f"import `{bound}` is never used")


def _definitions(tree):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            yield node, None
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        yield child, node.name


def _unused_code(tree, referenced):
    for node, owner in _definitions(tree):
        name = node.name
        if name.startswith("__") and name.endswith("__"):
            continue
        if name.startswith("test_") or name in SKIP_NAMES:
            continue
        if name not in referenced:
            kind = "class" if isinstance(node, ast.ClassDef) else ("method" if owner else "function")
            label = f"{owner}.{name}" if owner else name
            yield Finding("unused-code", node.lineno, f"{kind} `{label}` is never referenced")


def _is_abc(cls):
    return any(
        (isinstance(b, ast.Name) and b.id == "ABC") or (isinstance(b, ast.Attribute) and b.attr == "ABC")
        for b in cls.bases
    )


def _single_impl_abcs(tree):
    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    for cls in classes:
        if not _is_abc(cls):
            continue
        impls = [
            c.name
            for c in classes
            if any(isinstance(b, ast.Name) and b.id == cls.name for b in c.bases)
        ]
        if len(impls) <= 1:
            who = impls[0] if impls else "none"
            yield Finding(
                "single-impl-abc",
                cls.lineno,
                f"abstract class `{cls.name}` has {len(impls)} implementation(s) ({who}); "
                "an abstraction with one implementation is a layer, not a design",
            )


def _swallowed_errors(tree):
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(fn):
            if not isinstance(node, ast.ExceptHandler):
                continue
            broad = node.type is None or (isinstance(node.type, ast.Name) and node.type.id in {"Exception", "BaseException"})
            reraises = any(isinstance(n, ast.Raise) for n in ast.walk(node))
            if broad and not reraises:
                yield Finding(
                    "swallowed-error",
                    node.lineno,
                    f"broad `except` in `{fn.name}` swallows every error and carries on",
                )


def _is_safe_value(expr):
    if isinstance(expr, (ast.List, ast.Dict, ast.Set, ast.Tuple, ast.ListComp, ast.DictComp, ast.SetComp)):
        return True
    if isinstance(expr, ast.Constant) and expr.value is not None:
        return True
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        return True
    return isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id in SAFE_CALLS


def _impossible_checks(tree):
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        assigned = {}
        from_len = set()
        for node in ast.walk(fn):
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
                assigned[name] = assigned.get(name, True) and _is_safe_value(node.value)
                if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == "len":
                    from_len.add(name)
            elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
                assigned.setdefault(node.target.id, False)
        safe = {n for n, ok in assigned.items() if ok}

        for node in ast.walk(fn):
            if isinstance(node, ast.Compare) and len(node.ops) == 1:
                left, op, right = node.left, node.ops[0], node.comparators[0]
                if isinstance(left, ast.Name) and left.id in safe and isinstance(op, (ast.Is, ast.IsNot)) \
                        and isinstance(right, ast.Constant) and right.value is None:
                    yield Finding("impossible-check", node.lineno,
                                  f"`{left.id} is None` in `{fn.name}`: it was just built from a value that cannot be None")
                is_len_value = (
                    (isinstance(left, ast.Call) and isinstance(left.func, ast.Name) and left.func.id == "len")
                    or (isinstance(left, ast.Name) and left.id in from_len)
                )
                if is_len_value and isinstance(op, ast.Lt) and isinstance(right, ast.Constant) and right.value == 0:
                    yield Finding("impossible-check", node.lineno,
                                  f"length compared `< 0` in `{fn.name}`: a length is never negative")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "isinstance" \
                    and node.args and isinstance(node.args[0], ast.Name) and node.args[0].id in safe:
                yield Finding("impossible-check", node.lineno,
                              f"isinstance check on `{node.args[0].id}` in `{fn.name}`: its type is already known")


def analyze(target, also_scan=()):
    """Return a sorted list of Findings for `target`. `also_scan` dirs only count as references."""
    tree = _parse(target)
    trees = [tree]
    for directory in also_scan:
        trees.extend(_parse(p) for p in _python_files(directory))
    referenced = _referenced_names(trees)

    findings = set()
    for group in (
        _unused_imports(tree),
        _unused_code(tree, referenced),
        _single_impl_abcs(tree),
        _swallowed_errors(tree),
        _impossible_checks(tree),
    ):
        findings.update(group)
    return sorted(findings, key=lambda f: (f.line, f.kind))


def count_code_lines(target):
    lines = Path(target).read_text().splitlines()
    return sum(1 for line in lines if line.strip() and not line.strip().startswith("#"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", help="Python file to check")
    parser.add_argument("--also-scan", nargs="*", default=[], help="directories searched for references only (e.g. tests)")
    parser.add_argument("--max-findings", type=int, default=0, help="exit 1 if more findings than this (default 0)")
    args = parser.parse_args(argv)

    findings = analyze(args.target, args.also_scan)
    print(f"{args.target}  ({count_code_lines(args.target)} code lines)")
    for f in findings:
        print(f"  line {f.line:>3}  [{f.kind}] {f.message}")
    print(f"{len(findings)} finding(s)")
    return 1 if len(findings) > args.max_findings else 0


if __name__ == "__main__":
    sys.exit(main())
