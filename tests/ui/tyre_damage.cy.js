const instance = action => cy.get('.daily-availability-and-utilization-dashboard-wrapper').then(root => action(root[0].daily_availability_dashboard));
const setFilters = values => {
    instance(async page => {
        page.initializing = true;
        for (const [key, value] of Object.entries(values)) await page[key].set_value(value);
        page.initializing = false;
        page.load_dashboard();
    });
    cy.get('.daily-availability-and-utilization-dashboard-wrapper').should(root => expect(root[0].daily_availability_dashboard.loading, 'dashboard loaded').eq(false));
};
const expectCounts = (adt, selectedAsset = false) => ['hours', 'au'].forEach(panel => {
    cy.get(`[data-panel="${panel}"] .daily-tyre-kpi[data-category="ADT"]`).should('have.attr', 'data-count', String(adt));
    if (selectedAsset && panel === 'hours') cy.get(`[data-panel="${panel}"] .daily-tyre-kpi[data-category="Dozer"]`).should('not.exist');
    else cy.get(`[data-panel="${panel}"] .daily-tyre-kpi[data-category="Dozer"]`).should('have.attr', 'data-count', '0');
});

describe('Daily Engine tyre damage KPI on LAB', () => {
    beforeEach(() => {
        cy.setCookie('sid', Cypress.env('sid'), {domain: 'juan.isambane.co.za', secure: true, log: false});
        cy.viewport(1440, 1000);
        cy.visit('/app/daily-availability-and-utilization-dashboard', {onBeforeLoad: win => win.localStorage.clear()});
        cy.get('.daily-availability-and-utilization-dashboard-wrapper').should(root => expect(root[0].daily_availability_dashboard.initializing).eq(false));
        setFilters({location: 'Klipfontein', start_date: '2026-07-01', end_date: '2026-07-31'});
        expectCounts(0);
    });

    it('shows identical actual counts in both tabs with two large averages and a compact tyre card', () => {
        cy.viewport(1280, 950);
        ['hours', 'au'].forEach(tab => {
            cy.get(`.daily-dashboard-tab-button[data-tab="${tab}"]`).click();
            cy.get(`[data-panel="${tab}"] .daily-tyre-kpi`).should('have.length', 2);
            cy.get(`[data-panel="${tab}"] .daily-tyre-kpi[data-category="ADT"]`).should('be.visible').and('contain', 'Classified tyre damage breakdowns').and('contain', '0');
            cy.get(`[data-panel="${tab}"] .daily-tyre-kpi`).first().parent().then(row => {
                const cards = row.children('.frappe-card');
                expect(cards.length).eq(3);
                const first = cards[0].getBoundingClientRect(), last = cards[2].getBoundingClientRect();
                expect(last.width).lessThan(first.width);
                expect(Math.abs(first.height - last.height)).lte(1);
                expect(last.left).greaterThan(first.left);
            });
            cy.get(`[data-panel="${tab}"] .daily-tyre-kpi`).first().parent().scrollIntoView({offset: {top: -80, left: 0}});
            cy.screenshot(`tyre-kpi-${tab}-desktop`, {capture: 'viewport'});
        });
        cy.get('[data-panel="hours"] polyline').should('have.length.greaterThan', 0);
        cy.get('[data-panel="au"] .isd-category-average-legend').should('exist');
    });

    it('updates dates, historical site and the individual Asset filter in both tabs', () => {
        setFilters({hours_asset: 'IS587'});
        expectCounts(0, true);
        setFilters({end_date: '2026-07-15'});
        expectCounts(0, true);
        setFilters({hours_asset: '', location: 'Koppie', start_date: '2026-07-01', end_date: '2026-07-31'});
        expectCounts(0);
    });

    it('keeps all three KPI cards within desktop, tablet and mobile widths', () => {
        [1440, 1280, 768, 375].forEach(width => {
            cy.viewport(width, 950);
            ['hours', 'au'].forEach(tab => {
                cy.get(`.daily-dashboard-tab-button[data-tab="${tab}"]`).click();
                cy.get(`[data-panel="${tab}"] .daily-tyre-kpi`).first().parent().then(row => {
                    expect(row[0].scrollWidth).lte(row[0].clientWidth + 1);
                    const bounds = row[0].getBoundingClientRect();
                    row.children('.frappe-card').each((_, card) => expect(card.getBoundingClientRect().right).lte(bounds.right + 1));
                });
            });
        });
        cy.get('[data-panel="au"] .daily-damage-kpi-row').first().scrollIntoView();
        cy.screenshot('tyre-kpi-au-mobile', {capture: 'viewport'});
    });
});
