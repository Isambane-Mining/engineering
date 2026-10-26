import unittest
import frappe
from engineering.patches.combine_reliability_navigation import update_links


class TestCombinedReliabilityNavigation(unittest.TestCase):
    def test_consolidates_links_and_preserves_unrelated_entries(self):
        workspace = frappe.get_doc(dict(doctype='Workspace', links=[
            dict(type='Card Break', label='Reports', link_count=3),
            dict(type='Link', label='Before', link_type='DocType', link_to='Asset'),
            dict(type='Link', label='Machine Reliability', link_type='Page', link_to='machine-reliability'),
            dict(type='Link', label='Reliability Engineering', link_type='Page', link_to='reliability-engineering'),
            dict(type='Card Break', label='Other', link_count=1),
            dict(type='Link', label='After', link_type='DocType', link_to='Engineering Legals')]))
        self.assertTrue(update_links(workspace))
        self.assertEqual([x.label for x in workspace.links], ['Reports', 'Before', 'Reliability Engineering', 'Other', 'After'])
        self.assertEqual(workspace.links[0].link_count, 2)
        self.assertEqual(workspace.links[3].link_count, 1)
        self.assertFalse(update_links(workspace))

    def test_adds_entry_when_neither_old_link_exists(self):
        workspace = frappe.get_doc(dict(doctype='Workspace', links=[
            dict(type='Card Break', label='Machine Information Report', link_count=1),
            dict(type='Link', label='Machine File', link_type='DocType', link_to='Machine File')]))
        self.assertTrue(update_links(workspace))
        self.assertEqual(workspace.links[-1].link_to, 'reliability-engineering')
        self.assertEqual(workspace.links[0].link_count, 2)

    def test_custom_workspace_without_standard_cards_gets_visible_entry(self):
        workspace = frappe.get_doc(dict(doctype='Workspace', links=[], content='[{"id":"intro","type":"header","data":{"text":"Custom"}}]'))
        self.assertTrue(update_links(workspace))
        self.assertEqual(workspace.links[-1].link_to, 'reliability-engineering')
        content = frappe.parse_json(workspace.content)
        self.assertEqual(content[0]['id'], 'intro')
        self.assertEqual(content[-1]['data']['card_name'], workspace.links[0].label)
        self.assertFalse(update_links(workspace))
