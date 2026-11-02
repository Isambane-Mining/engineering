// Read-only live LAB activation checks. Document-save tests run in rolled-back Python transactions.
const login = () => cy.setCookie('sid', Cypress.env('sid'), {domain: 'juan.isambane.co.za', secure: true, log: false});

describe('Combined failure classification activation on LAB', () => {
    beforeEach(() => { login(); cy.viewport(1440, 1000); });
    it('removes both retired form controls and keeps the existing Link optional', () => {
        cy.request({url: '/api/resource/Plant Breakdown or Maintenance', qs: {fields: JSON.stringify(['name']), limit_page_length: 1}})
            .its('body.data.0.name').then(name => cy.visit('/app/plant-breakdown-or-maintenance/' + encodeURIComponent(name)));
        cy.window().should(win => expect(win.cur_frm?.fields_dict.failure_classification).to.exist);
        cy.window().then(win => {
            const fields = win.cur_frm.fields_dict;
            expect(fields.problem_category).not.to.exist;
            expect(fields.problem_subcategory).not.to.exist;
            expect(fields.failure_classification.df.fieldtype).eq('Link');
            expect(fields.failure_classification.df.options).eq('Breakdown Failure Classification');
            expect(fields.failure_classification.df.reqd || 0).eq(0);
            expect(fields.failure_classification.df.mandatory_depends_on).not.to.be.ok;
        });
    });
    it('preserves all three reliability views and machine filter selections', () => {
        cy.visit('/app/reliability-engineering');
        cy.get('.mr-cards .mr-card').should('have.length', 6);
        cy.get('.re-combined-tabs [data-report]').should('have.length', 3);
        cy.get('.mr-filters [data-fieldname="category"] select').select('Braking System');
        cy.get('.re-combined-tabs [data-report="analysis"]').click();
        cy.get('#re-combined-analysis-panel').should('be.visible');
        cy.get('.re-combined-tabs [data-report="problems"]').click();
        cy.get('#re-combined-problems-panel').should('be.visible');
        cy.get('.re-combined-tabs [data-report="machine"]').click();
        cy.get('.mr-filters [data-fieldname="category"] select').should('have.value', 'Braking System');
    });
    it('shows matching ADT drill-down counts and retains only Dozer average cards', () => {
        cy.visit('/app/daily-availability-and-utilization-dashboard', {onBeforeLoad: win => win.localStorage.clear()});
        cy.get('.daily-availability-and-utilization-dashboard-wrapper').should(root => expect(root[0].daily_availability_dashboard.initializing).eq(false));
        cy.get('.daily-availability-and-utilization-dashboard-wrapper').then(async root => {
            const view=root[0].daily_availability_dashboard;
            view.initializing=true;
            for (const [key,value] of Object.entries({location:'Klipfontein',start_date:'2026-07-01',end_date:'2026-07-31'})) await view[key].set_value(value);
            view.initializing=false; view.load_dashboard();
        });
        cy.get('.daily-availability-and-utilization-dashboard-wrapper').should(root => expect(root[0].daily_availability_dashboard.loading).eq(false));
        cy.get('[data-panel="hours"] .daily-tyre-kpi[data-category="ADT"]').should('have.attr','data-count','0').click();
        cy.get('.tyre-breakdown-popup').should('be.visible').and('contain','including rims, studs and bearings').and('contain','No classified tyre-related breakdowns');
        cy.wait(400); // Bootstrap ignores hide() during its opening transition.
        cy.get('.tyre-close').click();
        cy.get('.tyre-breakdown-popup').should('not.be.visible');
        cy.get('.daily-dashboard-tab-button[data-tab="au"]').click();
        cy.get('[data-panel="au"] .daily-tyre-kpi[data-category="ADT"]').should('have.attr','data-count','0');
        cy.get('.daily-tyre-kpi[data-category="Dozer"]').should('not.exist');
        cy.get('[data-kpi-category="Dozer"] .daily-au-average').should('have.length',2);
    });
    it('loads live TMM data and exposes the master classifications for details and actions', () => {
        cy.visit('/app/monthly-tmm-assurance');
        cy.get('.monthly-tmm-assurance').should('be.visible');
        cy.get('.monthly-tmm-assurance').then(async root => {
            let element=root[0];
            while (element && !element.monthly_tmm_assurance) element=element.parentElement;
            expect(element,'Monthly TMM Page instance').to.exist;
            const view=element.monthly_tmm_assurance;
            await view.ready; view.initializing=true;
            await view.month.set_value('2026-07'); await view.site.set_value('Koppie');
            view.initializing=false; await view.load();
        });
        cy.get('.tmm-all-categories summary').click();
        cy.get('.tmm-inspect-category').should('have.length',20);
        cy.get('.tmm-details').should('contain','Braking System').and('contain','Safety Systems');
        cy.viewport(390,844);
        cy.get('.monthly-tmm-assurance').then(root => expect(root[0].scrollWidth).lte(root[0].clientWidth+1));
        cy.screenshot('live-tmm-classifications-mobile',{capture:'viewport'});
    });
});
