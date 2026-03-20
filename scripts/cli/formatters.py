"""
Terminal output formatters for the computer CLI.

All rendering goes through these helpers so command modules stay clean.
"""
from __future__ import annotations

from typing import Any


def _hr(char: str = "─", width: int = 70) -> str:
    return char * width


def section(title: str) -> None:
    print(f"\n{_hr()}")
    print(f"  {title.upper()}")
    print(_hr())


def kv(label: str, value: Any, width: int = 28) -> None:
    print(f"  {label:<{width}} {value}")


def table(headers: list[str], rows: list[list[Any]], col_width: int = 22) -> None:
    header_line = "  " + "".join(f"{h:<{col_width}}" for h in headers)
    print(header_line)
    print("  " + "─" * (col_width * len(headers)))
    for row in rows:
        print("  " + "".join(f"{str(v):<{col_width}}" for v in row))


def status_line(label: str, ok: bool, detail: str = "") -> None:
    icon = "✓" if ok else "✗"
    detail_str = f"  → {detail}" if detail and not ok else ""
    print(f"  [{icon}] {label}{detail_str}")


def tree(items: list[dict[str, Any]], label_key: str = "name", children_key: str = "children",
         indent: int = 0) -> None:
    for item in items:
        prefix = "    " * indent + ("└── " if indent else "")
        print(f"  {prefix}{item.get(label_key, '?')}")
        for child in item.get(children_key, []):
            tree([child], label_key, children_key, indent + 1)


def diff_line(label: str, old: Any, new: Any) -> None:
    if old == new:
        print(f"  = {label}: {old}")
    else:
        print(f"  ~ {label}")
        print(f"    - {old}")
        print(f"    + {new}")


def warn(msg: str) -> None:
    print(f"  [!] {msg}")


def ok(msg: str) -> None:
    print(f"  [✓] {msg}")


def err(msg: str) -> None:
    print(f"  [✗] {msg}")


def summary_line(passed: int, total: int, label: str = "checks") -> None:
    pct = int(100 * passed / total) if total else 0
    icon = "✓" if passed == total else "✗"
    print(f"\n  {icon}  {passed}/{total} {label} passed ({pct}%)\n")
