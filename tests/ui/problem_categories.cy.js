const expected = ['Brakes', 'Steering', 'Engine / Starting', 'Hydraulics', 'Electrical', 'Cooling', 'Transmission / Drivetrain', 'Tyres / Wheels', 'Air Conditioning', 'Other'];
const dashboard = action => cy.get('.reliability-engineering-page').then(root => action(root[0].machineReliability));

describe('Optional breakdown problem categories on LAB', () => {
    beforeEach(() => {
        cy.setCookie('sid', Cypress.env('sid'), {domain: 'juan.isambane.co.za', secure: true, log: false});
    });

    it('opens an existing breakdown with an optional blank category beside the reason', () => {
        cy.request({url: '/api/resource/Plant Breakdown or Maintenance', qs: {fields: JSON.stringify(['name']), limit_page_length: 1}})
            .its('body.data.0.name').then(name => cy.visit('/app/plant-breakdown-or-maintenance/' + encodeURIComponent(name)));
        cy.window().should(win => expect(win.cur_frm?.fields_dict.problem_category).to.exist);
        cy.window().then(win => {
            const form = win.cur_frm;
            const field = form.fields_dict.problem_category;
            expect(field.df.reqd).eq(0);
            expect(field.df.mandatory_depends_on).not.to.be.ok;
            expect(form.doc.problem_category).not.to.be.ok;
            expect(field.df.options.split('\n')).deep.eq(['', ...expected]);
            const order = form.meta.fields.map(x => x.fieldname);
            expect(order.indexOf('problem_category')).eq(order.indexOf('breakdown_reason') + 1);
        });
        cy.get('[data-fieldname="problem_category"] select').select('Steering').should('have.value', 'Steering').select('').should('have.value', '');
        cy.window().then(win => {
            const field = win.cur_frm.fields_dict.problem_subcategory;
            expect(field.df.reqd).eq(0);
            expect(field.df.mandatory_depends_on).not.to.be.ok;
            expect(win.cur_frm.doc.problem_subcategory).not.to.be.ok;
        });
        cy.get('[data-fieldname="problem_subcategory"]').should('not.be.visible');
        cy.get('[data-fieldname="problem_category"] select').select('Tyres / Wheels');
        cy.get('[data-fieldname="problem_subcategory"] select').should('be.visible').select('Tyre Damage').select('');
        cy.get('[data-fieldname="problem_category"] select').select('');
        // Saving compatibility is exercised through transaction-only document tests.
    });

    it('uses the ten settings categories, searches steering and preserves brake results', () => {
        cy.visit('/app/reliability-engineering');
        cy.get('.mr-cards .mr-card').should('have.length', 6);
        cy.get('.mr-filters [data-fieldname="category"] select option').then(options => expect([...options].map(x => x.value)).deep.eq(['All Problems', ...expected]));
        dashboard(async page => {
            page.initializing = true;
            await page.fields.from_date.set_value('2026-05-30');
            await page.fields.to_date.set_value('2026-09-12');
            await page.fields.category.set_value('Steering');
            page.initializing = false;
            await page.load();
            expect(page.data.keywords).include('steering');
            expect(page.data.summary.direct_failures).greaterThan(0);
            expect(page.data.timeline.filter(x => x.is_failure).every(x => !x.problem_category && x.match_source === 'Reason keywords')).eq(true);
        });
        cy.get('.mr-marker.failure').first().click();
        cy.get('.modal:visible').should('contain', 'Problem Category').and('contain', 'Matched by');
        cy.wait(400);
        cy.get('.modal:visible .btn-modal-close').click();
        dashboard(async page => {
            page.initializing = true;
            await page.fields.category.set_value('Brakes');
            await page.fields.fleet.set_value('IS545');
            page.initializing = false;
            await page.load();
            expect(page.data.summary.direct_failures).eq(7);
            expect(page.data.summary.average_failure_gap).eq(32.25);
            await page.fields.additional_keywords.set_value('starter');
            await page.load();
            expect(page.data.keywords).include('starter');
        });
    });
});
