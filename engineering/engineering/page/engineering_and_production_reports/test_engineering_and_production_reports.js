// Run with node: asynchronous controls and delayed network responses model Frappe behavior.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(process.env.REPORT_PAGE_JS || path.join(__dirname,'engineering_and_production_reports.js'),'utf8');
const types=[
 {key:'hourly_production',label:'Hourly Production Summary',department:'Production',filters:['site','report_date','shift','hour_slot']},
 {key:'shift_production',label:'Shift Production Summary',department:'Production',filters:['site','report_date','shift']},
 {key:'daily_production',label:'Daily Production Summary',department:'Production',filters:['site','report_date']},
 {key:'hourly_downtime',label:'Hourly Downtime Summary',department:'Engineering',filters:['site','report_date','hour_slot']},
 {key:'daily_downtime',label:'Daily Downtime Summary',department:'Engineering',filters:['site','report_date','shift']},
];
const saved={name:'hour-1',site:'Klipfontein',report_date:'2026-08-03',hour_slot:'7:00-8:00'};
let handler, calls=[], downloads=[];
const context={console,URLSearchParams, __:(text,args)=>args?text.replace('{0}',args[0]):text,
 window:{open:url=>downloads.push(url)},frappe:{pages:{'engineering-and-production-reports':{}},
 utils:{escape_html:value=>String(value).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')},
 call:async request=>{calls.push(request);return {message:await handler(request)};}}};
vm.createContext(context);vm.runInContext(source+'\nglobalThis.ReportPage=EngineeringProductionReports;',context);
const elements={};
function element(selector) {
 return elements[selector] ||= {value:'',properties:{},classes:new Set(),attrs:{},0:{scrollIntoView(){}},
  text(value){this.value=value;return this;},html(value){this.value=value;return this;},
  prop(key,value){this.properties[key]=value;return this;},attr(key,value){this.attrs[key]=value;return this;},
  addClass(value){this.classes.add(value);return this;},removeClass(value){this.classes.delete(value);return this;}};
}
function makePage() {
 calls=[];downloads=[];
 handler=async ({method})=>method.endsWith('get_report_types')?types:method.endsWith('view_report')?{html:'<html>Saved preview</html>'}:{rows:[saved],next_start:null};
 const page=Object.create(context.ReportPage.prototype);
 Object.assign(page,{main:{find:element},method:'saved.',types:[],rows:[],sequence:0,viewSequence:0,controls:{},setting:false});
 for (const field of ['department','report_type','site','report_date','saved_report']) {
  page.controls[field]={df:{},value:'',refresh(){},get_value(){return this.value;},
   async set_value(value){if(this.value===value)return;await Promise.resolve();this.value=value;await page.changed(field);}};
 }
 return page;
}
let passed=0;
async function test(name,fn){await fn();passed++;console.log('PASS: '+name);}
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
(async()=>{
 await test('exact readable labels for both departments',async()=>{
  const p=makePage();
  assert.equal(p.reportLabel(saved,types[0]),'2026-08-03 | Klipfontein | 07:00-08:00');
  assert.equal(p.reportLabel({...saved,hour_slot:'23:00-24:00'},types[3]),'2026-08-03 | Klipfontein | 23:00-24:00');
  assert.equal(p.reportLabel({...saved,shift:'Day'},types[1]),'2026-08-03 | Klipfontein | Day Shift');
  assert.equal(p.reportLabel({...saved,shift:'Night'},types[1]),'2026-08-03 | Klipfontein | Night Shift');
  assert.equal(p.reportLabel(saved,types[2]),'2026-08-03 | Klipfontein | Full Daily');
  assert.equal(p.reportLabel({...saved,shift:'Night Shift'},types[4]),'2026-08-03 | Klipfontein | Night Shift');
  assert.equal(p.reportLabel({...saved,shift:'Full Daily'},types[4]),'2026-08-03 | Klipfontein | Full Daily');
 });
 await test('filters required, options refresh automatically, no Hour/Shift or table',async()=>{
  const p=makePage();await p.init();
  assert.equal(calls.filter(x=>x.method.endsWith('search_reports')).length,0);
  await p.controls.site.set_value('Klipfontein');
  assert.equal(calls.filter(x=>x.method.endsWith('search_reports')).length,0);
  await p.controls.report_date.set_value('2026-08-03');
  assert.equal(p.rows.length,1);
  const request=calls.find(x=>x.method.endsWith('search_reports'));
  assert.deepEqual(JSON.parse(JSON.stringify(request.args)),{report_type:'hourly_production',site:'Klipfontein',report_date:'2026-08-03',start:0});
  assert.equal(p.controls.saved_report.df.options[1].label,'2026-08-03 | Klipfontein | 07:00-08:00');
  assert.ok(!source.includes('add(\'shift\''));assert.ok(!source.includes('add(\'hour_slot\''));
  assert.ok(!source.includes('<table'));assert.ok(!source.includes('epr-more'));
 });
 await test('selection previews immediately, enables existing PDF download, clear preserves filters',async()=>{
  const p=makePage();await p.init();await p.controls.site.set_value('Klipfontein');await p.controls.report_date.set_value('2026-08-03');
  await p.controls.saved_report.set_value('hour-1');
  assert.equal(p.viewed.name,'hour-1');assert.equal(element('.epr-download').properties.disabled,false);
  assert.equal(element('iframe').attrs.srcdoc,'<html>Saved preview</html>');
  p.download();assert.ok(downloads[0].includes('download_pdf?report_type=hourly_production&name=hour-1'));
  await p.clearSelection();assert.equal(p.viewed,null);assert.equal(p.controls.site.value,'Klipfontein');assert.equal(p.rows.length,1);
  assert.equal(element('.epr-download').properties.disabled,true);
  assert.ok(calls.every(x=>/get_report_types|search_reports|view_report/.test(x.method)));
 });
 await test('all backend pages populate dropdown internally',async()=>{
  const p=makePage();await p.init();p.controls.site.value='Klipfontein';p.controls.report_date.value='2026-08-03';
  handler=async ({args})=>args.start===0?{rows:[saved],next_start:50}:{rows:[{...saved,name:'hour-2',hour_slot:'08:00-09:00'}],next_start:null};
  await p.load();assert.equal(p.rows.length,2);assert.equal(p.controls.saved_report.df.options.length,3);
  assert.equal(calls.filter(x=>x.method.endsWith('search_reports')).length,2);
 });
 await test('outdated filter search cannot repopulate selector',async()=>{
  const p=makePage();await p.init();p.controls.site.value='Klipfontein';p.controls.report_date.value='2026-08-03';
  const old=deferred();handler=async ({args})=>args.site==='Klipfontein'?old.promise:{rows:[],next_start:null};
  const first=p.load();await new Promise(r=>setImmediate(r));
  await p.controls.site.set_value('Gwab');old.resolve({rows:[saved],next_start:null});await first;
  assert.equal(p.rows.length,0);assert.equal(p.controls.saved_report.df.options.length,1);
 });
 await test('old preview cannot replace new selection or survive filter changes',async()=>{
  const p=makePage();await p.init();await p.controls.site.set_value('Klipfontein');await p.controls.report_date.set_value('2026-08-03');
  const old=deferred();handler=async ({method})=>method.endsWith('view_report')?old.promise:{rows:[],next_start:null};
  const first=p.controls.saved_report.set_value('hour-1');await new Promise(r=>setImmediate(r));
  await p.controls.report_date.set_value('2026-08-04');old.resolve({html:'Old preview'});await first;
  assert.equal(p.viewed,null);assert.equal(element('iframe').attrs.srcdoc,'');assert.equal(element('.epr-download').properties.disabled,true);
 });
 await test('newer saved-report selection wins over a delayed older preview',async()=>{
  const p=makePage();await p.init();await p.controls.site.set_value('Klipfontein');await p.controls.report_date.set_value('2026-08-03');
  p.rows.push({...saved,name:'hour-2'});
  const old=deferred();handler=async ({args})=>args.name==='hour-1'?old.promise:{html:'New preview'};
  const first=p.controls.saved_report.set_value('hour-1');await new Promise(r=>setImmediate(r));
  await p.controls.saved_report.set_value('hour-2');old.resolve({html:'Old preview'});await first;
  assert.equal(p.viewed.name,'hour-2');assert.equal(element('iframe').attrs.srcdoc,'New preview');
 });
 await test('empty results and failed preview never enable download',async()=>{
  const p=makePage();await p.init();p.controls.site.value='Klipfontein';p.controls.report_date.value='2026-08-03';
  handler=async()=>({rows:[],next_start:null});await p.load();assert.equal(p.rows.length,0);
  handler=async({method})=>{if(method.endsWith('view_report'))throw Error('denied');return {rows:[saved],next_start:null};};
  await p.load();await p.controls.saved_report.set_value('hour-1');assert.equal(p.viewed,null);assert.equal(element('.epr-download').properties.disabled,true);
 });
 console.log(`${passed} selector UX tests passed`);
})().catch(error=>{console.error(error);process.exitCode=1;});
