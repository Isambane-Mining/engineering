"""Stored A&U / MPP / six-slide presentation contracts; no live writes."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch
from zipfile import ZipFile
from lxml import etree
from pptx import Presentation
from . import monthly_tmm_assurance as api


def fixture():
    data=dict(site='Klipfontein',**api.reporting_period('2026-10',today=date(2026,11,3)),groups=[])
    plans=[dict(name=str(i),prod_month_start_date=a,prod_month_end_date=b) for i,(a,b) in enumerate([
        ('2026-07-20','2026-08-23'),('2026-08-24','2026-09-20'),('2026-09-21','2026-10-18')])]
    data['months']=api.resolve_mpp_periods(plans,data['months'])
    data.update(selected_period=data['months'][-1],warnings=[],unassigned_records=[])
    for i,group in enumerate(api.GROUPS):
        records=[dict(name=f'PRIVATE-RECORD-{group}-{n}',failure_classification=c,breakdown_reason='PRIVATE DESCRIPTION')
                 for n,c in enumerate(['Hydraulic','Hydraulic','Hydraulic','Engine','Engine','Safety Systems'])]
        data['groups'].append(dict(group=group,availability=[None if i==2 else 80,0 if i==0 else 85,68.81332236842105],counts=api.category_counts(records),actions=[dict(action='PRIVATE ACTION')]))
    return data


class TestMPPPeriods(unittest.TestCase):
    def months(self,month='2026-10'):
        return api.reporting_period(month,today=date(2027,2,3))['months']

    def test_confirmed_periods_from_plan_dates_and_end_month_labels(self):
        self.assertTrue(all(m['start'] is None and m['end'] is None for m in self.months()))
        d=fixture()
        self.assertEqual([(m['start'],m['end']) for m in d['months']], [('2026-07-20','2026-08-23'),('2026-08-24','2026-09-20'),('2026-09-21','2026-10-18')])
        self.assertEqual([m['label'] for m in d['months']],['Aug 2026','Sep 2026','Oct 2026'])

    def test_missing_duplicate_conflicting_and_cancelled_plans(self):
        plan=dict(name='one',prod_month_start_date='2026-09-21',prod_month_end_date='2026-10-18')
        result=api.resolve_mpp_periods([plan,dict(plan,name='two')],self.months())
        self.assertEqual(result[0]['status'],'missing')
        self.assertIsNone(result[0]['start'])
        self.assertEqual(result[-1]['status'],'ok')
        self.assertTrue(result[-1]['warnings'])
        conflicting=dict(plan,name='different',prod_month_start_date='2026-09-22')
        self.assertEqual(api.resolve_mpp_periods([plan,conflicting],self.months())[-1]['status'],'conflict')
        self.assertEqual(api.resolve_mpp_periods([dict(plan,docstatus=2)],self.months())[-1]['status'],'missing')

    def test_overlapping_adjacent_periods_rejected_inclusive_dates(self):
        plans=[dict(name='a',prod_month_start_date='2026-09-21',prod_month_end_date='2026-10-18'),
               dict(name='b',prod_month_start_date='2026-10-18',prod_month_end_date='2026-11-15')]
        result=api.resolve_mpp_periods(plans,self.months('2026-11'))
        self.assertEqual([m['status'] for m in result[-2:]],['conflict','conflict'])
        plans[-1]['prod_month_start_date']='2026-10-19'
        self.assertEqual([m['status'] for m in api.resolve_mpp_periods(plans,self.months('2026-11'))[-2:]],['ok','ok'])

    def test_year_rollover_and_inverted_dates(self):
        plans=[dict(name='dec',prod_month_start_date='2026-11-23',prod_month_end_date='2026-12-20'),
               dict(name='jan',prod_month_start_date='2026-12-21',prod_month_end_date='2027-01-17')]
        result=api.resolve_mpp_periods(plans,self.months('2027-01'))
        self.assertEqual(result[-1]['label'],'Jan 2027')
        self.assertEqual(result[-1]['start'],'2026-12-21')
        plans[-1]['prod_month_start_date']='2027-02-01'
        self.assertEqual(api.resolve_mpp_periods(plans,self.months('2027-01'))[-1]['status'],'conflict')

    def test_selected_period_missing_fails_without_calendar_fallback(self):
        period=api.reporting_period('2026-10',today=date(2026,11,3))
        periods=api.resolve_mpp_periods([],period['months'])
        with patch.object(api,'_period',return_value=period),patch.object(api,'_authorize_sources'),patch.object(api,'_mpp_periods',return_value=periods),patch.object(api.frappe,'throw',side_effect=ValueError) as fail:
            with self.assertRaises(ValueError):api.get_report('Klipfontein','2026-10')
        self.assertIn('No calendar-period substitution',fail.call_args.args[0])


class TestStoredHours(unittest.TestCase):
    def test_sql_regression_full_precision_and_single_multiplier(self):
        result=api.availability_by_group([dict(asset_category='ADT',shift_required_hours=Decimal('18240'),shift_available_hours=Decimal('14766.5299999999'))])
        self.assertAlmostEqual(result['ADTs'],68.81332510964866)
        self.assertEqual(f"{result['ADTs']:.2f}",'68.81')
        self.assertEqual(api.percent(result['ADTs']),'68.81%')

    def test_weighted_hours_exclusions_duplicates_zero_and_no_cap(self):
        rows=[dict(name='a',asset_category='TLB',shift_required_hours=10,shift_available_hours=10),
              dict(name='b',asset_category='Water Bowser',shift_required_hours=30,shift_available_hours=0),
              dict(name='c',asset_category='ADT',shift_required_hours=10,shift_available_hours=0),
              dict(name='d',asset_category='Loader',shift_required_hours=1,shift_available_hours=2),
              dict(name='bad',asset_category='Grader',shift_required_hours=100,shift_available_hours=100,invalid_pre_use_hours=1),
              dict(name='cancelled',asset_category='Drills',shift_required_hours=10,shift_available_hours=10,docstatus=2)]
        result=api.availability_by_group(rows+[rows[0]])
        self.assertEqual(result['Ancillary'],21.25)
        self.assertEqual(result['ADTs'],0)
        self.assertEqual(result['FELs'],170)
        self.assertIsNone(result['Graders']);self.assertIsNone(result['Drills'])
        self.assertIsNone(api.availability_by_group([dict(asset_category='ADT',shift_required_hours=0,shift_available_hours=5)])['ADTs'])

    def test_explicit_groups_no_dashboard_alias_inference(self):
        for category,group in api.CATEGORY_GROUPS.items():self.assertEqual(api.equipment_group(category),group)
        for category in ("ADT's",'LDV','Unknown',''):
            self.assertIsNone(api.equipment_group(category))


class TestMPPOverlap(unittest.TestCase):
    def test_october_ends_18th_and_carry_in_closed_once(self):
        rows=[dict(name='closed',breakdown_start_datetime='2026-08-01',resolved_datetime='2026-09-22'),
              dict(name='closed-before',breakdown_start_datetime='2026-08-01',resolved_datetime='2026-09-21 00:00:00'),
              dict(name='first',breakdown_start_datetime='2026-09-21'),
              dict(name='last',breakdown_start_datetime='2026-10-18 23:59:59'),
              dict(name='subsequent',breakdown_start_datetime='2026-10-19'),
              dict(name='cancelled',breakdown_start_datetime='2026-10-01',docstatus=2),
              dict(name='planned',breakdown_start_datetime='2026-10-01',downtime_type='Planned Maintenance')]
        result=api.monthly_population(rows+[rows[0]],'2026-09-21','2026-10-18')
        self.assertEqual([r['name'] for r in result],['closed','first','last'])
        november=api.monthly_population(rows,'2026-10-19','2026-11-15')
        self.assertIn('subsequent',{r['name'] for r in november})
        counts=api.category_counts([dict(r,failure_classification='Hydraulic') for r in result])
        self.assertEqual(counts['categories'][0]['count'],3)
        self.assertEqual(counts['categories'][-1]['cumulative_percent'],100)


class TestPresentation(unittest.TestCase):
    def test_six_slides_editable_charts_and_no_private_details(self):
        payload=api.presentation_bytes(fixture())
        Path('/tmp/tmm-mpp-presentation').mkdir(exist_ok=True)
        Path('/tmp/tmm-mpp-presentation/fixture.pptx').write_bytes(payload)
        deck=Presentation(BytesIO(payload))
        self.assertEqual(len(deck.slides),6)
        titles=[next(x.text for x in s.shapes if x.name=='tmm-title') for s in deck.slides]
        self.assertEqual(titles,['Availability by equipment group','Categorisation completeness','ADT Pareto','Excavator Pareto','Grader Pareto','Ancillary Pareto'])
        z=ZipFile(BytesIO(payload))
        slides=''.join(z.read(n).decode() for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
        for forbidden in ('PRIVATE-RECORD','PRIVATE DESCRIPTION','PRIVATE ACTION'):
            self.assertNotIn(forbidden,slides)
        self.assertIn('21 Sep 2026',slides);self.assertIn('18 Oct 2026',slides)
        charts=[n for n in z.namelist() if n.startswith('ppt/charts/chart') and n.endswith('.xml')]
        self.assertEqual(len(charts),5)
        ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
        for name in charts[1:]:
            xml=etree.fromstring(z.read(name))
            self.assertEqual(len(xml.xpath('//c:lineChart/c:ser',namespaces=ns)),2)
            series=xml.xpath('//c:lineChart/c:ser',namespaces=ns)
            values=[float(v) for v in series[0].xpath('c:val/c:numRef/c:numCache/c:pt/c:v/text()',namespaces=ns)]
            self.assertEqual(values[-1],100)
            self.assertEqual([float(v) for v in series[1].xpath('c:val/c:numRef/c:numCache/c:pt/c:v/text()',namespaces=ns)],[80]*3)
            self.assertEqual(xml.xpath('//c:valAx/c:scaling/c:max/@val',namespaces=ns)[-1],'100')

    def test_empty_groups_keep_six_slides_with_honest_empty_states(self):
        d=fixture()
        for g in d['groups']:g['counts']=api.category_counts([])
        deck=Presentation(BytesIO(api.presentation_bytes(d)))
        self.assertEqual(len(deck.slides),6)
        for s in list(deck.slides)[2:]:
            self.assertIn('No classified breakdown records',' '.join(x.text for x in s.shapes if x.has_text_frame))

    def test_template_has_no_historical_charts_images_notes_or_preview(self):
        with ZipFile(Path(api.__file__).with_name('monthly_tmm_template.pptx')) as z:
            self.assertFalse(any(any(part in n for part in ('ppt/media/','ppt/charts/','ppt/notesSlides/','docProps/thumbnail')) for n in z.namelist()))
            slides=''.join(z.read(n).decode() for n in z.namelist() if n.startswith('ppt/slides/slide') and n.endswith('.xml'))
            self.assertNotIn('consentrated',slides)
            self.assertNotIn('August–October 2026',slides)

    def test_completeness_note_matches_counts_without_record_details(self):
        d=fixture()
        d['groups'][0]['counts']=api.category_counts([dict(name='classified',failure_classification='Engine'),dict(name='missing')])
        d['unassigned_records']=[dict(name='unassigned')]
        deck=Presentation(BytesIO(api.presentation_bytes(d)))
        text=' '.join(s.text for s in deck.slides[1].shapes if s.has_text_frame)
        self.assertIn('39 distinct breakdown records',text)
        self.assertIn('37 have a recognised classification',text)
        self.assertIn('1 grouped records require classification review; 1 require equipment-group review',text)
        self.assertNotIn('unassigned',text)

    def test_export_permission_before_building_deck(self):
        with patch.object(api,'get_report',return_value=fixture()),patch.object(api,'_scope') as scope,patch.object(api,'presentation_bytes') as build:
            scope.return_value.check_permission.side_effect=PermissionError('print denied')
            with self.assertRaises(PermissionError):api.download_presentation('Klipfontein','2026-10')
            build.assert_not_called()


    def test_export_checks_print_for_every_group_before_build(self):
        from unittest.mock import Mock
        from types import SimpleNamespace
        good=SimpleNamespace(check_permission=Mock())
        denied=SimpleNamespace(check_permission=Mock(side_effect=PermissionError('second group denied')))
        with patch.object(api,'get_report',return_value=fixture()),patch.object(api,'_scope',side_effect=[good,denied]),patch.object(api,'presentation_bytes') as build:
            with self.assertRaises(PermissionError):api.download_presentation('Klipfontein','2026-10')
            build.assert_not_called()
        good.check_permission.assert_called_once_with('print')

    def test_twenty_causes_stay_editable_and_cumulative_ends_at_100(self):
        d=fixture()
        for group in d['groups']:
            group['counts']=api.category_counts([dict(name=str(i),failure_classification=c) for i,c in enumerate(api.INITIAL_CLASSIFICATIONS)])
        payload=api.presentation_bytes(d)
        Path('/tmp/tmm-mpp-presentation/dense.pptx').write_bytes(payload)
        deck=Presentation(BytesIO(payload))
        chart=next(shape.chart for shape in deck.slides[2].shapes if shape.has_chart)
        self.assertEqual(len(chart.series[0].values),20)
        self.assertEqual(list(chart.series[0].values),[1]*20)
        self.assertEqual(chart.series[1].values[-1],100)
        ns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
        self.assertEqual(chart._chartSpace.xpath('.//c:catAx/c:tickLblSkip/@val'),['1','1'])
        self.assertEqual(chart._chartSpace.xpath('.//c:barChart/c:ser/c:dLbls/c:showVal/@val'),['1'])
