"""Domain-tuned topic/entity/relationship extraction prompt for Stage 2.

Ported from the legacy gds-idea-assurance-knowledge-graphs pipeline
(GATS_CLASSIFICATION_PROMPT_CSV in src/extraction_prompts.py), which was
iterated against real GATS business case documents in production — the
classification hard-rules and category definitions below encode that
experience (see architecture_decisions.md in the legacy repo for the
reasoning behind expanding the classification vocabulary rather than
filtering entities post-extraction).

Deviations from the legacy version:

- Response Format section replaced with the toolkit's own default
  (EXTRACT_TOPICS_PROMPT in graphrag_toolkit.lexical_graph.indexing.prompts)
  instead of ported verbatim. Legacy's version uses a bare "relationships:"
  header rather than "entity-entity relationships:" / "entity-attributes:" —
  the toolkit's parser (parse_extracted_topics) only recognises headers
  matching `entity-...s:`, so legacy's variant silently adds a stray
  "relationships:" string to every statement's details. Using the
  toolkit's own header spelling avoids this.
- The "Spend ID" classification definition is generalised to "Primary
  Identifier", since the actual ID-type classification is document-type
  dependent (Spend ID for business cases/SR bids, Contract ID for Contract
  Finder — see DocumentType.entity_classifications in document_types.py).
  Hardcoding "Spend ID" would misguide extraction on Contract Finder docs.
- Renamed away from "GATS" — this prompt is shared across all DocumentTypes,
  not just GATS business cases.
- The two near-identical legacy variants (with/without a "_CSV" suffix)
  are collapsed into one; the "_CSV" version is the more refined of the two
  (it drops an "extract entities generously" instruction the other still
  had, which legacy's own architecture notes found caused noise).

Placeholders (filled by TopicExtractor.llm.predict(...) at call time, via
GraphRAGConfig / ExtractionConfig — not by this module):
    {text}                            - the input propositions
    {preferred_topics}                - from ExtractionConfig.preferred_topics
    {preferred_entity_classifications} - from ExtractionConfig.preferred_entity_classifications
"""

TOPIC_EXTRACTION_PROMPT = """
You are a top-tier algorithm designed for extracting information in structured formats to build a knowledge graph.
Your input consists of carefully crafted propositions - simple, atomic, and decontextualized statements. Your task is to:
   1. Organize these propositions into topics
   2. Extract entities and their attributes
   3. Identify relationships between entities

Try to capture as much information from the text as possible without sacrificing accuracy. Do not add any information that is not explicitly mentioned in the input propositions.

## Topic Extraction:
   1. Read the entire set of propositions and then extract a list of specific topics. Choose from the list of Preferred Topics, but if there are no existing topics, or none of the existing topics are relevant or specific enough for some of the propositions, create a new topic. Topic names should provide a clear, highly descriptive summary of the content.
   2. Each proposition must be assigned to at least one topic - ensure no propositions are left uncategorized.
   3. For each topic, perform the following Entity Extraction and Classification and Proposition Organization tasks.

## Entity Extraction and Classification:
   1. Extract a list of ALL entities, concepts and noun phrases mentioned in the propositions within each topic. Every proposition should have at least one entity that can be extracted from it.
   2. Classify each extracted entity. Some entity classifications include:
      - Person (e.g., John Doe, Mary Jane)
      - Location (e.g., New York City, Mount Everest)
      - Committee (e.g., Investment Committee, Audit Board)
      - Organizational Unit (e.g., Board Secretariat, Portfolio Office)
      - Role (e.g., Board Secretary, Senior Business Partner)
      - Document (e.g., Outline Business Case, Programme Business Case)
      - Abbreviation (e.g., IRC, OBC, HMT, PLM)
   3. DO NOT treat numerical values, dates, times, measurements, or object attributes (e.g. size, colour) as entities.
   4. A list of Preferred Entity Classifications is included below. Use these where they fit, but if none of the preferred classifications are appropriate, create a new classification that accurately describes the entity. The goal is to capture EVERY entity - do not skip an entity because it does not fit a preferred classification.
   5. Ensure consistency in labeling entities:
      - Always use the most complete identifier for an entity (e.g., 'John Doe' instead of 'he' or 'John').
      - Maintain entity consistency throughout the knowledge graph by resolving coreferences.
      - If an entity is referred to by different names or pronouns, always use the most complete identifier.
      - If the identifier is an acronym, and you recognize the acronym, use the entity's full name instead of the acronym. DO NOT put the acronym in parentheses after the full name.
   6. Consider the context and background knowledge when extracting and classifying entities to resolve ambiguities or identify implicit references.
   7. If an entity's identity is unclear or ambiguous, include it with a disclaimer or generic label (e.g., 'unknown_person').

## Classification Rules
- **NEVER use "Company" classification in government contexts**
- **ALL private sector entities are "Supplier" - NO EXCEPTIONS**
- **Government entities are "Government Departments" - NO EXCEPTIONS**

### Definitions (focus on these categories):

1. **Programme Name**
   - Official names of large-scale strategic initiatives or multi-project programmes
   - Examples: "Digital Future Programme", "National Cybersecurity Initiative"

2. **Project Name**
   - Specific defined projects or tasks, often within a programme
   - Examples: "Project Atlas", "Orion Data Migration Task"

3. **Primary Identifier** (e.g. Spend ID, Contract ID)
   - The unique reference/tracking number assigned to this document, spend item, or contract in government tracking systems

4. **Supplier** [MANDATORY for all private entities]
   - **ANY** private sector company, organization, contractor, consultancy, or service provider
   - **INCLUDES**: All entities that provide goods/services to government
   - **MANDATORY KEYWORDS**: If text contains "awarded", "contract", "won", "supplier", "contractor" → classify as Supplier
   - Examples: "Clearsprings Ready Homes", "Mears Group", "Serco", "Migrant Help", "Accenture"
   - **CRITICAL**: Use "Supplier" - NEVER "Company", "Corporation", "Business", or "Contractor"

5. **Thematic Topic of Digital**
   - Core digital concepts, strategies, or large-scale digital systems/platforms
   - Examples: "Cloud Adoption framework", "National Digital ID System"

6. **Technological Application**
   - Software products, platforms, hardware, languages, libraries, frameworks
   - Examples: "AWS S3", "TensorFlow", "Salesforce CRM"

7. **Government Departments** [MANDATORY for all government entities]
   - **ONLY** government bodies, departments, ALBs, public sector institutions
   - Examples: "Ministry of Justice", "Home Office", "Cabinet Office"
   - **CRITICAL**: Use "Government Departments" - NEVER "Organisation", "Organization", "Agency", "Department", or "Government"

8. **Arm's Length Body**
   - Public bodies that operate with some independence from ministers but are accountable to government
   - Includes executive agencies, NDPBs, and other sponsored bodies
   - Examples: "HMRC", "Environment Agency", "Ofsted", "UK Export Finance"

9. **Contract**
   - Named or referenced legal agreements between government and suppliers
   - Examples: "ELT Operations Contract", "Managed Service Agreement", "Call-off Contract 2024"

10. **Service**
    - Named government services or capabilities delivered to citizens or internal users
    - Examples: "English Language Testing", "Universal Credit", "Verify", "Biometric Residence Permit"

11. **Legislation**
    - Acts of Parliament, statutory instruments, or regulations that mandate or constrain action
    - Examples: "Public Contracts Regulations 2015", "Data Protection Act 2018", "Equality Act 2010"

12. **Framework**
    - Procurement frameworks, commercial frameworks, or strategic frameworks used to structure delivery
    - Examples: "G-Cloud", "Digital Outcomes and Specialists", "Technology Code of Practice"

13. **Risk**
    - Named or described risks, threats, or issues that could impact delivery
    - Examples: "supplier failure", "data breach risk", "single point of failure", "cost overrun"

14. **Benefit**
    - Explicit advantages, outcomes, or value propositions expected from a programme or project
    - Examples: "cost reduction", "increased user engagement", "faster deployment", "fraud prevention"

15. **Milestone**
    - Specific delivery milestones, key dates, or phase gates in a programme timeline
    - Examples: "Full Business Case approval", "Go-Live date", "Phase 2 completion", "contract award"

16. **KPI**
    - Key performance indicators, metrics, or targets used to measure success
    - Examples: "99.9% availability", "80% user satisfaction", "cost per transaction"

17. **SLA**
    - Service Level Agreements or specific contractual service commitments
    - Examples: "P1 incident response within 1 hour", "99.5% uptime SLA", "monthly reporting SLA"

18. **Obligation**
    - Contractual or legal obligations on either party (supplier or government)
    - Examples: "anti-fraud measures", "data handling requirements", "TUPE obligations", "security clearance"

19. **Commercial Model**
    - The contractual or pricing structure used to deliver a service
    - Examples: "fixed price", "time and materials", "outcome-based", "gain share", "managed service"

20. **Strategic Objective**
    - High-level goals from departmental strategies, spending reviews, or manifesto commitments
    - Examples: "net zero by 2050", "levelling up", "digital transformation of public services"

21. **Finding**
    - Conclusions or findings from audits, reviews, or assurance activities
    - Examples: "NAO found inadequate cost controls", "gateway review rated amber/red"

22. **Recommendation**
    - Specific recommendations from audits, reviews, or oversight bodies
    - Examples: "PAC recommended improved supplier oversight", "review recommended re-baselining"

23. **Methodology**
    - Structured approaches or frameworks for planning, executing, evaluating work
    - Examples: "Agile Scrum", "PRINCE2", "Design Thinking", "Five Case Model"

24. **System**
    - Named IT systems, platforms, or applications (internal or supplier-operated)
    - Examples: "Caseworking System", "Atlas", "Content Management System", "Legacy Mainframe"

25. **Spending Control**
    - Government spending controls or approval processes
    - Examples: "Cabinet Office Spend Control", "Digital Spend Control", "Commercial Spend Control"

26. **Assurance Review**
    - Named assurance or review processes applied to programmes
    - Examples: "IPA Gateway Review", "Integrated Assurance and Approval Plan", "CDDO assessment"

### ENFORCEMENT RULES:
- **FORBIDDEN CLASSIFICATIONS**: "Company", "Corporation", "Business", "Contractor", "Agency", "Department", "Organisation"
- **REQUIRED**: Every private entity → "Supplier", Every government entity → "Government Departments"
- **CONTEXT CLUES**: Contract language = "Supplier", Government role = "Government Departments"

## Proposition Organization:
   1. For each topic, identify the relevant propositions that belong to that topic.
   2. Use these propositions exactly as they appear - DO NOT rephrase or modify them.
   3. For each proposition, extract relationships as described below.
   4. CRITICAL: Every single input proposition MUST appear in your output. Do NOT skip any proposition.

## Relationship Extraction:
   1. For each proposition, extract all relationships between entities, and between entities and their attributes.
   2. Ensure consistency and generality in relationship types:
      - Use general and timeless relationship types (e.g., 'VALUE' instead of 'HAD_VALUE').
      - Avoid overly specific or momentary relationship types.
      - Prefer one- or two-word relationship types.
      - Prefer an active voice and the present tense when formulating relationship types.
   3. Relationship names should be all uppercase, with underscores instead of spaces (e.g. 'WORKS_FOR')
   4. Complex facts may be expressed through multiple relationship pairs, sometimes arranged in a hierarchy.

   ### Common relationship patterns:
   - Entity-entity: John Doe|WORKS_FOR|Acme Inc.
   - Entity-attribute: John Doe|OCCUPATION|software engineer
   - Hierarchical: Project X|PART_OF|Acme Inc.
   - Acronyms and definitions: IRC|ABBREVIATION|Immigration Removal Centre
   - Approvals and decisions: Investment Committee|APPROVED|English Language Testing OBC
   - Actions and events: Panel|ENQUIRED_ABOUT|contract value
   - Conditions: approval|SUBJECT_TO|all conditions being met
   - Roles: Camille Johnson|ROLE|Senior Portfolio Business Partner

   ### Handling difficult propositions:
   If a proposition does not contain a clear entity-entity relationship, you MUST still include it.
   Use the most relevant entity as subject with a descriptive relationship:
   - "The budget has increased due to contract length changes." → budget|INCREASED_DUE_TO|contract length changes
   - "There isn't a separate pot approved for the work." → separate funding pot|STATUS|not approved
   - "The document is page 3 of 7." → document|PAGE|3 of 7

## CRITICAL: Entity Name Consistency
When writing relationship lines, you MUST use entity names EXACTLY as they appear in your entities list.
- If your entity list says "Home Office|Government Departments", write "Home Office|WORKS_WITH|..." NOT "The Home Office|..."
- If your entity list says "Independent Child Trafficking Guardians|Service", write "Independent Child Trafficking Guardians|..." NOT "ICTG|..." or "the ICTG service|..."
- NEVER add articles (a, an, the) to entity names in relationship lines
- NEVER abbreviate entity names in relationship lines
- NEVER add extra words (like "service", "programme") that aren't in the entity list name
- Every entity that appears as subject or object in a relationship line MUST exist in the entities list above it
- If you need to reference something not in the entity list, ADD it to the entity list first

## CRITICAL: Entity Reuse Across Topics
If an entity appears in relationships under MULTIPLE topics, it MUST be listed in the
entities section of EVERY topic where it is referenced in relationships. Do NOT assume
entities carry over between topics. Each topic's entity list must be self-contained —
include ALL entities referenced in that topic's relationship lines.

## Final Validation Step:
Before outputting your response, validate:
1. Check each entity classification against the FORBIDDEN list ("Organisation", "Company",
   "Corporation", "Business", "Contractor", "Agency", "Department")
   - Private/voluntary/charity entities → change to "Supplier"
   - Government entities → change to "Government Departments"
2. Every entity referenced in a relationship line exists in that topic's entity list
3. Entity names in relationship lines match EXACTLY what's in the entity list

## Response Format:
topic: topic

  entities:

    entity|classification
    entity|classification

  proposition: [exact proposition text]

    entity-entity relationships:
    entity|RELATIONSHIP|entity
    entity|RELATIONSHIP|entity

    entity-attributes:
    entity|ATTRIBUTE_NAME|value
    entity|ATTRIBUTE_NAME|value

  proposition: [exact proposition text]

    entity-entity relationships:
    entity|RELATIONSHIP|entity
    entity|RELATIONSHIP|entity

    entity-attributes:
    entity|ATTRIBUTE_NAME|value
    entity|ATTRIBUTE_NAME|value



## Quality Criteria:
   The extracted results should be:
   - Complete: EVERY input proposition must appear in the output - no exceptions
   - Accurate: Faithfully represent the information without adding or omitting details
   - Consistent: Use consistent entity labels, types, relationship types, and adhere to the specified format

## Strict Compliance:
   - Use propositions exactly as provided - do not rephrase or modify them
   - Assign every proposition to at least one topic
   - EVERY proposition MUST appear in your output with at least one relationship
   - Follow the specified format exactly
   - Do not provide any other explanatory text
   - Extract only information explicitly stated in the propositions

Adhere strictly to the provided instructions. Non-compliance will result in termination.

<propositions>
{text}
</propositions>

<preferredTopics>
{preferred_topics}
</preferredTopics>

<preferredEntityClassifications>
{preferred_entity_classifications}
</preferredEntityClassifications>
""".strip()
