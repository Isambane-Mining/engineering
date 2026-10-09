const method='engineering.engineering.page.reliability_engineering.problem_machines.get_problem_machines';
const setFilter=(name,value)=>cy.get('.re-problems-tab').then(root=>{
 const panel=root.closest('.reliability-engineering-page')[0].reliabilityEngineering.problems;
 return panel[name].set_value(value);
});
describe('LAB Problem Machines',()=>{
 beforeEach(()=>{
  cy.setCookie('sid',Cypress.env('sid'),{domain:new URL(Cypress.config('baseUrl')).hostname,secure:true,log:false});
  cy.readFile('engineering/engineering/page/reliability_engineering/reliability_engineering.js').then(script=>{
   cy.intercept('**/api/method/frappe.desk.desk_page.getpage*',request=>request.continue(response=>{
    if(response.body.docs?.[0]?.name==='reliability-engineering') response.body.docs[0].script=script;
   }));
  });
  cy.readFile('engineering/public/css/engineering.css').then(body=>{
   cy.intercept('GET','**/assets/engineering/css/engineering.css*',{body,headers:{'content-type':'text/css'}});
  });
  cy.viewport(1440,1000);
  cy.visit('/app/reliability-engineering');
  cy.get('.re-analysis-tab').should('be.visible');
  cy.get('#re-problems-tab').click();
  cy.get('[data-fieldname="pm_top"] select').should('have.value','5');
  setFilter('from','2026-08-01');setFilter('to','2026-08-31');setFilter('site','Klipfontein');
  cy.get('.pm-table tbody tr').should('have.length',5);
 });
 it('synchronizes Top N charts, table and cards, and preserves analysis state',()=>{
  let reference;
  cy.request({url:'/api/method/'+method,qs:{from_date:'2026-08-01',to_date:'2026-08-31',location:'Klipfontein',show_top:10}})
   .its('body.message.ranking').then(rows=>reference=rows.map(row=>[row.asset,row.problem_score]));
  [1,3,5,10].forEach(top=>{
   cy.intercept('POST','**/api/method/'+method).as('ranking');
   cy.get('[data-fieldname="pm_top"] select').select(String(top));
   cy.get('.pm-table tbody tr').should('have.length',top);
   cy.get('.pm-bars li').should('have.length',top);
   cy.get('.pm-card').should('have.length',top);
   cy.get('.pm-frequency svg').should('exist');
   cy.get('.re-problems-tab').then(root=>{
    const panel=root.closest('.reliability-engineering-page')[0].reliabilityEngineering.problems;
    expect(panel.data.ranking.map(row=>[row.asset,row.problem_score])).deep.eq(reference.slice(0,top));
    expect(panel.frequencyChart.data.labels).to.have.length(top);
   });
  });
  cy.get('.pm-table-wrap').should('be.visible');
  cy.screenshot('problem-machines-desktop',{capture:'viewport'});
  cy.get('#re-analysis-tab').click();cy.get('.re-analysis-tab').should('be.visible');
  cy.get('[data-fieldname="measurement"] select').should('have.value','Overview');
  cy.get('#re-problems-tab').click();cy.get('.pm-table tbody tr').should('have.length',10);
 });
 it('uses cards on phones and tablets without page overflow',()=>{
  [375,768,1024].forEach(width=>{
   cy.viewport(width,900);
   cy.get('.pm-table-wrap').should('not.be.visible');
   cy.get('.pm-card').first().scrollIntoView().should('be.visible').and('contain','MTBF').and('contain','BDFR');
   cy.get('.pm-filters').then(element=>expect(element[0].scrollWidth).lte(element[0].clientWidth+1));
   cy.get('.re-shell').then(element=>expect(element[0].scrollWidth).lte(element[0].clientWidth+1));
  });
  cy.viewport(375,900);cy.get('.pm-card').first().scrollIntoView({offset:{top:-80,left:0}});cy.screenshot('problem-machines-mobile-cards',{capture:'viewport'});
 });
 it('keeps populated first-tab filters and drilldown working independently',()=>{
  cy.get('#re-analysis-tab').click();
  cy.get('.re-analysis-tab').then(root=>{
   const page=root.closest('.reliability-engineering-page')[0].reliabilityEngineering;
   return Promise.all([page.from.set_value('2026-08-01'),page.to.set_value('2026-08-31'),page.location.set_value('Koppie'),page.asset.set_value('EX015')]);
  });
  cy.get('.re-table tbody tr').should('have.length.greaterThan',0);
  cy.get('.re-kpis').should('contain','Breakdowns');
  cy.get('.re-table tbody tr').first().click();
  cy.get('.re-show-all').should('exist').click();
  cy.get('.re-breakdowns .re-event').should('have.length.greaterThan',0);
  cy.get('#re-problems-tab').click();
  cy.get('.pm-summary').should('contain','Klipfontein');
  cy.get('.pm-count').should('contain','44');
  cy.get('.re-problems-tab').then(root=>root.closest('.reliability-engineering-page')[0].reliabilityEngineering.load());
  cy.get('.pm-summary').should('contain','Klipfontein');
  cy.get('.pm-table tbody tr').should('have.length',5);
 });
 it('explains formulas, repeat data quality and the small-machine trial on both layouts',()=>{
  [1440,375].forEach(width=>{
   cy.viewport(width,900);
   cy.get('.re-problems-tab .re-formulas').should('have.attr','open');
   cy.get('.re-problems-tab .re-formulas').should('contain','BDFR = breakdowns / validated operating hours × 1,000')
    .and('contain','% Repeat Breakdown = known repeat breakdowns / all breakdowns × 100')
    .and('contain','7 days').and('contain','Free-text descriptions do not confirm repeats')
    .and('contain','MTBF =').and('contain','MTTR =').and('contain','Problem Score =');
   cy.get('.pm-trial-note').should('contain','Top 1–3');
   cy.get('.pm-cards').should('contain','Unavailable').and('contain','recurrence unverified');
   cy.get('#re-analysis-tab').click();
   cy.get('.re-analysis-tab .re-formulas').should('contain','BDFR =').and('contain','% Repeat Breakdown =');
   cy.get('#re-problems-tab').click();
  });
 });
 it('changes sites and dates, and handles empty and invalid ranges',()=>{
  setFilter('site','Koppie');cy.get('.pm-count').should('contain','19');
  setFilter('site','Uitgevallen');cy.get('.pm-count').should('contain','25');
  setFilter('from','2026-08-01');setFilter('to','2026-08-07');
  cy.get('.pm-summary').should('contain','2026-08-07');
  setFilter('to','2026-10-07');setFilter('from','2026-10-01');
  cy.get('.pm-count').should('contain','0');cy.get('.pm-card').should('not.exist');cy.get('.pm-impact').should('contain','No machines');
  setFilter('from','2026-10-08');cy.get('.pm-status').should('contain','on or after');cy.get('.pm-results').should('not.be.visible');
 });
});
