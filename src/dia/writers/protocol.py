"""Protocol definition for output writers."""

from typing import Protocol


class OutputWriter(Protocol):
    """Writes a JSON-serialisable payload to some destination, keyed by path.

    Implementations decide where output goes (S3, local disk, memory) —
    callers don't need to know or care. Keeps orchestration code (e.g.
    the pipeline runner) free of destination-specific branching.
    """

    def write(self, key: str, payload: dict) -> None:
        """Write a payload under the given key.

        Args:
            key: Destination path/key (e.g. "source-name/docs/report.pdf.json").
            payload: The JSON-serialisable dict to write.
        """
        ...
