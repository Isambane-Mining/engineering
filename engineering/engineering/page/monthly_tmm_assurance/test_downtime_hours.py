"""MPP downtime, deterministic local subcategories and editable export regressions."""
from datetime import datetime, date
from io import BytesIO
import unittest
from unittest.mock import patch
from pptx import Presentation
from . import monthly_tmm_assurance as api
from engineering.controllers import failure_classification as fc

class TestDowntimeHours(unittest.TestCase):
    def test_support_groups_are_separate(self):
        rows=[dict(name=str(i),asset_category=c,shift_required_hours=10,shift_available_hours=i*2) for i,c in enumerate(('Diesel Bowsers','Water Bowser','TLB','Service Truck'))]
        result=api.availability_by_group(rows)
        self.assertEqual([result[g] for g in ('Diesel bowsers','Water bowsers','TLBs','Service trucks')],[0,17,34,51])
        self.assertNotIn('Ancillary',api.GROUPS)

    def test_clips_carry_in_closed_open_deduplicates_and_flags_invalid(self):
        rows=[dict(name='carried',breakdown_start_datetime='2026-09-01',resolved_datetime='2026-09-22'),
              dict(name='open',breakdown_start_datetime='2026-10-18 20:00:00'),
              dict(name='bad',breakdown_start_datetime='broken'),
              dict(name='reversed',breakdown_start_datetime='2026-10-02',resolved_datetime='2026-10-01'),
              dict(name='future',breakdown_start_datetime='2026-11-01'),
              dict(name='excluded',breakdown_start_datetime='2026-10-01',exclude_from_au=1),
              dict(name='planned',breakdown_start_datetime='2026-10-01',downtime_type='Planned Maintenance')]
        calls=[]
        def measured(row,a,b):calls.append((row['name'],a,b));return (b-a).total_seconds()/3600/2
        result=api.measure_records(rows+[rows[0]],'2026-09-21','2026-10-18',datetime(2026,10,18,22),measured)
        self.assertEqual([r['name'] for r in result],['carried','open','bad','reversed'])
        self.assertEqual([r['downtime_hours'] for r in result[:2]],[12,1])
        self.assertEqual(calls[0][1],datetime(2026,9,21))
        self.assertTrue(all(r['timestamp_review'] for r in result[2:]))

    def test_hours_not_counts_full_denominator_crossing_and_top_three(self):
        rows=[dict(name=str(i),failure_classification='Electrical',downtime_hours=h,breakdown_reason=reason) for i,(h,reason) in enumerate([(1,'headlight faulty'),(1,'head light not working'),(8,'batery faulty'),(1,'no power')])]
        rows.append(dict(name='tyre',failure_classification='Tyres / Wheels',downtime_hours=3,breakdown_reason='tyer puncture'))
        rows.append(dict(name='blank',failure_classification='',downtime_hours=100))
        result=api.category_downtime(rows+[rows[0]],fc.INITIAL_CLASSIFICATIONS,{})
        self.assertEqual(result['classified_hours'],14)
        self.assertEqual(result['unresolved_hours'],100)
        self.assertEqual(result['categories'][0]['category'],'Electrical')
        self.assertTrue(result['categories'][1]['priority'])
        self.assertEqual(result['categories'][1]['cumulative_percent'],100)
        sub=result['categories'][0]['subcategories']
        self.assertEqual([(x['subcategory'],x['count'],x['hours']) for x in sub],[('Lighting fault',2,2),('Battery fault',1,8)])
        self.assertEqual(result['categories'][0]['subcategory_review_hours'],1)
        equal=api.category_downtime([dict(name=c,failure_classification=c,downtime_hours=1) for c in fc.INITIAL_CLASSIFICATIONS],fc.INITIAL_CLASSIFICATIONS,{})
        self.assertEqual(equal['categories'][9]['cumulative_percent'],50)
        self.assertEqual(equal['priority_category_count'],16)

    def test_local_synonyms_specificity_conflicts_and_manual(self):
        for reason,category,label in [('tyre puncher','Tyres / Wheels','Tyre puncture'),('tyer puncture','Tyres / Wheels','Tyre puncture'),('tyer - puncher','Tyres / Wheels','Tyre puncture'),('head-light faulty','Electrical','Lighting fault'),('BATERY, faulty!','Electrical','Battery fault'),('head light not working','Electrical','Lighting fault')]:
            self.assertEqual(fc.standard_subcategory(reason,category,{})['subcategory'],label)
        for reason,category in [('does not start','Engine'),('oil leak','Hydraulic'),('no power','Electrical'),('battery faulty and headlight faulty','Electrical'),('battery faulty','Engine')]:
            self.assertEqual(fc.standard_subcategory(reason,category,{})['status'],'Review')
        self.assertEqual(fc.standard_subcategory('custom','Electrical',{},approved_mapping='Approved component')['subcategory'],'Approved component')
        configured={'Hydraulic':['boom cylinder','cylinder']}
        self.assertEqual(fc.standard_subcategory('boom cylinder leaking','Hydraulic',configured)['subcategory'],'Boom cylinder')

    def test_planning_helper_used_without_elapsed_fallback(self):
        with patch('engineering.engineering.report.availability_and_utilisation_month_end_report.availability_and_utilisation_month_end_report.get_required_downtime_minutes_for_breakdown',return_value={'required_downtime_minutes':90}) as fn:
            self.assertEqual(api.planning_downtime('Test',{'asset_name':'Asset'},datetime(2026,9,21),datetime(2026,9,22)),1.5)
            self.assertEqual(fn.call_args.args[0]['location'],'Test')

    def test_presentation_groups_editable_and_priority_continuations(self):
        from .test_mpp_presentation import fixture
        data=fixture()
        for g in data['groups']:
            g['counts']=api.category_downtime([dict(name=c,failure_classification=c,downtime_hours=1) for c in fc.INITIAL_CLASSIFICATIONS],fc.INITIAL_CLASSIFICATIONS,{})
        deck=Presentation(BytesIO(api.presentation_bytes(data)))
        titles=[next(s.text for s in slide.shapes if s.name=='tmm-title') for slide in deck.slides]
        self.assertEqual(titles[:3],['Prime movers availability','Support equipment availability','ADT Pareto'])
        self.assertTrue(any('Dozer Pareto'==t for t in titles))
        self.assertTrue(any('continued' in t.lower() for t in titles))
        charts=[s.chart for slide in deck.slides for s in slide.shapes if s.has_chart]
        self.assertEqual(list(charts[0].plots[0].categories),['ADTs','Excavators','Dozers','Drills'])
        self.assertTrue(all(chart.part.chart_workbook.xlsx_part is not None for chart in charts))

class TestCanonicalPlanningCalculation(unittest.TestCase):
    def test_required_cap_startup_fatigue_and_zero_required_shift(self):
        from engineering.engineering.report.availability_and_utilisation_engine import availability_and_utilisation_engine as engine
        from engineering.engineering.doctype.availability_and_utilisation import availability_and_utilisation as au
        from datetime import timedelta
        plans={('Test','2026-09-21'):dict(shift_system='2x12Hour',shift_day_hours=6,shift_night_hours=0)}
        with patch.object(engine,'get_planning_rows',return_value=[]),patch.object(engine,'build_planning_map',return_value=plans),patch.object(au,'_exclusion_windows',side_effect=lambda site,shift,a,b:[(a,a+timedelta(hours=1)),(b-timedelta(hours=1),b)]):
            # 12 elapsed daytime hours minus 2 excluded, capped at 6 required;
            # nighttime has no required hours and contributes nothing.
            self.assertEqual(api.planning_downtime('Test',{'asset_name':'A'},datetime(2026,9,21,6),datetime(2026,9,22,6)),6)
            # Short overlap is measured after the same startup exclusion.
            self.assertEqual(api.planning_downtime('Test',{'asset_name':'A'},datetime(2026,9,21,6),datetime(2026,9,21,8)),1)
