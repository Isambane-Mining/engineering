const assert = require('node:assert/strict');
const {test} = require('node:test');
const fs = require('node:fs');
const path = require('node:path');
const sourcePath = path.resolve(__dirname, '../../../../../is_production/is_production/production/page/hourly_productivity_analysis/hourly_productivity_analysis.js');
const source = require(sourcePath);
const page = require('./machines_available.js');
const fixture = {
  site:'Test <site>', hours:Array.from({length:24}, (_, i) => `${(i+6)%24}:00`),
  rows:['September','October'].map((month, i) => ({date:`2026-${i+9}-01`, day:'Thu', month,
    month_key:month, fleet_total:4, cells:Array.from({length:24}, (_, h) => ({
      completed:h!==23, has_record:h!==22, available:[4,3.5,2,1,0,null][h%6], utilised:h%4
    }))}))
};
test('matrix markup matches original for every unavailable filter and month boundary', () => {
  for (const filter of [null,0,1,2,3,4]) {
    const html = page.renderMachineMatrix(fixture,filter).replace(/ tabindex="0" role="button" aria-haspopup="dialog" aria-expanded="false" data-machine-row="\d+" data-machine-hour="\d+"/g, '');
    assert.equal(html,source.renderMachineMatrix(fixture,filter));
  }
  const html=page.renderMachineMatrix(fixture,1);
  assert.equal((html.match(/class="hpa-month-divider"/g)||[]).length,2);
  assert.equal((html.match(/<td class="hpa-cell hm-cell/g)||[]).length,48);
  assert.match(html,/Test &lt;site&gt;/);
  assert.match(html,/hm-unavailable-match/);
});
test('unavailable interval boundaries and unknown values match source', () => {
  for (const total of [0,4,null,NaN]) for (const available of [0,3,3.5,4,null,NaN])
    for (const selected of [null,0,1,2,-1,1.5])
      assert.equal(page.matchesUnavailableRange(total,available,selected),source.matchesUnavailableRange(total,available,selected));
});
test('standalone script has no other tab controllers or asset loading', () => {
  const js=fs.readFileSync(path.join(__dirname,'machines_available.js'),'utf8');
  assert.doesNotMatch(js,/HourlyProductivityAnalysisPage|loadSummary|hourlyProductivityTabs|createElement\('script'\)/);
  assert.match(js,/export_machine_excel/);
});
test('popup renderer escapes PBM fields and handles empty results', () => {
  assert.match(page.renderBreakdowns({machines:[]}), /No recorded breakdowns/);
  const html=page.renderBreakdowns({machines:[{machine_number:'ADT <1>',downtime_minutes:30,breakdowns:[{
    failure_classification:'<img onerror=bad>',description:'<script>bad</script>',
    breakdown_start_datetime:'2026-10-01 00:30:00',resolved_datetime:null,overlap_minutes:30
  }]}]});
  assert.match(html,/ADT &lt;1&gt;/);
  assert.match(html,/&lt;script&gt;bad&lt;\/script&gt;/);
  assert.match(html,/Still Open/);
  assert.doesNotMatch(html,/<script>|<img|Source PBM/);
});

test('month model includes full calendar, selected range and recorded-only KPI denominators', () => {
  const data={rows:[{date:'2026-02-02',fleet_total:4,cells:[
    {completed:true,has_record:true,available:3.5,utilised:2},
    {completed:true,has_record:true,available:4,utilised:0},
    {completed:false,has_record:true,available:0,utilised:0},
    {completed:true,has_record:false,available:0,utilised:0}]}]};
  const model=page.monthModel(data,'2026-02');
  assert.equal(model.days.length,28);
  assert.equal(model.offset,6);
  assert.equal(model.days[1].index,0);
  assert.equal(model.days[0].index,-1);
  assert.equal(model.kpis.available,3.75);
  assert.equal(model.kpis.utilised,1);
  assert.equal(model.kpis.unavailable,.25);
  assert.equal(model.kpis.fleet,4);
  assert.equal(model.kpis.observed,2);
  assert.equal(page.monthModel({rows:[]},'2024-02').days.length,29);
  assert.equal(page.monthModel({rows:[]},'2026-02').kpis.available,null);
});
test('daily view preserves operational ordering, unknowns and red highlighting', () => {
  const data={hours:Array.from({length:24},(_,i)=>`${(i+6)%24}:00`),rows:[{
    date:'2026-09-01',fleet_total:4,cells:Array.from({length:24},(_,i)=>({completed:true,
      has_record:i!==23,available:3.5,utilised:2}))}]};
  const html=page.renderDailyView(data,0,1);
  assert.equal((html.match(/data-machine-hour=/g)||[]).length,24);
  assert.match(html,/Day Shift · 06:00–18:00/);
  assert.match(html,/Night Shift · 18:00–06:00/);
  assert.match(html,/hm-unavailable-match/);
  assert.match(html,/Unavailable/);
  assert.doesNotMatch(page.renderDailyView(data,0,null),/hm-unavailable-match/);
});
