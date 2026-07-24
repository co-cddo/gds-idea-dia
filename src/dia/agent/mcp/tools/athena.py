"""MCP tool: Athena SQL queries."""

import json
from typing import Any

import awswrangler as wr
from boto3 import session


def check_sql_safety(sql: str) -> None:
    """Block dangerous SQL keywords. Raises ValueError if anything other than SELECT."""
    up = sql.upper().strip()
    forbidden = ["DROP", "DELETE", "INSERT", "UPDATE", "ALTER", "CREATE", "GRANT", "REVOKE"]
    if any(f" {cmd} " in f" {up} " for cmd in forbidden):
        raise ValueError("Only SELECT statements are allowed.")


def list_athena_tables() -> str:
    """
    Lists all available Athena tables across the three databases:
    - assurance_contracts: LLM-extracted contracts with digital spend classification, GMPP project data,
      and digital workforce metrics (workforce_commision_26)
    - gats-assurance-ai: GATS spend controls cases and SR bids
    - gats-assurance: GDS Service Standard assessments per government service

    Call this first when the user asks for financial data, contract values, structured queries,
    or service assessment outcomes.
    """
    tables: dict[str, Any] = {}
    for db in [ATHENA_CONTRACTS_DB, ATHENA_GATS_DB, ATHENA_GATS_SERVICE_DB]:
        try:
            tables[db] = sorted(t["Name"] for t in wr.catalog.get_tables(database=db, boto3_session=session))
        except Exception as e:
            tables[db] = [f"Error: {e}"]
    return json.dumps(tables, indent=2)


def get_table_schema(database_name: str, table_name: str) -> str:
    """
    Returns column names and data types for a specific Athena table.

    Available databases:
    - 'assurance_contracts': Contains two tables:
      1. 'extracted_contracts' — LLM-extracted contracts with columns:
         id, ocid, buyer_name, buyer_category, seller_name, title, status, date, end_date,
         value, currency, n_documents, total_document_length, digital_procurement_level,
         relevant_text, relevant_tables, digital_spend_category, digital_spend_description,
         digital_spend_secondary, lifecycle_stage, delivery_model, named_commercial_technologies
      2. 'gmpp_24_25' — GMPP/NISTA government project spend overview with columns:
         Project Name, Department, Annual Report Category, Project Description,
         IPA Delivery Confidence Assessment, SRO Delivery Confidence Assessment,
         Departmental Commentary on Delivery Confidence Assessment Rating,
         Start Date, End Date, Schedule Narrative, Financial Year Baseline (£m),
         Financial Year Forecast (£m), Financial Year Variance (%),
         In Year Variance Narrative, Whole Life Cost (£m), Costs Narrative,
         Benefits (£m), Benefits Narrative,
         Does the project have an evaluation plan? (self reported),
         Senior Responsible Owner (SRO) Name, GMPP ID
         Use this table to cross-reference projects found in graph search against
         official GMPP/NISTA spend and delivery confidence data.
      3. 'workforce_commision_26' — digital workforce metrics per role/commission with columns:
         ingestion_date, commission_id, department, alb_agency_organisation, postcode, region,
         profession, dept_job_title, role_group, job_role, role_level, indicative_grades,
         employee_grade, resource_type, role_status, if_resource_contractor_tenure,
         if_resource_contractor_framework, gender, ethnicity, age, religion, disability,
         fte_person, gross_base_salary_actual_not_fte, location_related_allowance_actual_not_fte,
         all_other_allowances_rra_actual_not_fte, total_pay_actual_salary_plus_actual_allowances,
         contractor_day_rate_excluding_vat_agency_fees, quarter, quarter_start, internal_id,
         position_id, location, indictive_grade, employment_type, allowances, post_code,
         role_summary, if_resource_contractor_deployment_rationale, department_name,
         wfc_department_column, wfc_alb_agency_business_unit_or_organisation,
         performance_commission_naming, wfc_commission, department_alb_combined,
         public_dataset_mapping
         Use this table for digital/DDaT workforce headcount (FTE), grade and role mix,
         contractor vs civil-servant resourcing, pay and day-rate analysis, and diversity
         breakdowns by department/ALB. All columns are stored as strings.
    - 'gats-assurance-ai': GATS spend controls with columns like TotalValueRequested,
      TotalValueApproved, OrganisationSubmitter, CaseRefNo, Name, RiskScore, Status
    - 'gats-assurance': GDS Service Standard assessment data. Contains:
      'service_assessments_snapshot20251217' — one row per service assessment with columns:
         latest_update, service_id, service_name, department, crossgov_departmental,
         stage (Alpha/Beta/Live), type, assessment_date, outcome (Met/Not Met),
         points_notmet_1, points_notmet_2, ..., points_notmet_11
         Use this table to identify which of a department's services have been assessed
         against the GDS Service Standard, at which delivery stage, with what outcome,
         and which Standard points were most commonly not met.

    CRITICAL: Always call this before writing SQL to confirm exact column names.
    """
    clean_name = table_name.strip().replace('"', "").replace("'", "")
    try:
        df_types = wr.catalog.get_table_types(database=database_name, table=clean_name, boto3_session=session)
        return json.dumps(df_types, indent=2)
    except Exception as e:
        return f"Error: {e}"


def execute_sql(database_name: str, query: str) -> str:
    """
    Executes a read-only Athena SQL query against the specified database.

    Available databases:
    - 'assurance_contracts': Digital spend contracts, GMPP project data, and digital workforce
      metrics (workforce_commision_26) (workgroup: assurance-contracts)
    - 'gats-assurance-ai': GATS spend controls and SR bids
    - 'gats-assurance': GDS Service Standard assessments (table: service_assessments_snapshot20251217)

    GUIDELINES:
    1. Use standard ANSI SQL compatible with Athena (Presto/Trino).
    2. Always LIMIT results (max 50 rows) unless aggregating.
    3. For contracts: query digital_spend_category, buyer_name, seller_name, value etc.
    4. For GMPP: query "Project Name", "Department", "Whole Life Cost (£m)", "IPA Delivery Confidence Assessment" etc.
    5. For GATS: query TotalValueRequested, OrganisationSubmitter, RiskScore etc.
    6. For Service Standard: query service_name, department, stage, outcome,
       points_notmet_1..points_notmet_11 from service_assessments_snapshot20251217.
       Database name 'gats-assurance' contains a hyphen so wrap it in double quotes
       in fully-qualified references: "gats-assurance".service_assessments_snapshot20251217.
       To count failures across the 11 points columns, use COALESCE/CASE per column or
       UNNEST(ARRAY[points_notmet_1, ..., points_notmet_11]) and filter non-null/non-empty.
    7. Only SELECT statements are allowed.
    8. Table names with hyphens (e.g. sr-bid-structured-data) MUST be wrapped in backticks: `sr-bid-structured-data`.
       Column names with spaces or special characters must also be quoted with double quotes.
    9. DEPARTMENT NAME MATCHING: Data uses inconsistent casing and naming. Always use
       case-insensitive matching with LOWER() and try multiple variants. Example:
       WHERE LOWER(buyer_name) LIKE '%home office%' OR LOWER(buyer_name) LIKE '%ho%'
       For HMRC use: LOWER(col) LIKE '%hmrc%' OR LOWER(col) LIKE '%hm revenue%'
       OR LOWER(col) LIKE '%revenue and customs%'
       For MoJ use: LOWER(col) LIKE '%moj%' OR LOWER(col) LIKE '%ministry of justice%'
       For DfE use: LOWER(col) LIKE '%dfe%' OR LOWER(col) LIKE '%department for education%'
       Always use LIKE with wildcards rather than exact equality for department filtering.
    """
    check_sql_safety(query)

    if database_name == ATHENA_CONTRACTS_DB:
        workgroup = ATHENA_CONTRACTS_WORKGROUP
    else:
        # Both 'gats-assurance-ai' and 'gats-assurance' use the GATS workgroup
        workgroup = ATHENA_GATS_WORKGROUP

    try:
        df = wr.athena.read_sql_query(
            sql=query,
            database=database_name,
            workgroup=workgroup,
            boto3_session=session,
            ctas_approach=False,
        )
        if df.empty:
            return "Query returned 0 rows."
        return df.to_string(index=False)
    except Exception as e:
        return f"Query error: {e}"


def register(mcp_server) -> None:
    """Register all Athena tools onto an already-built MCP server."""
    mcp_server.tool()(list_athena_tables)
    mcp_server.tool()(get_table_schema)
    mcp_server.tool()(execute_sql)
