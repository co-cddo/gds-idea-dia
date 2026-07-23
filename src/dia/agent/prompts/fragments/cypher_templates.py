"""openCypher query templates for Neptune graph visualisation.

Restored from the original src/system_prompts.py prompts that previously
embedded these queries inline. These templates are emitted into the relevant
prompts so the agent has a starting point for the visualisation queries it
must produce.
"""
from __future__ import annotations

from prompts.fragments.utils import block


PROJECT_CYPHER_TEMPLATES = block(
    "project_cypher_templates",
    """
    NEPTURE openCYPHER — PROJECT VISUALISATION TEMPLATES

    Provide an openCypher query that can be run against the Neptune graph to visualise
    this project's entity neighbourhood. The query should:
    - find the entity node(s) matching the project name
    - traverse 2 hops outward to get connected entities
    - return nodes and relationships for graph visualisation
    - include entity labels and key properties

    ### Template A — full neighbourhood (2 hops)

    ```cypher
    // Visualise [PROJECT NAME] and its connections in Neptune
    // Run this in the Neptune notebook or console

    MATCH (p)-[r1]-(connected1)
    WHERE p.value CONTAINS '[project_name]'
       OR p.value CONTAINS '[alternative_name]'
    OPTIONAL MATCH (connected1)-[r2]-(connected2)
    WHERE connected2 <> p
    RETURN p, r1, connected1, r2, connected2
    LIMIT 100
    ```

    ### Template B — cross-source connections only

    ```cypher
    // Cross-source connections for [PROJECT NAME]
    // Shows entities that appear in multiple document types

    MATCH (p)-[r1]-(chunk1)-[r2]-(doc1)
    WHERE p.value CONTAINS '[project_name]'
      AND doc1.document_type IS NOT NULL
    WITH p,
         collect(DISTINCT doc1.document_type) AS doc_types,
         collect(DISTINCT {node: chunk1, rel: r1}) AS connections
    WHERE size(doc_types) > 1
    RETURN p.value AS entity, doc_types, size(connections) AS connection_count
    ORDER BY connection_count DESC
    LIMIT 50
    ```

    Adapt the queries based on what you found:
    - replace placeholder names with exact project / alternative-name strings from the graph
    - if you found specific entity IDs, use them directly (`WHERE id(p) IN ['id1', 'id2']`)
    - add OR conditions for abbreviations and full names
    - include label filters where helpful (e.g. `WHERE labels(p) = ['__Entity__']`)

    Both queries MUST be syntactically valid openCypher for Neptune.
    """,
)


SUPPLIER_LOCKIN_CYPHER_TEMPLATES = block(
    "supplier_lockin_cypher_templates",
    """
    NEPTUNE openCYPHER — SUPPLIER NETWORK VISUALISATION TEMPLATES

    Provide two openCypher queries that can be run against the Neptune graph to visualise
    the supplier dependency network discovered in this assessment.

    ### Query A — full supplier network (suppliers, projects, departments)

    ```cypher
    // Supplier lock-in network — suppliers linked to programmes and departments
    // Adapt supplier names based on what was found in the graph

    MATCH (s)-[r1]-(chunk1)-[r2]-(doc1)
    WHERE s.value IN ['[SUPPLIER_1]', '[SUPPLIER_2]', '[SUPPLIER_3]']
    WITH s, collect(DISTINCT doc1) AS docs, collect(DISTINCT chunk1) AS chunks
    UNWIND chunks AS c
    MATCH (c)-[rc]-(neighbour)
    WHERE neighbour.value IS NOT NULL
      AND neighbour <> s
    RETURN s, rc, neighbour
    LIMIT 150
    ```

    ### Query B — programme-centric view (programmes linked to multiple suppliers)

    ```cypher
    // Programmes with multiple supplier dependencies
    // Shows which projects are most exposed to supplier concentration

    MATCH (prog)-[r1]-(chunk1)-[r2]-(doc1)
    WHERE prog.value IN ['[PROGRAMME_1]', '[PROGRAMME_2]', '[PROGRAMME_3]']
    WITH prog, collect(DISTINCT chunk1) AS chunks
    UNWIND chunks AS c
    MATCH (c)-[rc]-(entity)
    WHERE entity.value IS NOT NULL
      AND entity <> prog
    RETURN prog, rc, entity
    LIMIT 150
    ```

    Adapt both queries based on what was found:
    - replace placeholder names with exact supplier / programme values from the graph
    - add OR conditions if a name appears in multiple variants (e.g. abbreviations)
    - add label filters where helpful (e.g. `AND labels(entity) = ['__Entity__']`)
    - if specific entity IDs were returned, use them directly:
      `WHERE id(s) IN ['id1', 'id2']`

    Both queries MUST be syntactically valid openCypher for Neptune.
    """,
)
