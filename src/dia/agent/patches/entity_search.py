"""Patch: rewrite the multi-entity graph search query for performance.

The library's built-in query for "find facts connecting multiple entities"
has two problems on Neptune:
  1. It filters `WHERE s IN entities AND o IN entities` using a list of node
     OBJECTS — Neptune's openCypher planner handles node-object membership
     checks very poorly at scale.
  2. It computes the full statement path for EVERY matched fact before LIMIT
     is applied, in a single query — so cost scales with the whole matched
     set, not the limited result.

Profiling showed the original query timing out at 90s even on a modest
62-entity hub. This patch replaces it with:
  1. id-set anchoring — compare by id() against a plain id list, not node
     objects.
  2. a two-step split — query A returns a LIMIT-bounded set of fact ids;
     query B maps only those facts to statements. (90s -> 8s on the same hub.)
  3. an entity cap (_ENTITY_CAP = 50) — mega-hubs (1000+ expanded entities)
     still timed out because query A unwinds every entity; capping the
     entity set fixes this with identical output in testing (90s -> ~9s).

Also handles a return-type contract difference between graphrag-toolkit
versions: older versions expect this function to return SearchResult
objects; newer versions expect raw statement ids (they finalise the result
themselves). Detected once via _entity_search_returns_raw_ids() by inspecting
do_graph_search's source.
"""

import inspect as _inspect
import logging

from graphrag_toolkit.lexical_graph.retrieval.retrievers import EntityBasedSearch

logger = logging.getLogger(__name__)


def apply() -> None:
    """Patch EntityBasedSearch._multiple_entity_based_graph_search in place.

    Idempotent: safe to call more than once — guarded by checking for
    `_unpatched_multiple_entity_based_graph_search`, which only gets set on
    the first call.
    """

    def _entity_search_returns_raw_ids() -> bool:
        try:
            src = _inspect.getsource(EntityBasedSearch.do_graph_search)
        except (OSError, TypeError):
            return False
        # Newer version does set() on the collected ids then calls the helper
        # once at the end of do_graph_search.
        return "set(statement_ids)" in src and "get_statements_by_topic_and_source" in src

    _RETURN_RAW_IDS = _entity_search_returns_raw_ids()

    def _finalise_entity_search_result(self, statement_ids):
        # Newer library: return raw ids (do_graph_search finalises them).
        if _RETURN_RAW_IDS:
            return statement_ids
        # Older library: finalise here into SearchResult objects.
        return self.get_statements_by_topic_and_source(statement_ids)

    # Profiling: on a mega-hub (1039 expanded entities) cap=150 ran in ~56s
    # (A=55s) -- too close to the 90s read timeout, tips over under load. cap=50
    # ran in ~9s with IDENTICAL output (same statements). 50 is the safe value.
    _ENTITY_CAP = 50

    if not hasattr(EntityBasedSearch, "_unpatched_multiple_entity_based_graph_search"):
        EntityBasedSearch._unpatched_multiple_entity_based_graph_search = (
            EntityBasedSearch._multiple_entity_based_graph_search
        )

        def _patched_multiple_entity_based_graph_search(self, start_id, end_ids, query):
            logger.debug(
                "Starting (id-set, two-step, capped) multiple-entity search [start_id: %s, end_ids: %s]",
                start_id,
                end_ids,
            )
            node_id = self.graph_store.node_id
            statement_limit = self.args.intermediate_limit
            # Gather a few candidate facts per wanted statement (bounded).
            fact_limit = statement_limit * 3

            # Query A: expand entities, cap the set, find a bounded set of facts.
            facts_cypher = f"""// entity search step A: bounded facts (capped, id-set anchored)
            MATCH p=(e1:`__Entity__`{{{node_id("entityId")}:$startId}})-[:`__RELATION__`*1..2]-(e2:`__Entity__`)
            WHERE {node_id("e2.entityId")} in $endIds
            UNWIND nodes(p) AS n
            WITH DISTINCT {node_id("n.entityId")} AS eid LIMIT $entityCap
            WITH COLLECT(eid) AS entityIds
            UNWIND entityIds AS sid
            MATCH (s:`__Entity__`)-[:`__SUBJECT__`]->(f)<-[:`__OBJECT__`]-(o:`__Entity__`)
            WHERE {node_id("s.entityId")} = sid AND {node_id("o.entityId")} IN entityIds
            RETURN DISTINCT {node_id("f.factId")} AS f LIMIT $factLimit
            """
            fact_rows = self.graph_store.execute_query(
                facts_cypher,
                {
                    "startId": start_id,
                    "endIds": end_ids,
                    "entityCap": _ENTITY_CAP,
                    "factLimit": fact_limit,
                },
            )
            fact_ids = [r["f"] for r in fact_rows]
            if not fact_ids:
                return _finalise_entity_search_result(self, [])

            # Query B: map only those facts to their statements.
            statements_cypher = f"""// entity search step B: facts -> statements
            UNWIND $factIds AS fid
            MATCH (f)-[:`__SUPPORTS__`]->()-[:`__PREVIOUS__`*0..1]-(l)
            WHERE {node_id("f.factId")} = fid
            RETURN DISTINCT {node_id("l.statementId")} AS l LIMIT $statementLimit
            """
            statement_rows = self.graph_store.execute_query(
                statements_cypher,
                {"factIds": fact_ids, "statementLimit": statement_limit},
            )
            statement_ids = [r["l"] for r in statement_rows]
            return _finalise_entity_search_result(self, statement_ids)

        EntityBasedSearch._multiple_entity_based_graph_search = _patched_multiple_entity_based_graph_search
