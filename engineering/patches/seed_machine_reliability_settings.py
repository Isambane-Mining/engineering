import frappe
from engineering.engineering.doctype.machine_reliability_settings.machine_reliability_settings import DEFAULT_CATEGORIES


def execute():
    settings = frappe.get_doc('Machine Reliability Settings')
    if not settings.categories:
        _seed_missing_engineering_legals_sections()
        for category, keywords, test_sections in DEFAULT_CATEGORIES:
            settings.append('categories', dict(category=category, keywords=keywords, test_sections=test_sections))
        settings.save(ignore_permissions=True)
    ensure_navigation()
    # Bound historical-source queries efficiently without altering ERP records.
    frappe.db.add_index('Plant Breakdown or Maintenance', ['breakdown_start_datetime', 'location'], 'machine_reliability_date_site')
    frappe.db.add_index('Engineering Legals', ['start_date', 'site'], 'machine_reliability_date_site')


def _seed_missing_engineering_legals_sections():
    """Ensure every Engineering Legals Sections name DEFAULT_CATEGORIES's
    test_sections depend on actually exists, creating only the ones missing.

    MachineReliabilitySettings.validate() rejects any test_sections entry
    that isn't an existing Engineering Legals Sections record. On a site
    with no prior Engineering Legals history (no earlier Desk entry or
    import ever created these names), this patch's own settings.save()
    below would otherwise fail validation before it even runs once.
    """
    required_sections = {
        section.strip()
        for _category, _keywords, test_sections in DEFAULT_CATEGORIES
        for section in (test_sections or '').splitlines()
        if section.strip()
    }
    for section in sorted(required_sections):
        if not frappe.db.exists('Engineering Legals Sections', section):
            frappe.get_doc({'doctype': 'Engineering Legals Sections', 'section': section}).insert(
                ignore_permissions=True
            )


def ensure_navigation():
    """Add one link without replacing a locally customized Workspace."""
    if not frappe.db.exists('Workspace', 'Engineering'):
        return
    workspace = frappe.get_doc('Workspace', 'Engineering')
    if any(x.link_to == 'machine-reliability' for x in workspace.links):
        return
    card_index = next((i for i, x in enumerate(workspace.links)
                       if x.type == 'Card Break' and x.label == 'Machine Information Report'), None)
    if card_index is None:
        return
    end = next((i for i in range(card_index + 1, len(workspace.links))
                if workspace.links[i].type == 'Card Break'), len(workspace.links))
    new_link = workspace.append('links', dict(type='Link', label='Machine Reliability',
                                             link_type='Page', link_to='machine-reliability'))
    workspace.links.remove(new_link)
    workspace.links.insert(end, new_link)
    workspace.links[card_index].link_count = end - card_index
    # Preserve existing legacy links even if another app has renamed a target.
    workspace.flags.ignore_links = True
    workspace.save(ignore_permissions=True)
