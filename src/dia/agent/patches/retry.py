"""Patch: stop retrying query timeouts, keep retrying transient errors.

A ReadTimeoutError/ConnectTimeoutError on an expensive graph traversal is
STRUCTURAL, not transient — retrying it just re-times-out on every attempt.
The library's base unretriable_exception_types() returns an empty tuple, so
tenacity (the retry library) retries everything, turning one 90s timeout
into (max_attempts x 90s) of wasted waiting.

This patch does two things:
  (a) Marks botocore ReadTimeoutError/ConnectTimeoutError as unretriable on
      GraphStore and every Neptune subclass that overrides
      unretriable_exception_types (the concrete Neptune client classes shadow
      the base via MRO, so the base alone isn't enough) — these now fail
      fast instead of retrying.
  (b) Enforces a floor of 3 attempts for everything else (genuinely
      transient errors — dropped connections, throttling), since the
      library's own default of 1 attempt gives up too eagerly.
"""

import graphrag_toolkit.lexical_graph.storage.graph.neptune_graph_stores as _neptune_mod
from botocore.exceptions import ConnectTimeoutError as _ConnectTimeoutError  # noqa: E402
from botocore.exceptions import ReadTimeoutError as _ReadTimeoutError
from graphrag_toolkit.lexical_graph.storage.graph.graph_store import GraphStore as _GraphStore


def apply() -> None:
    """Patch GraphStore (and Neptune subclasses) in place.

    Idempotent per-class: each class is guarded independently via its own
    `_unpatched_unretriable_exception_types` / `_unpatched_execute_query_with_retry`
    markers, since subclasses inherit the base's marker but still need their
    own override patched (hasattr would wrongly skip them — this checks
    `__dict__` directly instead).
    """

    if not hasattr(_GraphStore, "_unpatched_execute_query_with_retry"):
        _TIMEOUT_EXC = (_ReadTimeoutError, _ConnectTimeoutError)

        # (a) Make timeouts unretriable.
        # The concrete Neptune subclasses (NeptuneDatabaseClient /
        # NeptuneAnalyticsClient) OVERRIDE unretriable_exception_types with
        # their own list of botocore errorfactory exceptions, so patching the
        # base GraphStore is shadowed by MRO. Patch every class in the neptune
        # module that defines the method (plus the base, for completeness).
        _RETRY_PATCH_TARGETS = [_GraphStore]
        for _cls in vars(_neptune_mod).values():
            if (
                isinstance(_cls, type)
                and "unretriable_exception_types" in _cls.__dict__
                and _cls not in _RETRY_PATCH_TARGETS
            ):
                _RETRY_PATCH_TARGETS.append(_cls)

        def _make_patched_unretriable(orig):
            def _patched_unretriable_exception_types(self):
                return tuple(orig(self)) + _TIMEOUT_EXC

            return _patched_unretriable_exception_types

        for _cls in _RETRY_PATCH_TARGETS:
            # Use __dict__ (not hasattr): subclasses inherit the base's
            # _unpatched_* marker, so hasattr would wrongly skip them and the
            # subclass's own unretriable_exception_types would stay unpatched.
            if "_unpatched_unretriable_exception_types" not in _cls.__dict__:
                _cls._unpatched_unretriable_exception_types = _cls.__dict__["unretriable_exception_types"]
                _cls.unretriable_exception_types = _make_patched_unretriable(
                    _cls._unpatched_unretriable_exception_types
                )

        # (b) Keep a retry floor for transient (non-timeout) failures.
        _GraphStore._unpatched_execute_query_with_retry = _GraphStore.execute_query_with_retry

        def _patched_execute_query_with_retry(self, query, parameters=None, max_attempts=1, max_wait=10, **kwargs):
            return _GraphStore._unpatched_execute_query_with_retry(
                self,
                query,
                parameters or {},
                max_attempts=max(max_attempts, 3),
                max_wait=max_wait,
                **kwargs,
            )

        _GraphStore.execute_query_with_retry = _patched_execute_query_with_retry
