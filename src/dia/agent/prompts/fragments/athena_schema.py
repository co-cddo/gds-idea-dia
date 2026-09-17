"""Athena database / table / column reference fragments.

Restored from the operational detail in src/system_prompts.py during the modular
prompts migration. These blocks are the canonical schema reference shared by every
prompt that issues SQL.
"""

from __future__ import annotations

from dia.agent.prompts.fragments.utils import block

ATHENA_SCHEMA_REFERENCE = block(
    "athena_schema_reference",
    """
    ATHENA — STRUCTURED DATA REFERENCE

    Always call `list_athena_tables` first, then `get_table_schema` for any table
    before writing SQL. Never assume column names or types.

    Common cautions:
    - many columns are STRING type even when they hold numbers or dates
    - spend amounts are often formatted strings (e.g. "41,464,000" or "£41,464,000")
      Use: TRY_CAST(REPLACE(REPLACE(<col>, ',', ''), '"', '') AS BIGINT)
    - dates may be strings like "13-Sep-23" or "01 June 2023"
    - department names need flexible matching with LOWER() + LIKE
    - hyphenated database names must be wrapped in double quotes in SQL
      (e.g. "gats-assurance".service_assessments_snapshot20251217)
    - Yes/No columns: filter with = 'Yes' or = 'No' (case-sensitive as stored)

    ### `gats-assurance-ai` database — GATS approval pipeline + SR25 summary

    GATS spend controls table — key columns:
    - TotalValueRequested, TotalValueApproved, RiskScore, Status,
      OrganisationSubmitter, CaseRefNo, Name, Stage

    SR25 structured data (table name has hyphens — wrap in backticks):
    - department, total_rdel, total_cdel, rdel_uplift, cdel_uplift, benefit_cost_ratio

    Use for: requested vs approved, risk scores, pipeline status, RDEL/CDEL totals.
    Cross-reference Spend IDs and programme names found in the graph.

    ### `assurance_contracts.extracted_contracts` — Contract spend amounts

    Key columns:
    - buyer_name (department/organisation purchasing — match with LOWER()+LIKE)
    - seller_name (supplier)
    - title, value, currency
    - digital_spend_category, digital_spend_description
    - lifecycle_stage, delivery_model
    - named_commercial_technologies
    - status, date, end_date

    Use for: exact contract values per supplier, spend by category, spend by department,
    extensions / direct awards (via lifecycle_stage), named tech (Dynamics 365, Salesforce, etc.).

    ### `assurance_contracts.gmpp_24_25` — GMPP/NISTA major project oversight

    Key columns:
    - "Project Name", Department, "Annual Report Category", "Project Description"
    - "IPA Delivery Confidence Assessment" (Green/Amber/Red)
    - "SRO Delivery Confidence Assessment"
    - "Departmental Commentary on Delivery Confidence Assessment Rating"
    - "Start Date", "End Date", "Schedule Narrative"
    - "Financial Year Baseline (£m)", "Financial Year Forecast (£m)", "Financial Year Variance (%)"
    - "In Year Variance Narrative"
    - "Whole Life Cost (£m)", "Costs Narrative"
    - "Benefits (£m)", "Benefits Narrative"
    - "SRO Name", "GMPP ID"

    Use for: cross-referencing graph-found projects against IPA delivery confidence,
    whole life cost, and variance data. Many column names contain spaces — wrap in double quotes.

    ### `assurance_contracts.spend_controls_data_export` — GATS spend controls full export

    The most detailed GATS dataset (262 columns). Each row = one spend control case.

    Identification & status:
    - co_spendid (unique case ref, e.g. "COSC-00103")
    - co_organisationsubmitter (department/org)
    - co_casename, co_shortdescription
    - co_casestatus ("Assure" / "Withdrawn" / "Approve")
    - co_caseriskrating ("High" / "Medium" / "Low" / "Unspecified")
    - co_assurancerating, co_fullcasedecision
    - co_casesubmitdate, co_assuranceratingdate

    Money & timing:
    - co_spendamount (formatted string, e.g. "41,464,000")
    - co_approvalamount
    - co_spendstartdate, co_spendenddate, co_contractenddate
    - co_dt_ri_expectedannualcost, co_dt_ri_valueinitialterm, co_dt_ri_contractduration

    Categorisation:
    - co_spendcategory, co_dt_spendcategory
    - co_spendtype, co_businessunit

    Commercial:
    - co_commercialapproach (Open tender / Direct award / etc.)
    - co_directaward_yesno
    - co_contractextension_yesno
    - co_currentsupplier, co_proposedsupplier
    - co_hmt_yesno

    Risk & domain flags:
    - co_aiquantum_yesno, co_dt_ri_aiquantum
    - co_dt_ri_emergetech
    - co_gmpp_yesno, co_dt_ri_gmpp, co_dt_ri_ipa
    - co_legacytech_yesno
    - co_criticalnationalinfra_yesno
    - co_publicfacing, co_useonelogin

    Delivery & service:
    - co_dt_phase
    - co_dt_reqserviceassessment
    - co_sroname, co_controlsassessor, co_emailsubmitter
    - co_dt_ri_transactionsperyear

    Service Standard compliance flags (one per Standard point):
    - co_serstd_understand_users
    - co_serstd_wholeproblem
    - co_serstd_joinedup
    - co_serstd_simpletouse
    - co_serstd_everyonecanuse
    - co_serstd_multidisciplinaryteam
    - co_serstd_agile
    - co_serstd_iteration
    - co_serstd_securityprivacy
    - co_serstd_performance
    - co_serstd_toolsandtech
    - co_serstd_opensource
    - co_serstd_openstandards
    - co_serstd_reliableservice

    Data & accessibility compliance:
    - co_meetwcag_yesno
    - co_accessibilitystatement_yesno
    - co_gdprcompliant_yesno
    - co_datamanagementplan_yesno
    - co_cyberassessmentframework_yesno
    - co_securebydesign_high_yesno
    - co_usedesignsystem

    Use for: counting/filtering cases by AI involvement, spend thresholds, organisation,
    case status, risk rating, commercial approach, legacy tech, GMPP status, direct awards,
    extensions, service standard compliance, and accessibility.

    ### `assurance_contracts.workforce_commision_26` — Digital workforce metrics

    One row per role/resource. Digital & DDaT workforce data submitted per workforce
    commission. All columns are STRING type — cast numeric columns before aggregating.

    Identification & organisation:
    - commission_id, wfc_commission, performance_commission_naming
    - department, department_name, wfc_department_column, department_alb_combined
    - alb_agency_organisation, wfc_alb_agency_business_unit_or_organisation
    - region, location, postcode, post_code
    - quarter, quarter_start, ingestion_date, internal_id, position_id

    Role & grade:
    - profession, dept_job_title, role_group, job_role, role_summary
    - role_level, indicative_grades, indictive_grade, employee_grade
    - role_status, employment_type, resource_type
    - public_dataset_mapping

    Contractor detail (populated when resource is a contractor):
    - if_resource_contractor_tenure
    - if_resource_contractor_framework
    - if_resource_contractor_deployment_rationale
    - contractor_day_rate_excluding_vat_agency_fees

    Pay & headcount (formatted numeric strings — TRY_CAST before SUM/AVG):
    - fte_person
    - gross_base_salary_actual_not_fte
    - location_related_allowance_actual_not_fte
    - all_other_allowances_rra_actual_not_fte
    - allowances
    - total_pay_actual_salary_plus_actual_allowances

    Diversity:
    - gender, ethnicity, age, religion, disability

    Use for: digital/DDaT headcount (FTE) by department/ALB, grade and role mix,
    contractor vs civil-servant resourcing and day-rate analysis, pay/allowance totals,
    and diversity breakdowns. Match departments with LOWER() + LIKE on `department`,
    `department_name`, or `department_alb_combined`. Cross-reference efficiency plans in
    `kb_search_efficiency_reports` and SR25 workforce asks in `kb_search_sr25_bids`.

    ### `gats-assurance.service_assessments_snapshot20251217` — Service Standard assessments

    Database name has a hyphen — qualify as "gats-assurance".service_assessments_snapshot20251217.

    Key columns:
    - latest_update, service_id, service_name
    - department, crossgov_departmental
    - stage (Alpha / Beta / Live), type, assessment_date
    - outcome (Met / Not Met)
    - points_notmet_1 .. points_notmet_11

    Use for: which of the department's services have been assessed, at which stage,
    with what outcome, which Service Standard points the department most often fails.

    See `<service_standard_source>` for cross-source triangulation rules.
    """,
)


GATS_QUESTION_COLUMN_MAP = block(
    "gats_question_to_column_map",
    """
    GATS — QUESTION TO COLUMN MAP

    These map common natural-language questions to the column they should query in
    `assurance_contracts.spend_controls_data_export`:

    - "Does this spend involve AI?" -> co_aiquantum_yesno or co_dt_ri_aiquantum
    - "Is this on GMPP?" -> co_gmpp_yesno or co_dt_ri_gmpp
    - "What is the IPA rating?" -> co_dt_ri_ipa
    - "Is this a direct award?" -> co_directaward_yesno
    - "Is it a contract extension?" -> co_contractextension_yesno
    - "Does it involve legacy tech?" -> co_legacytech_yesno
    - "Is it public-facing?" -> co_publicfacing
    - "Does it use One Login?" -> co_useonelogin
    - "What is the commercial approach?" -> co_commercialapproach
    - "Is HMT approval needed?" -> co_hmt_yesno
    - "What's the contract duration?" -> co_dt_ri_contractduration
    - "Is it emerging technology?" -> co_dt_ri_emergetech
    - "Transactions per year?" -> co_dt_ri_transactionsperyear
    - "Is it CNI?" -> co_criticalnationalinfra_yesno
    - "Service assessment required?" -> co_dt_reqserviceassessment
    - "Who is the SRO?" -> co_sroname
    - "Current/proposed supplier?" -> co_currentsupplier / co_proposedsupplier
    - "What's the spend category?" -> co_spendcategory or co_dt_spendcategory
    - "Submitting organisation?" -> co_organisationsubmitter
    """,
)


GATS_COMMON_QUERY_PATTERNS = block(
    "gats_common_query_patterns",
    """
    GATS — COMMON QUERY PATTERNS

    1. Count cases with a condition:
       SELECT COUNT(*) FROM assurance_contracts.spend_controls_data_export
       WHERE co_aiquantum_yesno = 'Yes'

    2. Filter by spend amount (e.g. < £10m) — use TRY_CAST + REPLACE for formatted strings:
       SELECT *
       FROM assurance_contracts.spend_controls_data_export
       WHERE TRY_CAST(REPLACE(REPLACE(co_spendamount, ',', ''), '"', '') AS BIGINT) < 10000000

    3. Group by organisation:
       SELECT co_organisationsubmitter, COUNT(*) AS case_count
       FROM assurance_contracts.spend_controls_data_export
       GROUP BY co_organisationsubmitter
       ORDER BY case_count DESC

    4. Combined filters (AI cases under £10m):
       SELECT co_spendid, co_casename, co_organisationsubmitter, co_spendamount
       FROM assurance_contracts.spend_controls_data_export
       WHERE co_aiquantum_yesno = 'Yes'
         AND TRY_CAST(REPLACE(REPLACE(co_spendamount, ',', ''), '"', '') AS BIGINT) < 10000000

    5. Aggregate spend by category:
       SELECT digital_spend_category, COUNT(*) AS contracts,
              SUM(TRY_CAST(REPLACE(REPLACE(value, ',', ''), '£', '') AS BIGINT)) AS total_value
       FROM assurance_contracts.extracted_contracts
       GROUP BY digital_spend_category
       ORDER BY total_value DESC

    6. Top suppliers by total contract value:
       SELECT seller_name, COUNT(*) AS contracts,
              SUM(TRY_CAST(REPLACE(REPLACE(value, ',', ''), '£', '') AS BIGINT)) AS total_value
       FROM assurance_contracts.extracted_contracts
       WHERE LOWER(buyer_name) LIKE '%home office%'
       GROUP BY seller_name
       ORDER BY total_value DESC
       LIMIT 50

    7. Service Standard outcomes by stage:
       SELECT stage, outcome, COUNT(*) AS assessments
       FROM "gats-assurance".service_assessments_snapshot20251217
       WHERE LOWER(department) LIKE '%home office%'
       GROUP BY stage, outcome
       ORDER BY stage, outcome

    8. Digital workforce FTE and contractor mix by department:
       SELECT department,
              SUM(TRY_CAST(REPLACE(fte_person, ',', '') AS DOUBLE)) AS total_fte,
              SUM(CASE WHEN LOWER(resource_type) LIKE '%contractor%' THEN 1 ELSE 0 END) AS contractor_rows
       FROM assurance_contracts.workforce_commision_26
       WHERE LOWER(department) LIKE '%home office%'
       GROUP BY department

    9. Average contractor day rate by profession:
       SELECT profession,
              AVG(TRY_CAST(REPLACE(REPLACE(contractor_day_rate_excluding_vat_agency_fees, ',', ''), '£', '') AS DOUBLE)) AS avg_day_rate
       FROM assurance_contracts.workforce_commision_26
       WHERE LOWER(resource_type) LIKE '%contractor%'
       GROUP BY profession
       ORDER BY avg_day_rate DESC
    """,
)


SQL_HARD_RULES = block(
    "sql_hard_rules",
    """
    SQL HARD RULES:
    - SELECT only. Never INSERT, UPDATE, DELETE, DROP, MERGE, or ALTER.
    - Always call `get_table_schema` before writing SQL.
    - Always show the SQL query you executed.
    - LIMIT 50 unless aggregating.
    - Use LOWER() + LIKE with wildcards for all text/department matching.
    - Use TRY_CAST(REPLACE(REPLACE(<col>, ',', ''), '"', '') AS BIGINT) for formatted spend amounts.
    - Use double quotes around hyphenated database/table/column names
      (e.g. "gats-assurance".service_assessments_snapshot20251217, "Project Name").
    - Format final spend in output as £X,XXX,XXX for readability.
    - If a query returns 0 rows, explain the filters used and suggest broader alternatives.
    - Never fabricate data — only report what the query returns.
    """,
)
