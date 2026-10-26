import unittest
from unittest.mock import patch
import frappe
from engineering.engineering.page.daily_availability_and_utilization_dashboard import tyre_damage as tyre


class TestTyreDamageMatching(unittest.TestCase):
    def test_only_explicit_category_and_subcategory_count(self):
        self.assertTrue(tyre.is_classified_tyre_damage(dict(problem_category='Tyres / Wheels', problem_subcategory='Tyre Damage')))
        for values in [{}, {'problem_category': 'Tyres / Wheels'},
                       {'problem_subcategory': 'Tyre Damage'},
                       {'problem_category': 'Other', 'problem_subcategory': 'Tyre Damage'},
                       {'breakdown_reason': 'flat tyre', 'resolution_summary': 'tyre burst repaired'}]:
            with self.subTest(values=values):
                self.assertFalse(tyre.is_classified_tyre_damage(values))

    def test_more_than_one_damage_term_is_one_record(self):
        rows = [dict(name='A', category='ADT', machine='IS1'), dict(name='A', category='ADT', machine='IS1'),
                dict(name='B', category='Dozer', machine='DZ1')]
        self.assertEqual(tyre.damage_counts(rows), {'ADT': 1, 'Dozer': 1})
        self.assertEqual(tyre.damage_counts(rows, machine='IS1'), {'ADT': 1, 'Dozer': 0})



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
            row.problem_category = 'Tyres / Wheels'
            row.problem_subcategory = 'Tyre Damage' if row.name in ('yes', 'out', 'dozer') else ''
        identities=[frappe._dict(name='ASSET1',asset_name='IS1'),frappe._dict(name='DOZER1',asset_name='DZ1')]
        with patch.object(frappe,'has_permission',return_value=True),patch.object(frappe,'get_all',return_value=identities),patch.object(frappe,'get_list',return_value=rows) as read:
            result=tyre.fetch_tyre_damage_records(source,'Old Site','2026-07-01','2026-07-02')
            for selected in ['ASSET1', 'IS1']:
                restricted=tyre.fetch_tyre_damage_records(source,'Old Site','2026-07-01','2026-07-02',selected)
                self.assertEqual([x['name'] for x in restricted],['yes'])
        self.assertEqual([x['name'] for x in result],['yes','dozer'])
        self.assertEqual(tyre.damage_counts(result),{'ADT':1,'Dozer':1})
        args=read.call_args.kwargs
        self.assertIn(['location','=','Old Site'],args['filters'])
        self.assertIn(['downtime_type','=','Breakdown'],args['filters'])
        self.assertNotIn('resolution_summary',args['fields'])
        self.assertNotIn('breakdown_reason',args['fields'])
        self.assertIn(['problem_category', '=', 'Tyres / Wheels'], args['filters'])
        self.assertIn(['problem_subcategory', '=', 'Tyre Damage'], args['filters'])
        self.assertLessEqual(args['limit_page_length'],20001)

    def test_empty_roster_and_missing_permission_do_not_query_records(self):
        with patch.object(frappe,'get_list') as read:
            self.assertEqual(tyre.fetch_tyre_damage_records([],'Site','2026-07-01','2026-07-02'),[])
            read.assert_not_called()
        with patch.object(frappe,'has_permission',return_value=False):
            self.assertIsNone(tyre.fetch_tyre_damage_records([dict(indent=3,asset_name='A',shift_date='2026-07-01')],'Site','2026-07-01','2026-07-02'))


class TestTyreDamageLiveDashboard(unittest.TestCase):
    def test_live_filters_and_scope_partition(self):
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        results = {}
        for scope in ['Production + Swing/Spare Machines', 'Production Machines', 'Swing/Spare Machines']:
            source=dashboard.fetch_grouped_data('Klipfontein','2026-07-01','2026-07-31',scope,'85% A & U','Isambane & Excavo Assets')
            records=tyre.fetch_tyre_damage_records(source,'Klipfontein','2026-07-01','2026-07-31')
            results[scope]={x['name'] for x in records}
            self.assertEqual(len(records),len(results[scope]))
            selected=tyre.fetch_tyre_damage_records(source,'Klipfontein','2026-07-01','2026-07-31','IS587')
            self.assertTrue(all(x['machine']=='IS587' for x in selected))
            self.assertTrue({x['name'] for x in selected}.issubset(results[scope]))
        self.assertEqual(results['Production + Swing/Spare Machines'],results['Production Machines']|results['Swing/Spare Machines'])
        self.assertFalse(results['Production Machines']&results['Swing/Spare Machines'])
        self.assertEqual(len(results['Production + Swing/Spare Machines']),0)

    def test_per_asset_display_retains_one_category_total_on_each_tab(self):
        from bs4 import BeautifulSoup
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        html=dashboard.execute(frappe._dict(location='Koppie',start_date='2026-07-01',end_date='2026-07-31',hours_display='Hours per Asset'))[2]
        soup=BeautifulSoup(html,'html.parser')
        for panel in soup.select('.daily-dashboard-tab-panel'):
            cards=panel.select('.daily-tyre-kpi')
            self.assertEqual(len(cards),2)
            self.assertEqual({c['data-category']:c['data-count'] for c in cards},{'ADT':'0','Dozer':'0'})

    def test_live_counts_match_both_tabs(self):
        from bs4 import BeautifulSoup
        from engineering.engineering.page.daily_availability_and_utilization_dashboard import daily_availability_and_utilization_dashboard as dashboard
        filters=frappe._dict(location='Klipfontein',start_date='2026-07-01',end_date='2026-07-31',asset_ownership='Isambane & Excavo Assets',machine_scope='Production + Swing/Spare Machines')
        after=dashboard.execute(filters)[2]
        after_soup=BeautifulSoup(after,'html.parser')
        counts={panel['data-panel']:{x['data-category']:x['data-count'] for x in panel.select('.daily-tyre-kpi')} for panel in after_soup.select('.daily-dashboard-tab-panel')}
        self.assertEqual(counts,{'hours':{'ADT':'0','Dozer':'0'},'au':{'ADT':'0','Dozer':'0'}})
        for panel in after_soup.select('.daily-dashboard-tab-panel'):
            for card in panel.select('.daily-tyre-kpi'):
                self.assertEqual(len(card.parent.select(':scope > .frappe-card')),3)


class TestTyreDamageRendering(unittest.TestCase):
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
            self.assertEqual({c['data-category']:c['data-count'] for c in panel.select('.daily-tyre-kpi')}, {'ADT':'1', 'Dozer':'1'})
