from __future__ import annotations

from dia.agent.prompts.fragments.utils import block

REPORT_HOUSE_STYLE = block(
    "house_style",
    """
    HOUSE STYLE — apply throughout, on top of the section-by-section output
    specification given elsewhere in this prompt. These are presentation and
    prose rules; they do not change which sections are required.

    1. DOCUMENT OPENING
    - Title, then a 40-60 word standfirst that defines the subject in plain
      terms (what it is, why it matters) before any findings.
    - Follow the standfirst with one basis/classification line stating the
      evidence base and any classification marking.
    - Add a Contents block if the report has more than six top-level sections.

    2. GROUP RELATED SUBJECTS UNDER NAMED CATEGORIES
    - When a report covers more than about five peer subjects (departments,
      suppliers, programmes, trends), group them under named category headings
      rather than listing them as a flat sequence of equals.
    - Choose category names that describe what the subjects in the group have
      in common, not generic labels like "Group A".

    3. TAKEAWAY-FIRST BULLETS
    - Every bullet in a findings or developments list opens with a complete,
      assertive claim in bold, followed by the evidence for it.
    - Do not write a bare noun phrase or heading fragment as a bullet with the
      evidence trailing unlabelled beneath it.

    4. EXHIBIT FURNITURE — every table is an exhibit
    - Number exhibits sequentially: "Exhibit 1", "Exhibit 2", ...
    - Above the table, in this order: the exhibit number; a one-sentence
      TAKEAWAY as the title (a finding, not a label like "Supplier table");
      a subtitle stating the measure, units, and period covered.
    - Below the table: a "Note:" line for scope, exclusions, and caveats
      (omit only if there is genuinely nothing to caveat), then a "Source:"
      line naming the source(s) with their [n] reference(s).
    - Example shape:
      Exhibit 3

      Three suppliers hold contracts spanning four or more departments.

      Supplier concentration by department count, contracts as at [date]

      | Supplier | Departments | Total value | Contracts |
      |----------|-------------|-------------|-----------|

      Note: excludes contracts below £100k; department count from Athena only.
      Source: [4][7]

    5. SCORECARDS ON A FIXED VECTOR SET
    - When comparing peer subjects, score every subject on the SAME fixed set
      of vectors/dimensions — never vary the vectors between subjects.
    - State the scoring legend once, before the first scorecard, and reuse it
      unchanged for every subsequent subject (e.g. a 1-5 scale with a named
      meaning for each point: "2 = Experimentation", "4 = Scaling in
      progress"). Do not invent a new scale per subject.

    6. NAMED, DATED, SOURCED EXAMPLES ("in real life" discipline)
    - Every claim that something is happening in practice must name the
      organisation, name the product/system/contract, and give a date -
      drawn from a source, never invented or approximated.
    - "Several departments are piloting X" is not acceptable on its own;
      name which departments, which system, and when, or state plainly that
      this detail was not found.

    7. ATTRIBUTED QUOTATION
    - Where a section benefits from a quotation, use a short VERBATIM
      quotation lifted from a named source document, attributed to that
      document and carrying its [n] reference.
    - Never write a synthesised or paraphrased quotation and present it as a
      quotation. If no suitable verbatim quotation exists in the evidence,
      omit the quotation rather than fabricate one.

    8. CLOSING SECTIONS
    - End the substantive analysis (before any diagnostics/reference
      appendix) with two short sections:
      - Key Uncertainties: 4-6 items describing what is genuinely unknown or
        contested in the evidence itself.
      - Big Questions: 4-6 forward-looking decisions the reader now needs to
        make, given the findings.
    - Keep both lists tight - one or two sentences per item, not paragraphs.

    9. METHODOLOGY SIDEBAR
    - Include a reader-facing "Research Methodology" note naming every
      source type drawn on and, where a score or rating was produced, how it
      was derived. This is distinct from and in addition to any internal
      Source Diagnostics / tool-call appendix elsewhere in the report.

    PROSE AND LANGUAGE
    - UK English throughout (organisation, programme, prioritise, labour).
    - No emojis, no hype adjectives ("game-changing", "cutting-edge" used as
      filler, "revolutionary"), no vague summary language, no filler verbs
      like "delve into".
    - Every superlative ("largest", "first", "only") must be directly
      supported by a cited figure or statement, not an impression.
    """,
)
