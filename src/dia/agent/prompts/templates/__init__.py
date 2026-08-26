from dia.agent.prompts.templates.ai_transformation import (
    get_ai_transformation_system_prompt,
    get_ai_transformation_system_prompt_v2,
)
from dia.agent.prompts.templates.dbr import get_dbr_system_prompt
from dia.agent.prompts.templates.default import get_default_system_prompt
from dia.agent.prompts.templates.gats_query import get_gats_query_system_prompt
from dia.agent.prompts.templates.graph_cost_aware import get_graph_cost_aware_system_prompt
from dia.agent.prompts.templates.pitch_deck import get_pitch_deck_system_prompt
from dia.agent.prompts.templates.project_investigation import get_project_investigation_system_prompt
from dia.agent.prompts.templates.sovereign_stack import get_sovereign_stack_system_prompt_v3
from dia.agent.prompts.templates.supplier_ecosystem import get_supplier_ecosystem_system_prompt
from dia.agent.prompts.templates.supplier_lockin import get_supplier_lockin_system_prompt
from dia.agent.prompts.templates.targeted_question import get_targeted_question_system_prompt

# NOTE: get_sovereign_stack_system_prompt (v1) is intentionally NOT exported.
# v3 supersedes it (adds Cabinet Office to graph coverage, identical structure
# otherwise). Add a v1 template if you need to reproduce the older 8-department
# coverage list.

__all__ = [
    "get_dbr_system_prompt",
    "get_default_system_prompt",
    "get_gats_query_system_prompt",
    "get_project_investigation_system_prompt",
    "get_supplier_lockin_system_prompt",
    "get_supplier_ecosystem_system_prompt",
    "get_sovereign_stack_system_prompt_v3",
    "get_targeted_question_system_prompt",
    "get_pitch_deck_system_prompt",
    "get_graph_cost_aware_system_prompt",
    "get_ai_transformation_system_prompt",
    "get_ai_transformation_system_prompt_v2",
]
