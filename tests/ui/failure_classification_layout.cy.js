// Real server-rendered markup using offline fixtures; no running LAB changes.
describe('ADT tyre / wheel card and retained Dozer averages', () => {
    beforeEach(() => cy.visit('/'));
    it('keeps the ADT card on both tabs and preserves Dozer performance content', () => {
        ['hours', 'au'].forEach(tab => {
            cy.get(`.daily-dashboard-tab-button[data-tab="${tab}"]`).click();
            cy.get(`[data-panel="${tab}"] .daily-tyre-kpi`).should('have.length', 1).and('be.visible')
                .and('have.attr', 'data-category', 'ADT').and('have.attr', 'data-count', '1');
            cy.get(`[data-panel="${tab}"] .daily-tyre-kpi`).should('contain', 'Tyre / Wheel Breakdowns');
            cy.get(`[data-panel="${tab}"] .daily-tyre-kpi[data-category="Dozer"]`).should('not.exist');
        });
        cy.get('[data-kpi-category="Dozer"] .daily-au-average').should('have.length', 2);
        cy.get('[data-kpi-category="Dozer"]').should('contain', 'Average Availability').and('contain', 'Average Utilisation');
        cy.get('[data-panel="hours"]').should('contain', 'DOZER').find('svg').should('have.length.greaterThan', 1);
    });
    it('fits the average rows at desktop, tablet and mobile widths', () => {
        [1440, 1280, 768, 375].forEach(width => {
            cy.viewport(width, 950);
            ['hours', 'au'].forEach(tab => {
                cy.get(`.daily-dashboard-tab-button[data-tab="${tab}"]`).click();
                cy.get(`[data-panel="${tab}"] .daily-damage-kpi-row`).each(row => {
                    expect(row[0].scrollWidth).lte(row[0].clientWidth + 1);
                    expect(row.children('.frappe-card').length).oneOf([2, 3]);
                });
            });
        });
        cy.get('[data-kpi-category="Dozer"]').scrollIntoView();
        cy.screenshot('dozer-mobile-two-averages', {capture: 'viewport'});
        cy.viewport(1440, 950);
        cy.get('[data-kpi-category="ADT"]').scrollIntoView();
        cy.screenshot('adt-desktop-tyre-wheel-card', {capture: 'viewport'});
    });
});
