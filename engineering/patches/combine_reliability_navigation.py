"""Consolidate report links without replacing customized Workspace content."""
import frappe


TARGETS = {'machine-reliability', 'reliability-engineering'}


def update_links(workspace):
    changed, found, links = False, False, []
    for row in workspace.links:
        if row.link_type == 'Page' and row.link_to in TARGETS:
            if found:
                changed = True
                continue
            found = True
            if row.link_to != 'reliability-engineering' or row.label != 'Reliability Engineering':
                row.link_to, row.label = 'reliability-engineering', 'Reliability Engineering'
                changed = True
        links.append(row)
    if not found:
        card = next((i for i, x in enumerate(links) if x.type == 'Card Break' and x.label == 'Machine Information Report'), None)
        if card is None:
            card = next((i for i, x in enumerate(links) if x.type == 'Card Break'), None)
        if card is None:
            card = len(links)
            links.append(workspace.append('links', dict(type='Card Break', label='Reliability reports')))
            content = frappe.parse_json(workspace.content or '[]')
            content.append(dict(id='combinedReliabilityReports', type='card',
                data=dict(card_name='Reliability reports', col=12)))
            workspace.content = frappe.as_json(content)
        end = next((i for i in range(card + 1, len(links)) if links[i].type == 'Card Break'), len(links))
        row = workspace.append('links', dict(type='Link', label='Reliability Engineering', link_type='Page', link_to='reliability-engineering'))
        links.insert(end, row)
        changed = True
    if changed:
        workspace.set('links', links)
        card = None
        for row in workspace.links:
            if row.type == 'Card Break':
                card = row
                card.link_count = 0
            elif card:
                card.link_count += 1
    return changed


def execute():
    if not frappe.db.exists('Workspace', 'Engineering'):
        return
    workspace = frappe.get_doc('Workspace', 'Engineering')
    if update_links(workspace):
        # Preserve unrelated legacy links, even where another app renamed a target.
        workspace.flags.ignore_links = True
        workspace.save(ignore_permissions=True)
