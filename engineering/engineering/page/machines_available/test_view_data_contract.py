"""All viewing modes consume the existing authoritative operational-hour payload."""
from datetime import datetime
from unittest import TestCase
from is_production.production.page.hourly_productivity_analysis import test_hourly_productivity_analysis as source_tests
from is_production.production.page.hourly_productivity_analysis import hourly_productivity_analysis as source


class TestViewDataContract(TestCase):
    def setUp(self):
        self.fixture=source_tests.TestHourlyProductivityAnalysis()
        self.fixture.setUp()

    def test_month_views_receive_full_24_hour_days_without_synthetic_data(self):
        data=self.fixture.build(start='2026-10-01',end='2026-10-31')
        self.assertEqual(len(data['rows']),31)
        for row in data['rows']:
            self.assertEqual(len(row['cells']),24)
            self.assertEqual(row['cells'][0]['start'],row['date']+' 06:00:00')
            self.assertTrue(all(not cell['has_record'] for cell in row['cells']))
            self.assertTrue(all(cell['record_status']=='missing' for cell in row['cells']))
        self.assertEqual(data['rows'][-1]['cells'][18]['start'],'2026-11-01 00:00:00')

    def test_all_view_scopes_follow_saved_mpp_and_same_filter_contract(self):
        plan=self.fixture.plan
        plan['excavator_truck_assignments']=[dict(excavator='EX1',truck='T1'),dict(excavator='',truck='T2')]
        for scope,total in [('all',2),('production',1),('spare',1)]:
            data=source.build_analysis('2026-10-01','2026-10-02','Koppie',[plan],self.fixture.f.assets,[],[],machine_scope=scope,now=datetime(2026,11,2))
            self.assertEqual(len(data['rows']),2)
            self.assertEqual({row['fleet_total'] for row in data['rows']},{total})
            self.assertEqual((data['from_date'],data['to_date']),('2026-10-01','2026-10-02'))
