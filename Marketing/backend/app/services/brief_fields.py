"""The extractable brief fields per type — (column key, human label).

Single source of truth for the ADK Brief Creator Agent's output schema. Mirrors
the frontend brief spec.
"""

# The two dates are deliberately absent: they're derived by the system on save
# (brief_date = today, expected_date = +3 days), never extracted from the notes.
_SHARED = [
    ("project_name", "Project Name"),
    ("product_name", "Product Name"),
    ("owner_name", "Owner / Product Owner"),
]

_SMALL_MED = _SHARED + [
    ("sm_go_live_timeline", "Go-live Timeline"),
    ("sm_one_line_summary", "One-line summary: what we are building/launching and why"),
    ("sm_primary_goal", "Primary goal / objective"),
    ("sm_business_kpi", "Business KPI impacted"),
    ("sm_strategic_context", "Strategic context"),
    ("sm_audience_who", "Who is this for? (Internal / Public CUG / Existing / New)"),
    ("sm_audience_segment", "Segment / Cohort specifics"),
    ("sm_audience_exclusions", "Any exclusions"),
    ("sm_mandatories_tnc", "Mandatories and T&C to be used"),
    ("sm_platforms", "Platforms"),
    ("sm_dimensions_specs", "Dimensions & Specifications"),
    ("sm_final_ui_screen", "Final UI screen (link / note)"),
    ("sm_samples_references", "Samples / Examples / References"),
]

_LARGE = _SHARED + [
    ("lg_project_purpose", "Project Purpose"),
    ("lg_business_objective", "Overall Business Objective"),
    ("lg_marketing_objective", "Marketing Objective"),
    ("lg_communication_objective", "Communication Objective"),
    ("lg_effectiveness_metric", "Effectiveness metric"),
    ("lg_ideal_customer", "Ideal customer / persona: behavior, habits, interests"),
    ("lg_demo_age", "Demographics: Age"),
    ("lg_demo_gender", "Demographics: Gender"),
    ("lg_demo_top_cities", "Demographics: Top cities"),
    ("lg_goals_motivations", "Goals & Motivations"),
    ("lg_category_insight", "Category insight"),
    ("lg_conservative_target", "Conservative target"),
    ("lg_aspirational_target", "Aspirational target"),
    ("lg_product_insight", "Product Insight"),
    ("lg_key_markets", "Key markets / locations"),
    ("lg_competition", "Competition"),
    ("lg_product_features", "Products / service features on offer"),
    ("lg_key_features_deliverables", "Key features / deliverables of each"),
    ("lg_unique_offerings", "Unique offerings vs competition"),
    ("lg_think_before", "Think — before communication"),
    ("lg_think_after", "Think — after communication"),
    ("lg_feel_before", "Feel — before communication"),
    ("lg_feel_after", "Feel — after communication"),
    ("lg_do_before", "Do — before communication"),
    ("lg_do_after", "Do — after communication"),
    ("lg_cultural_sensitivity", "Cultural Sensitivity"),
    ("lg_languages", "Languages"),
    ("lg_other_considerations", "Other considerations"),
    ("lg_deliverables", "Deliverables: sizes, format, placements, deadlines"),
]


def fields_for(brief_type: str) -> list[tuple[str, str]]:
    return _LARGE if brief_type == "large" else _SMALL_MED
