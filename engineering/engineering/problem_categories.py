"""Canonical captured categories. Do not infer these labels from descriptions.

The DocType's static Select metadata mirrors this tuple; a regression test keeps
that required schema representation in sync. UI clients read the server metadata.
"""
BASE_PROBLEM_CATEGORIES = (
    'Brakes', 'Steering', 'Engine / Starting', 'Hydraulics', 'Electrical', 'Cooling',
    'Transmission / Drivetrain', 'Tyres / Wheels', 'Air Conditioning', 'Other',
)
SAFETY_PROBLEM_CATEGORIES = ('FRCS', 'Stop Blocks', 'Machine Locks', 'Bowl Lock Pins', 'Brake Test', 'Steps / Handrail')
PROBLEM_CATEGORIES = BASE_PROBLEM_CATEGORIES + SAFETY_PROBLEM_CATEGORIES


def validate_problem_category(value, *, is_new, previous=None):
    """Allow an unchanged legacy value, require a canonical new/corrected value."""
    if not is_new and value == previous:
        return
    if value not in PROBLEM_CATEGORIES:
        raise ValueError('Choose a valid Problem Category for this breakdown. Historical values must be reviewed, not inferred.')
