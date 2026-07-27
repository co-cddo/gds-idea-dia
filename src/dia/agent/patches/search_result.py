"""Patch: make SearchResult.model_validate tolerant of ISO timestamp strings.

The graphrag-toolkit's Versioning model expects `valid_from`, `valid_to`,
`extract_timestamp`, and `build_timestamp` to be integer (millisecond)
timestamps. Neptune actually returns these fields as ISO 8601 date strings,
which fails Pydantic validation.

This patch pre-processes the raw dict before validation runs, converting any
ISO string in those four fields to an int. If a value can't be parsed, it's
set to -1 rather than raising, so validation never fails on this field.
"""

from datetime import datetime as _dt

from graphrag_toolkit.lexical_graph.retrieval.model import SearchResult as _SearchResult


def apply() -> None:
    """Patch SearchResult.model_validate in place.

    Idempotent: safe to call more than once (e.g. via importlib.reload) —
    guarded by checking for `_unpatched_model_validate`, which only gets set
    on the first call.
    """
    if not hasattr(_SearchResult, "_unpatched_model_validate"):
        _SearchResult._unpatched_model_validate = _SearchResult.model_validate.__func__

        _original_sr_validate = _SearchResult._unpatched_model_validate

        @classmethod
        def _patched_sr_validate(cls, obj, *args, **kwargs):
            if isinstance(obj, dict) and isinstance(obj.get("source"), dict):
                versioning = obj["source"].get("versioning")
                if isinstance(versioning, dict):
                    for _field in (
                        "valid_from",
                        "valid_to",
                        "extract_timestamp",
                        "build_timestamp",
                    ):
                        _val = versioning.get(_field)
                        if isinstance(_val, str):
                            try:
                                versioning[_field] = int(_dt.fromisoformat(_val).timestamp() * 1000)
                            except (ValueError, TypeError):
                                versioning[_field] = -1
            return _original_sr_validate(cls, obj, *args, **kwargs)

        _SearchResult.model_validate = _patched_sr_validate
