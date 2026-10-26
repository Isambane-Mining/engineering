const page = action => cy.get('.mr-page').then(root => {
    let element = root[0];
    while (element && !element.machineReliability) element = element.parentElement;
    expect(element, 'Machine Reliability page instance').to.exist;
    return action(element.machineReliability);
});
const filters = values => page(async instance => {
    instance.initializing = true;
    for (const [name, value] of Object.entries(values)) await instance.fields[name].set_value(value);
    instance.initializing = false;
    await instance.load();
});

describe('Machine Reliability on LAB', () => {
    beforeEach(() => {
        cy.setCookie('sid', Cypress.env('sid'), {domain: 'juan.isambane.co.za', secure: true, log: false});
        cy.viewport(1440, 1000);
        cy.visit('/app/reliability-engineering');
        cy.get('.mr-cards .mr-card').should('have.length', 6);
        filters({from_date: '2026-07-01', to_date: '2026-08-31', category: 'Brakes'});
        cy.get('.mr-marker.failure').should('have.length.greaterThan', 0);
    });

    it('shows one dashboard with timeline details and both scales', () => {
        cy.get('.mr-marker.failure').first().should('have.attr', 'title').and('include', 'Standing hours');
        cy.get('.mr-marker.failure').first().click();
        cy.get('.modal:visible').should('contain', 'Fleet Number').and('contain', 'Repair description').and('contain', 'Machine hours');
        cy.get('.modal:visible a').should('have.attr', 'href').and('include', 'plant-breakdown-or-maintenance');
        // Bootstrap ignores hide() during the opening transition.
        cy.wait(400);
        cy.get('.modal:visible .btn-modal-close').click();
        cy.get('.modal:visible').should('not.exist');
        cy.get('[data-mode="hours"]').click();
        cy.get('.mr-timeline-note').should('contain', 'never combined');
        cy.get('.mr-unpositioned').should('contain', 'without machine-hour readings');
        cy.get('.mr-unpositioned summary').click();
        cy.get('.mr-unpositioned [data-record]').first().click();
        cy.get('.modal:visible').should('contain', 'Fleet Number').and('contain', 'Not recorded');
        cy.wait(400);
        cy.get('.modal:visible .btn-modal-close').click();
        cy.get('.modal:visible').should('not.exist');
        cy.get('[data-mode="date"]').click();
        cy.get('.mr-header').scrollIntoView();
        cy.screenshot('machine-reliability-overview', {capture: 'viewport', scale: true});
    });

    it('filters historical sites, categories, fleet and additional words consistently', () => {
        filters({site: 'Koppie', asset_category: 'ADT', additional_keywords: 'starter'});
        page(instance => {
            expect(instance.data.keywords).include('starter');
            expect(instance.data.timeline.length).greaterThan(0);
            expect(instance.data.timeline.every(x => x.site === 'Koppie')).eq(true);
            const fleet = instance.data.timeline.find(row => row.is_failure).fleet;
            return instance.fields.fleet.set_value(fleet);
        });
        cy.get('.mr-status').should('not.contain', 'Loading');
        page(instance => {
            const fleet = instance.fields.fleet.get_value();
            expect(instance.data.timeline.every(x => x.fleet === fleet)).eq(true);
            expect(instance.data.tables.history.rows.length).greaterThan(0);
            [instance.data.top_all, instance.data.top_problem, instance.data.tables.history.rows, instance.data.tables.legal.rows].forEach(rows => expect(rows.every(x => x.fleet === fleet && x.site === 'Koppie')).eq(true));
        });
        page(instance => instance.fields.asset_category.set_value('Excavator'));
        page(instance => expect(instance.fields.fleet.get_value()).eq(''));
    });

    it('fits desktop, tablet and mobile without page overflow', () => {
        [1440, 768, 375].forEach(width => {
            cy.viewport(width, 950);
            cy.get('.mr-shell').then(root => expect(root[0].scrollWidth).lte(root[0].clientWidth + 1));
            cy.document().then(doc => expect(doc.documentElement.scrollWidth, 'document width').lte(doc.documentElement.clientWidth + 1));
            cy.get('.mr-filters').then(root => expect(root[0].scrollWidth).lte(root[0].clientWidth + 1));
        });
        cy.screenshot('machine-reliability-mobile', {capture: 'viewport'});
    });

    it('shows a genuine empty period and clears results for invalid dates', () => {
        filters({from_date: '2020-01-01', to_date: '2020-01-31'});
        cy.get('.mr-timeline').should('contain', 'No events');
        page(instance => expect(instance.data.summary.problem_records).eq(0));
        filters({from_date: '2026-08-31', to_date: '2026-08-01'});
        cy.get('.mr-status').should('contain', 'valid date range');
        cy.get('.mr-card').should('not.exist');
    });
    it('keeps IS545 calculations, reading checks and shared filter results unchanged', () => {
        cy.get('.mr-page [role="tablist"],.mr-page [role="tab"],.mr-tabs,#mr-details,#mr-frequency').should('not.exist');
        filters({from_date: '2025-10-01', to_date: '2026-08-31', fleet: 'IS545', category: 'Brakes'});
        page(instance => {
            expect(instance.data.summary.direct_failures).eq(7);
            expect(instance.data.summary.average_failure_gap).eq(32.25);
        });
        cy.get('.mr-cards').should('contain', '32.25 h');
        cy.get('.mr-quality').should('contain', 'excluded hour gaps');
        filters({from_date: '2026-06-01', to_date: '2026-06-30'});
        cy.get('.mr-cards').should('contain', '22 h');
        cy.get('#mr-overview').should('be.visible').and('have.attr', 'aria-busy', 'false');
    });

    it('preserves independent dashboards and legacy entry routing', () => {
        let problemChart;
        cy.get('.re-combined-shell [role="tablist"]').should('have.length', 1);
        cy.get('.re-combined-shell [role="tab"]').should('have.length', 3);
        cy.get('.re-combined-heading').should('contain', 'Reliability Engineering');
        cy.get('.re-combined-heading').then(header => cy.get('.re-combined-tabs').then(tabs => {
            expect(header[0].getBoundingClientRect().bottom).lte(tabs[0].getBoundingClientRect().top);
        }));
        cy.get('#re-combined-machine-tab').should('have.attr', 'aria-selected', 'true');
        cy.get('.re-combined-tabs [role="tab"]').then(tabs => expect([...tabs].map(x => x.textContent)).deep.eq(['Machine Reliability', 'Breakdown Analysis', 'Problem Machines']));
        filters({from_date: '2026-05-30', to_date: '2026-09-12', fleet: 'IS545', category: 'Brakes', additional_keywords: 'retarder'});
        cy.get('[data-mode="hours"]').click();
        cy.get('#re-combined-analysis-tab').click();
        cy.get('.re-analysis-tab').should('be.visible');
        cy.get('.reliability-engineering-page').should(root => expect(root[0].reliabilityEngineering.data).to.exist);
        cy.get('.reliability-engineering-page').then(root => {
            const analysis = root[0].reliabilityEngineering;
            analysis.initializing = true;
            return Promise.resolve().then(async () => {
                await analysis.from.set_value('2026-07-01');
                await analysis.to.set_value('2026-08-31');
                await analysis.location.set_value('Koppie');
                await analysis.asset.set_value('EX015');
                analysis.initializing = false;
                await analysis.load();
            });
        });
        cy.get('.re-table tbody tr').should('have.length.greaterThan', 0);
        cy.get('.re-chart svg').should('exist');
        cy.get('#re-combined-machine-tab').click();
        page(instance => {
            expect(instance.fields.fleet.get_value()).eq('IS545');
            expect(instance.fields.additional_keywords.get_value()).eq('retarder');
            expect(instance.fields.from_date.get_value()).eq('2026-05-30');
            expect(instance.mode).eq('hours');
            expect(instance.data.summary.average_failure_gap).eq(32.25);
        });
        cy.get('#re-combined-analysis-tab').click();
        cy.get('.reliability-engineering-page').then(root => expect(root[0].reliabilityEngineering.location.get_value()).eq('Koppie'));
        cy.get('#re-combined-problems-tab').click();
        cy.get('.reliability-engineering-page').then(async root => {
            const problems = root[0].reliabilityEngineering.problems;
            await problems.ready;
            problems.initializing = true;
            await problems.from.set_value('2026-07-01');
            await problems.to.set_value('2026-08-31');
            await problems.site.set_value('Koppie');
            problems.initializing = false;
            await problems.load();
        });
        cy.get('.pm-table tbody tr').should('have.length.greaterThan', 0);
        cy.get('.reliability-engineering-page').then(root => { problemChart = root[0].reliabilityEngineering.problems.frequencyChart; });
        cy.get('.re-combined-shell [role="tablist"]').should('have.length', 1);
        cy.get('.re-combined-shell [role="tab"]').should('have.length', 3);
        cy.get('#re-combined-machine-tab').click();
        cy.get('#re-combined-analysis-tab').click();
        cy.get('.re-analysis-tab').should('be.visible');
        cy.get('.reliability-engineering-page').then(root => {
            expect(root[0].reliabilityEngineering.asset.get_value()).eq('EX015');
            expect(root[0].reliabilityEngineering.location.get_value()).eq('Koppie');
        });
        cy.get('#re-combined-problems-tab').click();
        cy.get('.re-problems-tab').should('be.visible');
        cy.get('.reliability-engineering-page').then(root => {
            const problems = root[0].reliabilityEngineering.problems;
            expect(problems.site.get_value()).eq('Koppie');
            expect(problems.from.get_value()).eq('2026-07-01');
            expect(problems.frequencyChart, 'chart retained across tab switches').eq(problemChart);
        });
        cy.window().then(win => win.frappe.set_route('machine-reliability'));
        cy.location('pathname').should('match', /reliability-engineering$/);
        cy.get('#re-combined-machine-tab').should('have.attr', 'aria-selected', 'true');
        page(instance => expect(instance.fields.fleet.get_value()).eq('IS545'));
        [1440, 1280, 768, 375].forEach(width => {
            cy.viewport(width, 950);
            cy.document().then(doc => expect(doc.documentElement.scrollWidth).lte(doc.documentElement.clientWidth + 1));
            ['analysis', 'problems'].forEach(name => {
                cy.get(`#re-combined-${name}-tab`).click();
                if (name === 'problems') cy.get('.pm-frequency svg .bar').first().should(bar => {
                    expect(bar[0].getBBox().width, 'visible frequency bar width').greaterThan(0);
                    expect(bar[0].getBBox().height, 'visible frequency bar height').greaterThan(0);
                });
                cy.get('.re-combined-tabs').then(tabs => expect(tabs[0].scrollWidth).lte(tabs[0].clientWidth + 1));
                cy.document().then(doc => expect(doc.documentElement.scrollWidth).lte(doc.documentElement.clientWidth + 1));
            });
            cy.get('#re-combined-machine-tab').click();
        });
        cy.viewport(1280, 950);
        cy.get('.re-combined-tabs').scrollIntoView();
        cy.screenshot('combined-machine-desktop', {capture: 'viewport'});
        cy.get('#re-combined-analysis-tab').click();
        cy.get('.re-combined-tabs').scrollIntoView();
        cy.screenshot('combined-analysis-desktop', {capture: 'viewport'});
        cy.viewport(375, 950);
        cy.screenshot('combined-analysis-mobile', {capture: 'viewport'});
    });

    it('moves keyboard focus through all three main tabs', () => {
        cy.get('#re-combined-machine-tab').focus().type('{rightarrow}');
        cy.get('#re-combined-analysis-tab').should('be.focused').and('have.attr', 'aria-selected', 'true');
        cy.get('#re-combined-analysis-tab').type('{rightarrow}');
        cy.get('#re-combined-problems-tab').should('be.focused').and('have.attr', 'aria-selected', 'true');
        cy.get('#re-combined-problems-tab').type('{rightarrow}');
        cy.get('#re-combined-machine-tab').should('be.focused');
        cy.get('#re-combined-machine-tab').type('{leftarrow}');
        cy.get('#re-combined-problems-tab').should('be.focused');
        cy.get('#re-combined-problems-tab').type('{home}');
        cy.get('#re-combined-machine-tab').should('be.focused');
        cy.get('#re-combined-machine-tab').type('{end}');
        cy.get('#re-combined-problems-tab').should('be.focused');
        cy.get('.re-combined-shell [role="tabpanel"]:visible').should('have.length', 1);
    });
});


describe('Combined report access isolation', () => {
    it('keeps the Machine Reliability page gate without blocking the other reports', () => {
        cy.setCookie('sid', Cypress.env('sid'), {domain: 'juan.isambane.co.za', secure: true, log: false});
        cy.intercept('**/api/method/frappe.desk.desk_page.getpage*', request => {
            const name = typeof request.body === 'string' ? new URLSearchParams(request.body).get('name') : request.body?.name;
            if (name === 'machine-reliability') request.reply({statusCode: 403, body: {exc_type: 'PermissionError'}});
        });
        cy.intercept('**/api/method/engineering.engineering.page.machine_reliability.machine_reliability.get_options*').as('machineOptions');
        cy.visit('/app/reliability-engineering');
        cy.get('.re-machine-host').should('contain', 'Unable to open Machine Reliability');
        cy.get('@machineOptions.all').should('have.length', 0);
        cy.get('.modal:visible').should('exist');
        cy.wait(400);
        cy.get('.modal:visible .btn-modal-close').click();
        cy.get('.modal:visible').should('not.exist');
        cy.get('#re-combined-analysis-tab').click();
        cy.get('.re-analysis-tab').should('be.visible');
        cy.get('.re-filters').should('be.visible');
    });
});
