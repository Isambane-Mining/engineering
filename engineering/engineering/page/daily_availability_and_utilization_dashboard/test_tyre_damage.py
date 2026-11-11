
from engineering.patches.failure_classification_seed import INITIAL_CLASSIFICATIONS as TEST_CLASSIFICATIONS, seed_configuration
TEST_CONFIGURATION = seed_configuration()
import unittest
from unittest.mock import patch
import frappe
from copy import deepcopy
from types import SimpleNamespace
from engineering.engineering.page.daily_availability_and_utilization_dashboard import tyre_damage as tyre


from unittest.mock import patch as patch_classification_configuration

@patch_classification_configuration('engineering.controllers.failure_classification.get_configuration', new=lambda: TEST_CONFIGURATION)
class TestTyreDamageMatching(unittest.TestCase):
    def test_only_explicit_classification_counts(self):
        self.assertTrue(tyre.is_classified_tyre_damage(dict(failure_classification='Tyres / Wheels'), classifications=TEST_CONFIGURATION['tyre_classifications']))
        for values in [{}, {'failure_classification': 'Mechanical'},
                       {'breakdown_reason': 'flat tyre', 'resolution_summary': 'tyre burst repaired'}]:
            with self.subTest(values=values):
                self.assertFalse(tyre.is_classified_tyre_damage(values, classifications=TEST_CONFIGURATION['tyre_classifications']))

    def test_more_than_one_damage_term_is_one_record(self):
        rows = [dict(name='A', category='ADT', machine='IS1'), dict(name='A', category='ADT', machine='IS1'),
                dict(name='B', category='Dozer', machine='DZ1')]
        self.assertEqual(tyre.damage_counts(rows), {'ADT': 1, 'Dozer': 1})
        self.assertEqual(tyre.damage_counts(rows, machine='IS1'), {'ADT': 1, 'Dozer': 0})



@patch_classification_configuration('engineering.controllers.failure_classification.get_configuration', new=lambda: TEST_CONFIGURATION)
class TestTyreDamageSources(unittest.TestCase):
    def test_query_and_count_follow_permitted_engine_scope_and_record_site_category(self):
        source = [dict(indent=3, asset_name='IS1', shift_date='2026-07-01', asset_category='ADT'),
                  dict(indent=3, asset_name='IS1', shift_date='2026-07-02', asset_category='ADT'),
                  dict(indent=3, asset_name='DZ1', shift_date='2026-07-01', asset_category='Dozer')]
        rows = [frappe._dict(name='yes',asset_name='ASSET1',location='Old Site',asset_category='ADT',downtime_type='Breakdown',breakdown_start_datetime='2026-07-01 12:00:00',breakdown_reason='flat tyre',resolution_summary=''),
                frappe._dict(name='repair',asset_name='ASSET1',location='Old Site',asset_category='ADT',downtime_type='Breakdown',breakdown_start_datetime='2026-07-01 12:00:00',breakdown_reason='engine stopped',resolution_summary='tyre cut repaired'),
                frappe._dict(name='routine',asset_name='ASSET1',location='Old Site',asset_category='ADT',downtime_type='Breakdown',breakdown_start_datetime='2026-07-01 12:00:00',breakdown_reason='Tyre inflation'),
                frappe._dict(name='out',asset_name='ASSET1',location='Old Site',asset_category='ADT',downtime_type='Breakdown',breakdown_start_datetime='2026-07-03 12:00:00',breakdown_reason='flat tyre'),
                frappe._dict(name='dozer',asset_name='DOZER1',location='Old Site',asset_category='Dozer',downtime_type='Breakdown',breakdown_start_datetime='2026-07-01 12:00:00',breakdown_reason='tire burst')]
        for row in rows:
            row.failure_classification = 'Tyres / Wheels' if row.name in ('yes', 'out', 'dozer') else ''
        identities=[frappe._dict(name='ASSET1',asset_name='IS1'),frappe._dict(name='DOZER1',asset_name='DZ1')]
        with patch.object(frappe,'has_permission',return_value=True),patch.object(frappe,'get_all',return_value=identities),patch.object(frappe,'get_list',return_value=rows) as read:
            result=tyre.fetch_tyre_damage_records(source,'Old Site','2026-07-01','2026-07-02', tyre_classifications=TEST_CONFIGURATION['tyre_classifications'])
            for selected in ['ASSET1', 'IS1']:
                restricted=tyre.fetch_tyre_damage_records(source,'Old Site','2026-07-01','2026-07-02',selected, tyre_classifications=TEST_CONFIGURATION['tyre_classifications'])
                self.assertEqual([x['name'] for x in restricted],['yes'])
        self.assertEqual([x['name'] for x in result],['yes','dozer'])
        self.assertEqual(tyre.damage_counts(result),{'ADT':1,'Dozer':1})
        args=read.call_args.kwargs
        self.assertIn(['location','=','Old Site'],args['filters'])
        self.assertIn(['downtime_type','=','Breakdown'],args['filters'])
        self.assertNotIn('resolution_summary',args['fields'])
        self.assertNotIn('breakdown_reason',args['fields'])
        self.assertIn(['failure_classification', 'in', list(TEST_CONFIGURATION['tyre_classifications'])], args['filters'])
        self.assertIn(['docstatus', '<', 2], args['filters'])
        self.assertLessEqual(args['limit_page_length'],20001)

    def test_empty_roster_and_missing_permission_do_not_query_records(self):
        with patch.object(frappe,'get_list') as read:
            self.assertEqual(tyre.fetch_tyre_damage_records([],'Site','2026-07-01','2026-07-02', tyre_classifications=TEST_CONFIGURATION['tyre_classifications']),[])
            read.assert_not_called()
        with patch.object(frappe,'has_permission',return_value=False):
            self.assertIsNone(tyre.fetch_tyre_damage_records([dict(indent=3,asset_name='A',shift_date='2026-07-01')],'Site','2026-07-01','2026-07-02', tyre_classifications=TEST_CONFIGURATION['tyre_classifications']))


@patch_classification_configuration('engineering.controllers.failure_classification.get_configuration', new=lambda: TEST_CONFIGURATION)
class DashboardFixtures(unittest.TestCase):
    """Real Engine aggregation/rendering with only external reads replaced."""
    def setUp(self):
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        self.source = [dict(indent=3, asset_category=category, asset_name=machine,
                            shift_date='2026-07-01', shift='Day', work_hours=6,
                            pbm_total_downtime=4, planned_maintenance_hours=1,
                            required_hours=12, is_spare_swing_unit=spare)
                       for category, machine, spare in [('ADT', 'IS587', 0), ('Dozer', 'DZ1', 1)]]
        def breakdowns(*args, **kwargs):
            location = next(f[2] for f in kwargs['filters'] if f[0] == 'location')
            return [frappe._dict(name=name, asset_name=asset, asset_category=category,
                                 breakdown_start_datetime='2026-07-01 12:00:00',
                                 location=location, downtime_type='Breakdown',
                                 failure_classification='Tyres / Wheels')
                    for name, asset, category in [('damage-1', 'A1', 'ADT'), ('damage-2', 'A2', 'Dozer')]]
        patches = [
            patch.object(dashboard.au_engine, 'get_data', side_effect=lambda filters: deepcopy(self.source)),
            patch.object(dashboard, 'nowdate', return_value='2026-08-01'),
            patch.object(dashboard, 'get_monthly_production_shift_hours', return_value={'2026-07-01': {'day': 12, 'night': 12}}),
            patch.object(dashboard, 'fetch_short_haul_hours', return_value={}),
            patch.object(dashboard, 'get_site_colour_map', return_value={}),
            patch.object(frappe, 'has_permission', return_value=True),
            patch.object(frappe, 'get_list', side_effect=breakdowns),
            patch.object(frappe, 'get_all', return_value=[frappe._dict(name='A1', asset_name='IS587'), frappe._dict(name='A2', asset_name='DZ1')]),
            patch.object(frappe, 'db', SimpleNamespace(sql=lambda *args, **kwargs: self.fail('Unexpected database access'))),
        ]
        for context in patches:
            context.start()
            self.addCleanup(context.stop)


@patch_classification_configuration('engineering.controllers.failure_classification.get_configuration', new=lambda: TEST_CONFIGURATION)
class TestTyreDamageLiveDashboard(DashboardFixtures):
    def test_live_filters_and_scope_partition(self):
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        results = {}
        for scope in ['Production + Swing/Spare Machines', 'Production Machines', 'Swing/Spare Machines']:
            source=dashboard.fetch_grouped_data('Klipfontein','2026-07-01','2026-07-31',scope,'85% A & U','Isambane & Excavo Assets')
            records=tyre.fetch_tyre_damage_records(source,'Klipfontein','2026-07-01','2026-07-31', tyre_classifications=TEST_CONFIGURATION['tyre_classifications'])
            results[scope]={x['name'] for x in records}
            self.assertEqual(len(records),len(results[scope]))
            selected=tyre.fetch_tyre_damage_records(source,'Klipfontein','2026-07-01','2026-07-31','IS587', tyre_classifications=TEST_CONFIGURATION['tyre_classifications'])
            self.assertTrue(all(x['machine']=='IS587' for x in selected))
            self.assertTrue({x['name'] for x in selected}.issubset(results[scope]))
        self.assertEqual(results['Production + Swing/Spare Machines'],results['Production Machines']|results['Swing/Spare Machines'])
        self.assertFalse(results['Production Machines']&results['Swing/Spare Machines'])
        self.assertEqual(len(results['Production + Swing/Spare Machines']),2)

    def test_per_asset_display_retains_one_category_total_on_each_tab(self):
        from bs4 import BeautifulSoup
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        html=dashboard.execute(frappe._dict(location='Koppie',start_date='2026-07-01',end_date='2026-07-31',hours_display='Hours per Asset'))[2]
        soup=BeautifulSoup(html,'html.parser')
        for panel in soup.select('.daily-dashboard-tab-panel'):
            cards=panel.select('.daily-tyre-kpi')
            self.assertEqual(len(cards),1)
            self.assertEqual({c['data-category']:c['data-count'] for c in cards},{'ADT':'1'})

    def test_live_counts_match_both_tabs(self):
        from bs4 import BeautifulSoup
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        filters=frappe._dict(location='Klipfontein',start_date='2026-07-01',end_date='2026-07-31',asset_ownership='Isambane & Excavo Assets',machine_scope='Production + Swing/Spare Machines')
        after=dashboard.execute(filters)[2]
        after_soup=BeautifulSoup(after,'html.parser')
        counts={panel['data-panel']:{x['data-category']:x['data-count'] for x in panel.select('.daily-tyre-kpi')} for panel in after_soup.select('.daily-dashboard-tab-panel')}
        self.assertEqual(counts,{'hours':{'ADT':'1'},'au':{'ADT':'1'}})
        for panel in after_soup.select('.daily-dashboard-tab-panel'):
            for card in panel.select('.daily-tyre-kpi'):
                self.assertEqual(len(card.parent.select(':scope > .frappe-card')),3)


@patch_classification_configuration('engineering.controllers.failure_classification.get_configuration', new=lambda: TEST_CONFIGURATION)
class TestTyreDamageRendering(DashboardFixtures):
    def test_shared_hours_graph_and_original_cards_do_not_change(self):
        import re
        from bs4 import BeautifulSoup
        from engineering.engineering.page.daily_availability_dashboard.daily_availability_dashboard import build_hours_based_performance_html
        source=[dict(asset_category='ADT',asset_name='IS1',_au_source_rows=[dict(shift_date='2026-07-01',shift='Day',work_hours=6,pbm_total_downtime=4,planned_maintenance_hours=1,required_hours=12)])]
        original=build_hours_based_performance_html(source,'2026-07-01','2026-07-01')
        updated=build_hours_based_performance_html(source,'2026-07-01','2026-07-01',tyre_damage_counts={'ADT':2,'Dozer':0})
        chart=lambda text:[x for x in re.findall(r'<svg\b.*?</svg>',text,re.S) if 'daily-tyre-icon' not in x]
        self.assertEqual(chart(original),chart(updated))
        before,after=BeautifulSoup(original,'html.parser'),BeautifulSoup(updated,'html.parser')
        self.assertEqual([str(x) for x in before.select('.frappe-card')[:2]],[str(x) for x in after.select('.frappe-card')[:2]])
        self.assertNotIn('daily-tyre-kpi',original)
        self.assertEqual(after.select_one('.daily-tyre-kpi')['data-count'],'2')

    def test_positive_counts_render_identically_in_both_tabs(self):
        from bs4 import BeautifulSoup
        from engineering.engineering.page.daily_availability_and_utilization_dashboard.daily_availability_and_utilization_dashboard import build_dashboard_html
        source=[dict(indent=3,asset_category=category,asset_name=machine,shift_date='2026-07-01',shift='Day',work_hours=6,pbm_total_downtime=4,planned_maintenance_hours=1,required_hours=12)
                for category,machine in [('ADT','IS1'),('Dozer','DZ1')]]
        records=[dict(name='damage-1', category='ADT', machine='IS1'),
                 dict(name='damage-1', category='ADT', machine='IS1'),
                 dict(name='damage-2', category='Dozer', machine='DZ1')]
        html=build_dashboard_html('Koppie','2026-07-01','2026-07-01',{}, {},source_rows=source,tyre_damage_records=records)
        panels=BeautifulSoup(html,'html.parser').select('.daily-dashboard-tab-panel')
        self.assertEqual(len(panels), 2)
        for panel in panels:
            self.assertEqual({c['data-category']:c['data-count'] for c in panel.select('.daily-tyre-kpi')}, {'ADT':'1'})


@patch_classification_configuration('engineering.controllers.failure_classification.get_configuration', new=lambda: TEST_CONFIGURATION)
class TestTyreDrilldown(DashboardFixtures):
    def test_card_and_drilldown_use_the_same_unique_adt_records(self):
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        from engineering.controllers import tyre_damage as controller
        source=dashboard.fetch_grouped_data('Old Site','2026-07-01','2026-07-01')
        counted=controller.damage_counts(controller.fetch_tyre_damage_records(source,'Old Site','2026-07-01','2026-07-01', tyre_classifications=TEST_CONFIGURATION['tyre_classifications']))
        original_read=frappe.get_list
        def read(doctype,**kwargs):
            if isinstance(kwargs.get('filters'),dict):
                return [frappe._dict(name='damage-1',asset_name='A1',breakdown_reason='wheel studs broken',
                    breakdown_start_datetime='2026-07-01 12:00:00',resolved_datetime='2026-07-01 14:00:00')]
            rows=original_read(doctype,**kwargs)
            return rows+rows  # Both KPI and drill-down must deduplicate identities.
        with patch.object(frappe,'get_list',side_effect=read):
            details=dashboard.get_tyre_breakdown_details(category='ADT',location='Old Site',start_date='2026-07-01',end_date='2026-07-01')
        self.assertEqual(details['total_records'],counted['ADT'])
        self.assertEqual([x['name'] for x in details['rows']],['damage-1'])
        self.assertEqual(details['total_standing_hours'],2)

    def test_planned_cancelled_wrong_class_and_wrong_roster_are_excluded(self):
        from engineering.controllers import tyre_damage as controller
        source=self.source
        common=dict(asset_name='A1',asset_category='ADT',location='Old Site',downtime_type='Breakdown',
                    breakdown_start_datetime='2026-07-01 12:00:00',failure_classification='Tyres / Wheels')
        rows=[frappe._dict(common,name='valid')]
        for name,values in [('planned',dict(downtime_type='Planned Maintenance')),
                            ('cancelled',dict(docstatus=2)),('wrong-class',dict(failure_classification='Engine')),
                            ('wrong-site',dict(location='Other Site')),('wrong-machine',dict(asset_name='not-in-roster'))]:
            rows.append(frappe._dict(dict(common,**values),name=name))
        with patch.object(frappe,'get_list',return_value=rows):
            result=controller.fetch_tyre_damage_records(source,'Old Site','2026-07-01','2026-07-01', tyre_classifications=TEST_CONFIGURATION['tyre_classifications'])
        self.assertEqual([x['name'] for x in result],['valid'])

    def test_drilldown_permission_and_dozer_category_are_rejected(self):
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        def throw(message,exc=frappe.ValidationError):raise exc(message)
        with patch.object(frappe,'throw',side_effect=throw):
            with self.assertRaises(frappe.ValidationError):
                dashboard.get_tyre_breakdown_details(category='Dozer',location='Old Site',start_date='2026-07-01',end_date='2026-07-01')
            with patch.object(frappe,'has_permission',return_value=False):
                with self.assertRaises(frappe.PermissionError):
                    dashboard.get_tyre_breakdown_details(category='ADT',location='Old Site',start_date='2026-07-01',end_date='2026-07-01')

    def test_dozer_graphs_rows_and_two_average_cards_survive_in_all_display_modes(self):
        from bs4 import BeautifulSoup
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        for display in ['Hours Average per Category','Hours per Asset']:
            html=dashboard.execute(frappe._dict(location='Koppie',start_date='2026-07-01',end_date='2026-07-01',hours_display=display))[2]
            soup=BeautifulSoup(html,'html.parser')
            self.assertFalse(soup.select('.daily-tyre-kpi[data-category="Dozer"]'))
            self.assertIn('DOZER',html)
            self.assertIn('Average Working Hours',html)
            row=soup.select_one('[data-kpi-category="Dozer"]')
            self.assertIsNotNone(row)
            self.assertEqual(len(row.select('.frappe-card')),2)
            self.assertIn('Dozer Average Availability',row.get_text())
            self.assertIn('Dozer Average Utilisation',row.get_text())
