"""Output models for the extraction pipeline.

Each stage of the pipeline has its own output shape. These are the typed
contracts — the runner builds one of these per document, then hands it to
an OutputWriter (which just serialises whatever dict it's given).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TextExtractionOutput:
    """The JSON document written by Stage 1 for each successfully processed document.

    Written to `{source_name}/{key}.json` via an OutputWriter. `metadata` is
    always present (empty dict if no metadata provider was configured, or no
    match was found for this document) — downstream consumers get a
    consistent schema regardless of source.
    """

    key: str
    source_name: str
    content_type: str
    version: str
    text: str
    chars: int
    metadata: dict
    extracted_at: str
    code_version: str
