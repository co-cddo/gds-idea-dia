"""Tests for the Stage 2 topic/entity/relationship extraction prompt."""

import re

from llama_index.core.prompts import PromptTemplate

from dia.document_types import BASE_ENTITY_CLASSIFICATIONS
from dia.pipeline.graph_extraction_prompts import TOPIC_EXTRACTION_PROMPT

PLACEHOLDERS = ["{text}", "{preferred_topics}", "{preferred_entity_classifications}"]


def test_has_all_required_placeholders():
    for placeholder in PLACEHOLDERS:
        assert placeholder in TOPIC_EXTRACTION_PROMPT


def test_formats_cleanly_via_llama_index_prompt_template():
    """The toolkit calls llm.predict(PromptTemplate(template=...), **kwargs) —
    verify that substitution actually works, not just that placeholders exist."""
    template = PromptTemplate(template=TOPIC_EXTRACTION_PROMPT)
    formatted = template.format(
        text="Example proposition.",
        preferred_topics="Example Topic",
        preferred_entity_classifications="Supplier\nGovernment Departments",
    )
    assert "Example proposition." in formatted
    assert "Example Topic" in formatted
    assert "{text}" not in formatted
    assert "{preferred_topics}" not in formatted
    assert "{preferred_entity_classifications}" not in formatted


def test_response_format_uses_entity_prefixed_headers():
    """Regression guard: the toolkit's parser (parse_extracted_topics) only
    recognises relationship-section headers matching `entity-...s:` — a bare
    "relationships:" header (as used by the legacy prompt this was ported
    from) silently pollutes every statement's details. See module docstring."""
    assert "entity-entity relationships:" in TOPIC_EXTRACTION_PROMPT
    assert "entity-attributes:" in TOPIC_EXTRACTION_PROMPT

    # No bare "relationships:" header (i.e. not preceded by "entity-").
    for match in re.finditer(r"(.{0,7})relationships:", TOPIC_EXTRACTION_PROMPT):
        assert match.group(1).endswith("entity-") or match.group(1).endswith("entity "), (
            f"found a relationships: header not prefixed with entity-: {match.group(0)!r}"
        )


def test_no_hardcoded_spend_id():
    """Spend ID is business-case/SR-bids specific (Contract Finder uses
    Contract ID instead) — the generalised definition should mention both
    as examples, not treat one as the canonical/only identifier field."""
    assert "Primary Identifier" in TOPIC_EXTRACTION_PROMPT
    assert "Spend ID" in TOPIC_EXTRACTION_PROMPT
    assert "Contract ID" in TOPIC_EXTRACTION_PROMPT
    # Not listed as its own numbered definition item (that's the legacy bug).
    assert "**Spend ID**" not in TOPIC_EXTRACTION_PROMPT


def test_not_named_after_a_specific_source():
    """This prompt is shared across all DocumentTypes, not just GATS."""
    assert "GATS" not in TOPIC_EXTRACTION_PROMPT


def test_contains_supplier_and_government_hard_rules():
    assert '"Supplier" - NO EXCEPTIONS' in TOPIC_EXTRACTION_PROMPT
    assert '"Government Departments" - NO EXCEPTIONS' in TOPIC_EXTRACTION_PROMPT


def test_forbidden_classifications_list_present():
    for forbidden in ["Company", "Corporation", "Business", "Contractor", "Agency", "Department", "Organisation"]:
        assert forbidden in TOPIC_EXTRACTION_PROMPT


def test_definition_categories_are_known_entity_classifications():
    """Every category given a detailed definition should be a real,
    known classification — guards against the prompt and
    document_types.BASE_ENTITY_CLASSIFICATIONS drifting apart."""
    defined_categories = re.findall(r"^\d+\.\s+\*\*(.+?)\*\*", TOPIC_EXTRACTION_PROMPT, re.MULTILINE)

    assert len(defined_categories) == 26

    known = set(BASE_ENTITY_CLASSIFICATIONS)
    for category in defined_categories:
        if category.startswith("Primary Identifier"):
            continue  # generalised placeholder for Spend ID / Contract ID, not itself a fixed classification
        assert category in known, f"{category!r} defined in prompt but not in BASE_ENTITY_CLASSIFICATIONS"
