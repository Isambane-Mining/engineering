const expected = ['Mechanical', 'Hydraulic', 'Electrical', 'Engine', 'Transmission / Drivetrain', 'Braking System', 'Steering System', 'Cooling System', 'Fuel System', 'Lubrication System', 'Undercarriage / Suspension', 'Tyres / Wheels', 'Structural', 'Pneumatic / Air System', 'Electronic / Control System', 'Air Conditioning / Cab', 'Safety Systems', 'Attachments / Implements', 'Pump / Fluid Transfer Systems', 'Tipping / Body Hoist Systems'];

describe('Failure classification on LAB after activation', () => {
    beforeEach(() => cy.setCookie('sid', Cypress.env('sid'), {domain: 'juan.isambane.co.za', secure: true, log: false}));
    it('uses the existing optional Link', () => {
        cy.request({url: '/api/resource/Plant Breakdown or Maintenance', qs: {fields: JSON.stringify(['name']), limit_page_length: 1}})
            .its('body.data.0.name').then(name => cy.visit('/app/plant-breakdown-or-maintenance/' + encodeURIComponent(name)));
        cy.window().should(win => expect(win.cur_frm?.fields_dict.failure_classification).to.exist);
        cy.window().then(win => {
            const field = win.cur_frm.fields_dict.failure_classification;
            expect(field.df.fieldtype).eq('Link');
            expect(field.df.options).eq('Breakdown Failure Classification');
            expect(field.df.reqd || 0).eq(0);
        });
    });
    it('offers all 20 master classifications', () => {
        cy.visit('/app/reliability-engineering');
        cy.get('.mr-cards .mr-card').should('have.length', 6);
        cy.get('.mr-filters [data-fieldname="category"] select option').then(options => {
            const values = [...options].map(x => x.value);
            expected.forEach(value => expect(values).include(value));
        });
    });
});
