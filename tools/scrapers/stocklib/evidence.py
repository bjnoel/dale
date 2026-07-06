"""
Shared evidence-grading vocabulary and badge rendering for the curated guides.

Companion-planting and pollination guides make claims of varying certainty, from
peer-reviewed to folklore. Each claim carries an evidence grade so the page is
honest about what is proven versus traditional. One definition lives here so the
guides cannot drift on the grade set or the badge styling.
"""

# Closed vocabulary. A test asserts every claim uses one of these.
EVIDENCE_GRADES = {
    "research-backed",       # peer-reviewed or university-extension support
    "established-practice",  # broad horticultural consensus, low controversy
    "traditional",           # folklore / anecdotal, plausible but little hard evidence
    "context-dependent",     # true only for certain varieties, climates or conditions
}

# label + Tailwind classes per grade (single styling source of truth).
GRADE_BADGE = {
    "research-backed": ("Research-backed", "bg-green-100 text-green-800 border-green-300"),
    "established-practice": ("Established practice", "bg-emerald-50 text-emerald-700 border-emerald-200"),
    "traditional": ("Traditional, limited evidence", "bg-amber-50 text-amber-800 border-amber-200"),
    "context-dependent": ("Depends on conditions", "bg-sky-50 text-sky-700 border-sky-200"),
}


def grade_badge(grade: str, block: bool = False) -> str:
    """Render the evidence badge for a grade.

    Default (inline): sits at the end of a run of text with a small left margin,
    baseline-aligned. Pass block=True to place the badge on its own line inside a
    wrapper (no left margin), which reads cleanly in table cells where the note
    can wrap to several lines and a trailing inline badge would strand itself.
    """
    label, cls = GRADE_BADGE[grade]
    spacing = "mt-1.5" if block else "ml-1 align-middle"
    return (
        f'<span class="inline-block text-xs px-1.5 py-0.5 rounded border {cls} '
        f'{spacing} whitespace-nowrap">{label}</span>'
    )
