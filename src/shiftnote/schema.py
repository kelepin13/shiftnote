"""JSON Schema for the LLM, flattened so every provider accepts it."""

from __future__ import annotations

from functools import cache
from typing import Any

from .models import CareNote


def _inline_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Replace every {"$ref": "#/$defs/X"} with the definition itself.

    Some providers reject `$ref`/`$defs`, so the schema we send is fully inlined.
    """
    if isinstance(node, dict):
        if "$ref" in node:
            name = node["$ref"].split("/")[-1]
            return _inline_refs(defs[name], defs)
        return {k: _inline_refs(v, defs) for k, v in node.items() if k not in ("$defs", "title")}
    if isinstance(node, list):
        return [_inline_refs(v, defs) for v in node]
    return node


@cache
def care_note_schema() -> dict[str, Any]:
    raw = CareNote.model_json_schema()
    return _inline_refs(raw, raw.get("$defs", {}))
