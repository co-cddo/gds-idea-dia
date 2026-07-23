"""In-memory output writer — for tests and programmatic inspection."""


class InMemoryWriter:
    """Captures written payloads in memory instead of persisting them.

    Useful for tests (assert on what was written without moto/tmp_path)
    and for programmatic use where you want the output in-process rather
    than round-tripped through disk or S3.
    """

    def __init__(self) -> None:
        self.written: dict[str, dict] = {}

    def write(self, key: str, payload: dict) -> None:
        """Store a payload under the given key."""
        self.written[key] = payload
