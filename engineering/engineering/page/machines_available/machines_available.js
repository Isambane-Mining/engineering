/* Standalone view of the source Machine Available vs Utilised tab.
 * Calculation and Excel APIs remain owned and permission-checked by is_production.
 */
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c =>
    ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
  function machineColour(available, utilised, verified) {
    if (!verified || !Number.isFinite(Number(available)) ||
        !Number.isFinite(Number(utilised)) ||
        available == null || utilised == null ||
        Number(available) <= 0 || Number(utilised) < 0)
      return 'neutral';

    const ratio = Number(utilised) / Number(available);

    if (ratio >= 0.80) return 'green';
    if (ratio >= 0.50) return 'yellow';
    if (ratio >= 0.20) return 'orange';
    return 'red';
  }

  function matchesUnavailableRange(total, available, selected) {
    if (selected == null || available == null) return false;
    if (!Number.isFinite(Number(total)) ||
        !Number.isFinite(Number(available)) ||
        !Number.isInteger(selected) || selected < 0 ||
        Number(total) <= 0) return false;

    const missing = Number(total) - Number(available);
    const epsilon = 1e-9;

    if (selected === 0) return Math.abs(missing) <= epsilon;

    return missing > selected - 1 + epsilon &&
           missing <= selected + epsilon;
  }

  function renderMachineMatrix(data, unavailableNumber = null) {
    let lastMonth = '';

    const metric = (value, cls, digits) =>
      Number.isFinite(Number(value)) && value != null && Number(value) >= 0
        ? `<span class="${cls}">${Number(value).toLocaleString('en-US',{maximumFractionDigits:digits})}</span>`
        : '—';

    const rows = data.rows.map((row, rowIndex) => {
      const divider = row.month_key !== lastMonth
        ? `<tr class="hpa-month-divider">
             <th colspan="27"><span>${escape(row.month)}</span></th>
           </tr>`
        : '';

      lastMonth = row.month_key;

      const cells = row.cells.map((cell, index) => {
        const verified = cell.completed && cell.has_record;
        const total = Number(row.fleet_total);
        const highlighted = verified &&
          matchesUnavailableRange(total, cell.available, unavailableNumber);
        const available = verified
          ? metric(cell.available,'hm-avail',2) : '—';
        const utilised = verified
          ? metric(cell.utilised,'hm-used',0) : '—';

        const value = available === '—' && utilised === '—'
          ? '—' : `${available} / ${utilised}`;

        const colour = machineColour(
          cell.available, cell.utilised, verified
        );

        return `<td class="hpa-cell hm-cell hm-${colour} ${
          index === 12 ? 'hpa-night-start' : ''
        } ${highlighted ? 'hm-unavailable-match' : ''}" tabindex="0" role="button" aria-haspopup="dialog" aria-expanded="false" data-machine-row="${rowIndex}" data-machine-hour="${index}" title="${verified
          ? 'Available / Utilised ADTs'
          : 'Unknown, missing or pending'}">${value}</td>`;
      }).join('');

      return `${divider}<tr>
        <th scope="row" class="hpa-sticky-date">${escape(row.date)}</th>
        <td class="hpa-sticky-day">${escape(row.day)}</td>
        <td class="hpa-sticky-month">${escape(row.month)}</td>
        ${cells}
      </tr>`;
    }).join('');

    return `<div class="hpa-scroll" tabindex="0" role="region"
      aria-label="Machine available versus utilised hourly table; scroll horizontally and vertically">
      <table class="hpa-table hm-matrix">
        <caption>Available / Utilised ADTs · ${escape(data.site)}</caption>
        <thead>
          <tr>
            <th rowspan="2" class="hpa-sticky-date">Date</th>
            <th rowspan="2" class="hpa-sticky-day">Day</th>
            <th rowspan="2" class="hpa-sticky-month">Month</th>
            <th colspan="12" class="hpa-shift-day">
              DAY SHIFT · 06:00–18:00
            </th>
            <th colspan="12" class="hpa-shift-night">
              NIGHT SHIFT · 18:00–06:00
            </th>
          </tr>
          <tr>
            ${data.hours.map((hour,index) =>
              `<th class="hpa-hour ${
                index === 12 ? 'hpa-night-start' : ''
              }">${escape(hour.replaceAll(':00',''))}</th>`
            ).join('')}
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>
    <section class="hpa-chart hm-chart" aria-label="Machine count legend">
      <div class="hm-legend">
        <strong>Machine Available vs Utilised</strong>
        <div><i class="hm-available-key"></i>
          <span>Available ADTs</span></div>
        <div><i class="hm-utilised-key"></i>
          <span>Utilised ADTs</span></div>
        <div><i class="hm-green-key"></i>
          <span>Green · 80–100% utilisation</span></div>
        <div><i class="hm-yellow-key"></i>
          <span>Yellow · 50–79%</span></div>
        <div><i class="hm-orange-key"></i>
          <span>Orange · 20–49%</span></div>
        <div><i class="hm-red-key"></i>
          <span>Red · below 20%</span></div>
        <div><i class="hm-unknown-key"></i>
          <span>White · Unknown / missing / pending</span></div>
      </div>
    </section>`;
  }

  const displayNumber = value => value == null ? '—' : Number(value).toLocaleString(undefined, {maximumFractionDigits: 2});
  const ratioColour = ratio => ratio == null ? 'neutral' : ratio >= .8 ? 'green' : ratio >= .5 ? 'yellow' : ratio >= .2 ? 'orange' : 'red';
  function hourMetrics(row, cell) {
    const verified = cell?.completed && cell.has_record;
    const valid = value => value != null && Number.isFinite(Number(value)) && Number(value) >= 0;
    const available = verified && valid(cell.available) ? Number(cell.available) : null;
    const utilised = verified && valid(cell.utilised) ? Number(cell.utilised) : null;
    const total = valid(row.fleet_total) ? Number(row.fleet_total) : null;
    return {available, utilised, unavailable: available != null && total != null ? Math.max(0, total - available) : null,
      total, colour: machineColour(available, utilised, verified)};
  }
  function aggregateRows(rows) {
    const metrics = rows.flatMap(row => row.cells.map(cell => hourMetrics(row, cell)));
    const average = key => {
      const values = metrics.map(m => m[key]).filter(n => n != null);
      return values.length ? values.reduce((a,b) => a+b,0) / values.length : null;
    };
    const fleets = rows.filter(row => row.fleet_total != null).map(row => Number(row.fleet_total)).filter(Number.isFinite);
    const observed = metrics.filter(m => m.available != null).length;
    return {available: average('available'), utilised: average('utilised'), unavailable: average('unavailable'),
      fleet: fleets.length ? fleets.reduce((a,b) => a+b,0)/fleets.length : null,
      variableFleet: new Set(fleets).size > 1, observed, hours: rows.length * 24};
  }
  function monthModel(data, month) {
    const [year, m] = month.split('-').map(Number);
    const count = new Date(Date.UTC(year, m, 0)).getUTCDate();
    const rows = data.rows.filter(row => row.date.startsWith(month + '-'));
    return {month, title: new Date(Date.UTC(year,m-1,1)).toLocaleDateString(undefined,{month:'long',year:'numeric',timeZone:'UTC'}),
      offset: (new Date(Date.UTC(year,m-1,1)).getUTCDay()+6)%7,
      kpis: aggregateRows(rows), days: Array.from({length:count},(_,i) => {
        const date = `${month}-${String(i+1).padStart(2,'0')}`;
        const index = data.rows.findIndex(row => row.date === date);
        const row = data.rows[index];
        const stats = row ? aggregateRows([row]) : null;
        return {date, day: i+1, index, row, stats,
          colour: stats?.available != null && stats.fleet > 0 ? ratioColour(stats.available/stats.fleet) : 'neutral'};
      })};
  }
  function viewLegend(kind = 'utilisation') {
    return `<div class="hm-view-legend" aria-label="${kind} colour legend">${[
      ['green','80–100%'],['yellow','50–79%'],['orange','20–49%'],['red','Below 20%'],['neutral','Unknown']
    ].map(([colour,label]) => `<span><i class="hm-${colour}"></i>${escape(label)}</span>`).join('')}</div>
      <p class="hm-view-note">Colours show ${kind}. Red outlines match the unavailable-machine filter.</p>`;
  }
  function renderCalendar(data, month, selectedDate, unavailable) {
    const model = monthModel(data, month), k = model.kpis;
    return `<section class="hm-calendar-view"><div class="hm-section-heading"><h2>Monthly Overview</h2><span>${escape(model.title)}</span></div>
      <div class="hm-kpis">${[['blue','Avg Available',k.available],['purple','Avg Utilised',k.utilised],
        ['red','Avg Unavailable',k.unavailable],['green',k.variableFleet?'Avg Fleet Size':'Fleet size',k.fleet]
      ].map(([colour,label,value]) => `<div class="hm-kpi ${colour}"><span>${label}</span><strong>${displayNumber(value)}</strong></div>`).join('')}</div>
      <p class="hm-view-note">Completed, recorded hours only · ${k.observed} of ${k.hours} selected hours have availability data.</p>
      <div class="hm-section-heading"><h2>Daily availability</h2><span>Tap a day</span></div>
      <div class="hm-cal-grid">${['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map(day=>`<div class="hm-weekday">${day}</div>`).join('')}
        ${'<div class="hm-cal-blank"></div>'.repeat(model.offset)}
        ${model.days.map(day => {
          const matched = day.row?.cells.some(cell => cell.completed && cell.has_record && matchesUnavailableRange(day.row.fleet_total,cell.available,unavailable));
          return `<button type="button" class="hm-cal-day hm-${day.colour} ${day.date===selectedDate?'selected':''} ${matched?'hm-unavailable-match':''}"
            data-view-date="${day.date}" ${day.index<0?'disabled':''} aria-label="${day.date}${day.index<0?' · Outside selected date range':` · Average available ${displayNumber(day.stats.available)}`}"
            title="${day.index<0?'Outside selected date range':'Open hourly breakdown'}">${day.day}${matched?'<i class="hm-cal-dot"></i>':''}</button>`;
        }).join('')}</div>${viewLegend('availability as a proportion of the historical MPP fleet')}
      <p class="hm-view-note">Unselected dates remain unknown. Tap a date to investigate its 24 operational hours.</p><button type="button" class="hm-view-export" title="Export the selected From Date–To Date range">↓ Export Excel</button></section>`;
  }
  function cellAttributes(index, hour, counts) {
    return `data-machine-row="${index}" data-machine-hour="${hour}" data-machine-counts="${escape(counts)}" aria-haspopup="dialog" aria-expanded="false"`;
  }
  function renderDailyView(data, index, unavailable) {
    const row = data.rows[index];
    if (!row) return '<p class="hm-view-note">Select a date in the reporting range.</p>';
    const stats = aggregateRows([row]);
    return `<section class="hm-day-view"><div class="hm-day-nav">
      <button type="button" class="hm-icon-button" data-day-step="-1" ${index===0?'disabled':''} aria-label="Previous day">‹</button>
      <strong>${escape(row.date)}</strong><button type="button" class="hm-icon-button" data-day-step="1" ${index===data.rows.length-1?'disabled':''} aria-label="Next day">›</button></div>
      <div class="hm-day-summary"><span>Fleet <b>${displayNumber(row.fleet_total)}</b></span><span>Avg unavailable <b class="hm-down-count">${displayNumber(stats.unavailable)}</b></span><span>Tap an hour</span></div>
      ${row.cells.map((cell,hour) => {
        const m = hourMetrics(row,cell), counts = `${displayNumber(m.available)} / ${displayNumber(m.utilised)}`;
        const match = cell.completed && cell.has_record && matchesUnavailableRange(row.fleet_total,cell.available,unavailable);
        return `${hour===0?'<h3 class="hm-shift-head">Day Shift · 06:00–18:00</h3>':hour===12?'<h3 class="hm-shift-head">Night Shift · 18:00–06:00</h3>':''}
          <button type="button" class="hm-cell hm-hour-row hm-${m.colour} ${match?'hm-unavailable-match':''}" ${cellAttributes(index,hour,counts)}>
            <span class="hm-hour-label">${escape(data.hours[hour])}</span><span class="hm-hour-count"><b class="hm-avail">${displayNumber(m.available)}</b> / <b class="hm-used">${displayNumber(m.utilised)}</b></span>
            <span class="hm-down-count" aria-label="Unavailable ${displayNumber(m.unavailable)}">${m.unavailable==null?'—':'−'+displayNumber(m.unavailable)}</span><span aria-hidden="true">›</span></button>`;
      }).join('')}<p class="hm-view-note">Available / Utilised · Unavailable. Unknown and unfinished hours show —. Operational day ends at 06:00 the next calendar day.</p>
      ${viewLegend()}</section>`;
  }
  function renderMonthlyHeatmap(data, month, unavailable) {
    const model = monthModel(data, month);
    return `<section class="hm-heatmap-view"><div class="hm-section-heading"><h2>Month × Hour</h2><span>Swipe horizontally →</span></div>
      <div class="hpa-scroll hm-heat-scroller" tabindex="0" role="region" aria-label="Monthly operational hour heatmap">
        <table class="hm-heat-table hm-matrix"><caption>${escape(model.title)} · ${escape(data.site)} · Available / Utilised</caption><thead>
          <tr><th rowspan="2" class="hm-date-head">Date</th><th colspan="12" class="hpa-shift-day">DAY SHIFT · 06:00–18:00</th><th colspan="12" class="hpa-shift-night">NIGHT SHIFT · 18:00–06:00</th></tr>
          <tr>${data.hours.map(hour=>`<th class="hm-hour-head">${escape(hour.split(/[–-]/)[0].replace(':00',''))}</th>`).join('')}</tr></thead><tbody>
          ${model.days.map(day=>`<tr><th class="hm-date-head" scope="row">${escape(day.date.slice(5))}</th>${Array.from({length:24},(_,hour)=>{
            if (!day.row) return '<td class="hm-heat-empty" aria-label="Outside selected date range">—</td>';
            const cell = day.row.cells[hour], m = hourMetrics(day.row,cell);
            const counts = `${displayNumber(m.available)} / ${displayNumber(m.utilised)}`;
            const match = cell.completed && cell.has_record && matchesUnavailableRange(day.row.fleet_total,cell.available,unavailable);
            return `<td><button type="button" class="hm-cell hm-heat hm-${m.colour} ${match?'hm-unavailable-match':''}" ${cellAttributes(day.index,hour,counts)}
              title="${day.date} · ${escape(data.hours[hour])} · ${counts}" aria-label="${day.date} ${escape(data.hours[hour])}, available / utilised ${counts}, unavailable ${displayNumber(m.unavailable)}">
              <span class="hm-heat-value">${counts}</span></button></td>`;
          }).join('')}</tr>`).join('')}</tbody></table></div>${viewLegend()}
      <div class="hm-heat-info">Tap a square for availability and breakdown details. <b>Red outline</b> matches your unavailable-machine filter.</div><button type="button" class="hm-view-export" title="Export the selected From Date–To Date range">↓ Export Excel</button></section>`;
  }

  function renderBreakdowns(data) {
    const minutes = value => Number(value).toLocaleString(undefined, {maximumFractionDigits: 2});
    if (!data.machines?.length) return '<p>No recorded breakdowns</p>';
    return data.machines.map(machine => `<section class="hm-breakdown-machine">
      <h4>${escape(machine.machine_number)}</h4>
      <p class="hm-breakdown-total">Downtime: <strong>${minutes(machine.downtime_minutes)} minutes</strong></p>
      ${machine.breakdowns.map(record => `<div class="hm-breakdown-record"><dl>
        <dt>Failure Classification</dt><dd>${escape(record.failure_classification || 'Not available')}</dd>
        <dt>Reason</dt><dd>${escape(record.description || 'Not available')}</dd>
        <dt>Breakdown start</dt><dd>${escape(record.breakdown_start_datetime)}</dd>
        <dt>Resolved</dt><dd>${escape(record.resolved_datetime || 'Still Open')}</dd>
        <dt>Hour overlap</dt><dd>${minutes(record.overlap_minutes)} minutes</dd>
      </dl></div>`).join('')}
    </section>`).join('');
  }

  class HourBreakdownPopup {
    constructor(panel, context) {
      this.panel = panel;
      this.context = context;
      this.token = 0;
      this.card = $('<aside class="hm-breakdown-popup" role="dialog" aria-label="Hourly breakdown details" hidden></aside>').appendTo(panel);
      panel.on('mouseenter focusin', '.hm-cell', event => {
        if (!this.pinned) this.show(event.currentTarget);
      });
      panel.on('mouseleave focusout', '.hm-cell', () => this.scheduleClose());
      panel.on('click', '.hm-cell', event => this.toggle(event.currentTarget));
      panel.on('keydown', '.hm-cell', event => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          this.toggle(event.currentTarget);
        }
      });
      this.card.on('mouseenter focusin', () => clearTimeout(this.closeTimer));
      this.card.on('mouseleave focusout', () => this.scheduleClose());
      this.card.on('click', '.hm-breakdown-close', () => this.close());
      this.dismiss = event => {
        if (this.anchor && !this.card[0].contains(event.target) && !this.anchor.contains(event.target) &&
            !(panel[0].contains(event.target) && event.target.closest('.hm-cell'))) this.close();
      };
      this.escapeKey = event => { if (event.key === 'Escape') this.close(); };
      this.reposition = event => {
        if (this.anchor && (!(event.target instanceof Node) || !this.card[0].contains(event.target))) this.position();
      };
      document.addEventListener('pointerdown', this.dismiss);
      document.addEventListener('keydown', this.escapeKey);
      window.addEventListener('scroll', this.reposition, true);
      window.addEventListener('resize', this.reposition);
      // Desk keeps pages mounted when navigating. Close the popup on route changes.
      this.routeChange = () => this.close();
      if (frappe.router?.on) frappe.router.on('change', this.routeChange);
    }

    scheduleClose() {
      clearTimeout(this.closeTimer);
      this.closeTimer = setTimeout(() => {
        if (!this.pinned && !this.card[0].matches(':hover') && !this.card[0].contains(document.activeElement)) this.close();
      }, 180);
    }

    close() {
      clearTimeout(this.closeTimer);
      clearTimeout(this.loadTimer);
      this.token++;
      if (this.anchor) this.anchor.setAttribute('aria-expanded', 'false');
      this.anchor = null;
      this.pinned = false;
      this.card.prop('hidden', true).empty();
    }

    toggle(cell) {
      if (this.anchor === cell && this.pinned) return this.close();
      this.show(cell, true);
    }

    show(cell, pin = false) {
      clearTimeout(this.closeTimer);
      if (this.anchor === cell) {
        this.pinned = this.pinned || pin;
        return;
      }
      this.close();
      const context = this.context();
      if (!context.data) return;
      const row = context.data.rows[Number(cell.dataset.machineRow)];
      const hour = Number(cell.dataset.machineHour);
      const value = row?.cells[hour];
      if (!value) return;
      this.anchor = cell;
      this.pinned = pin;
      cell.setAttribute('aria-expanded', 'true');
      const token = ++this.token;
      const counts = cell.dataset.machineCounts || cell.textContent.trim();
      const label = value.start && value.end
        ? `${value.start} – ${value.end}` : `${row.date} · ${context.data.hours[hour]}`;
      this.card.html(`<button type="button" class="hm-breakdown-close" aria-label="Close breakdown details">×</button>
        <h3>${escape(row.date)} · ${escape(context.data.hours[hour])}</h3>
        <p class="hm-breakdown-period">${escape(label)}</p><p class="hm-breakdown-counts">Available / Utilised: <strong>${escape(counts)}</strong></p>
        <div class="hm-breakdown-body" role="status">Loading breakdowns…</div>`).prop('hidden', false);
      this.position();
      // A short hover delay avoids queries for cells crossed while moving the pointer.
      this.loadTimer = setTimeout(async () => {
        try {
          const response = await frappe.call({
            method: 'engineering.engineering.page.machines_available.machines_available.get_hour_breakdowns',
            args: {site: context.data.site, date: row.date, hour, machine_scope: context.scope}
          });
          if (token !== this.token) return;
          this.card.find('.hm-breakdown-body').html(renderBreakdowns(response.message || {}));
        } catch (error) {
          if (token !== this.token) return;
          this.card.find('.hm-breakdown-body').text('Unable to load breakdown details. Check permissions and try again.');
        }
        if (token === this.token) this.position();
      }, pin ? 0 : 120);
    }

    position() {
      if (!this.anchor || !this.anchor.isConnected || !this.panel[0].getClientRects().length) return this.close();
      const rect = this.anchor.getBoundingClientRect();
      const table = (this.anchor.closest('.hpa-scroll') || this.anchor.closest('.hm-day-view')).getBoundingClientRect();
      if (rect.bottom <= Math.max(0, table.top) || rect.top >= Math.min(innerHeight, table.bottom) ||
          rect.right <= Math.max(0, table.left) || rect.left >= Math.min(innerWidth, table.right)) return this.close();
      const card = this.card[0];
      const gap = 10, margin = 12;
      this.card.css('maxHeight', '');
      if (innerWidth < 600 || this.anchor.matches('.hm-hour-row')) {
        const below = Math.max(0, innerHeight - rect.bottom - gap - margin);
        const above = Math.max(0, rect.top - gap - margin);
        const useBelow = below >= above;
        this.card.css('maxHeight', `${Math.min(innerHeight * 0.6, Math.max(above, below))}px`);
        const left = Math.max(margin, Math.min(rect.left, innerWidth - card.offsetWidth - margin));
        const top = useBelow ? rect.bottom + gap : rect.top - gap - card.offsetHeight;
        this.card.css({left: `${left}px`, top: `${Math.max(margin, top)}px`});
        return;
      }
      const width = card.offsetWidth, height = card.offsetHeight;
      let left = rect.right + gap;
      if (left + width > innerWidth - margin) left = rect.left - width - gap;
      if (left < margin) left = Math.max(margin, (innerWidth - width) / 2);
      let top = rect.top;
      if (innerHeight - table.bottom >= height + gap + margin) {
        // Use empty space under short tables before covering neighbouring hours.
        top = table.bottom + gap;
        left = Math.max(margin, Math.min(rect.left, innerWidth - width - margin));
      }
      top = Math.max(margin, Math.min(top, innerHeight - height - margin));
      this.card.css({left: `${left}px`, top: `${top}px`});
    }
  }

  function mountMachinesAvailable(wrapper) {
    const page = frappe.ui.make_app_page({parent: wrapper, title: 'Machines Available', single_column: true});
    page.main.html('<div class="machines-available-page"></div>');
    const panel = page.main.find('.machines-available-page');
      panel.html(`
        <div class="hpa-shell hm-shell">
          <div class="hpa-filters hm-filters">
            <div class="hm-site"></div>
            <div class="hm-from_date"></div>
            <div class="hm-to_date"></div>
            <div class="hm-scope-control">
              <label for="hm-scope-select">Machines</label>
              <select id="hm-scope-select" class="form-control hm-scope">
                <option value="all">All</option>
                <option value="production">Production Machines</option>
                <option value="spare">Spare Machines</option>
              </select>
            </div>
            <div class="hm-unavailable-control">
              <label for="hm-unavailable-select">Machine Number Unavailable</label>
              <select id="hm-unavailable-select" class="form-control hm-unavailable">
                <option value="">No highlight</option>
              </select>
            </div>
            <button type="button" class="btn btn-primary hm-refresh">
              Refresh
            </button>
            <button type="button" class="btn btn-default hm-export">
              Export Excel
            </button>
          </div>
          <div class="hm-status" role="status" aria-live="polite">
            Select a site and date range.
          </div>
          <div class="hm-view-controls" hidden>
            <label class="hm-month-control">Month<select class="form-control hm-month" aria-label="Reporting month"></select></label>
            <div class="hm-mode-nav" role="tablist" aria-label="Machines Available views">
              <button type="button" role="tab" id="hm-mode-calendar" data-view-mode="calendar" aria-controls="hm-view-panel" aria-selected="true">Month</button>
              <button type="button" role="tab" id="hm-mode-day" data-view-mode="day" aria-controls="hm-view-panel" aria-selected="false" tabindex="-1">Day</button>
              <button type="button" role="tab" id="hm-mode-heatmap" data-view-mode="heatmap" aria-controls="hm-view-panel" aria-selected="false" tabindex="-1">Heatmap</button>
            </div>
          </div>
          <div class="hm-content" id="hm-view-panel" role="tabpanel" aria-labelledby="hm-mode-calendar"></div>
        </div>`);

      let initializing = true;
      let requestToken = 0;
      let machineData = null;
      let mode = 'calendar';
      let selectedDate = null;
      let selectedMonth = null;

      const controls = {};
      const popup = new HourBreakdownPopup(panel, () => ({data: machineData, scope: panel.find('.hm-scope').val()}));

      const drawMachineData = () => {
        if (!machineData) return;
        const value = panel.find('.hm-unavailable').val();
        const number = value === '' ? null : Number(value);
        popup.close();
        const months = [...new Set(machineData.rows.map(row => row.date.slice(0,7)))];
        if (!months.includes(selectedMonth)) selectedMonth = months[0];
        if (!machineData.rows.some(row => row.date === selectedDate && row.date.startsWith(selectedMonth))) {
          selectedDate = machineData.rows.find(row => row.date.startsWith(selectedMonth)).date;
        }
        panel.find('.hm-month').html(months.map(month => `<option value="${month}">${escape(monthModel(machineData,month).title)}</option>`).join('')).val(selectedMonth);
        panel.find('.hm-view-controls').prop('hidden', false);
        panel.find('[data-view-mode]').each((_,button) => {
          const active = button.dataset.viewMode === mode;
          button.setAttribute('aria-selected',String(active));button.tabIndex=active?0:-1;
        });
        const content = mode === 'calendar' ? renderCalendar(machineData,selectedMonth,selectedDate,number)
          : mode === 'day' ? renderDailyView(machineData,machineData.rows.findIndex(row => row.date===selectedDate),number)
          : renderMonthlyHeatmap(machineData,selectedMonth,number);
        panel.find('.hm-content').attr('aria-labelledby','hm-mode-'+mode).html(content);
      };

      const refresh = async () => {
        if (initializing) return;

        const token = ++requestToken;
        const site = controls.site.get_value();
        const from_date = controls.from_date.get_value();
        const to_date = controls.to_date.get_value();
        const scope = panel.find('.hm-scope').val();

        const status = panel.find('.hm-status');
        const content = panel.find('.hm-content');

        popup.close();
        machineData = null;
        content.empty();
        panel.find('.hm-view-controls').prop('hidden', true);

        if (!site || !from_date || !to_date ||
            from_date > to_date) {
          status.text('Select a valid site and date range.');
          return;
        }

        status.text('Loading machine counts…');

        try {
          const response = await frappe.call({
            method:
              'is_production.production.page.hourly_productivity_analysis.hourly_productivity_analysis.get_analysis',
            args: {site,from_date,to_date,machine_scope:scope}
          });

          if (token !== requestToken) return;

          const data = response.message;

          if (data?.planning_error || data?.configuration_error) {
            const error = data.planning_error ||
              data.configuration_error;
            status.text(error.title || 'Configuration unavailable.');
            return;
          }

          if (!data?.rows?.length) {
            status.text('No data available for this period.');
            return;
          }

          machineData = data;
          const selector = panel.find('.hm-unavailable');
          const previous = selector.val();
          const maximum = Math.max(0, ...data.rows.map(
            row => Number(row.fleet_total) || 0
          ));
          selector.empty().append(
            $('<option>').val('').text('No highlight')
          );
          if (maximum > 0) {
            selector.append($('<option>').val('0').text('0 · Fully available'));
          }
          for (let n = 1; n <= maximum; n++) {
            selector.append(
              $('<option>').val(String(n)).text(`${n - 1}–${n}`)
            );
          }
          selector.val(previous && Number(previous) <= maximum ? previous : '');
          drawMachineData();
          status.empty();

        } catch (error) {
          if (token === requestToken) {
            status.text(
              'Unable to load machine data. Check permissions and MPP.'
            );
          }
        }
      };

      for (const [name,label,type,options] of [
        ['site','Site','Link','Location'],
        ['from_date','From Date','Date'],
        ['to_date','To Date','Date']
      ]) {
        controls[name] = frappe.ui.form.make_control({
          parent: panel.find('.hm-' + name),
          render_input: true,
          df: {
            fieldname: 'hm_' + name,
            label,
            fieldtype: type,
            options,
            reqd: 1,
            onchange: () => {
              refresh();
            }
          }
        });
      }


      panel.find('.hm-export').on('click', () => {
        const site = controls.site.get_value();
        const from_date = controls.from_date.get_value();
        const to_date = controls.to_date.get_value();
        const machine_scope = panel.find('.hm-scope').val();

        if (!site || !from_date || !to_date || from_date > to_date) {
          frappe.msgprint('Select valid site and dates.');
          return;
        }

        const unavailable_number = panel.find('.hm-unavailable').val();
        const params = new URLSearchParams({
          site, from_date, to_date, machine_scope, unavailable_number
        });

        window.location.href =
          '/api/method/is_production.production.page.hourly_productivity_analysis.hourly_productivity_analysis.export_machine_excel?' +
          params.toString();
      });

      const setMode = value => {
        if (!['calendar','day','heatmap'].includes(value)) return;
        mode = value;
        drawMachineData();
      };
      panel.on('click', '[data-view-mode]', event => setMode(event.currentTarget.dataset.viewMode));
      panel.on('keydown', '[data-view-mode]', event => {
        const modes = ['calendar','day','heatmap'];
        const index = modes.indexOf(mode);
        if (!['ArrowLeft','ArrowRight','Home','End'].includes(event.key)) return;
        event.preventDefault();
        const next = event.key === 'Home'?0:event.key === 'End'?2:(index+(event.key==='ArrowRight'?1:2))%3;
        setMode(modes[next]);panel.find('#hm-mode-'+modes[next]).trigger('focus');
      });
      panel.find('.hm-month').on('change', () => {selectedMonth=panel.find('.hm-month').val();drawMachineData();});
      panel.on('click','[data-view-date]',event => {
        selectedDate=event.currentTarget.dataset.viewDate;selectedMonth=selectedDate.slice(0,7);setMode('day');
      });
      panel.on('click keydown','.hm-heat',event => {
        if (event.type==='keydown' && !['Enter',' '].includes(event.key)) return;
        const row=machineData?.rows[Number(event.currentTarget.dataset.machineRow)];
        if (row) selectedDate=row.date;
      });
      panel.on('click','[data-day-step]',event => {
        if (!machineData) return;
        const index=machineData.rows.findIndex(row=>row.date===selectedDate)+Number(event.currentTarget.dataset.dayStep);
        if (!machineData.rows[index]) return;
        selectedDate=machineData.rows[index].date;selectedMonth=selectedDate.slice(0,7);drawMachineData();
      });
      panel.on('click','.hm-view-export',()=>panel.find('.hm-export').trigger('click'));
      panel.find('.hm-unavailable').on('change',drawMachineData);
      panel.find('.hm-refresh').on('click',refresh);
      panel.find('.hm-scope').on('change', refresh);

      const initialize = async () => {
        try {
          const response = await frappe.call({
            method: 'engineering.engineering.page.machines_available.machines_available.get_defaults'
          });
          const {from_date, to_date} = response.message;

          await controls.from_date.set_value(from_date);
          await controls.to_date.set_value(to_date);


          initializing = false;
          if (controls.site.get_value()) await refresh();

        } catch (error) {
          initializing = false;
          panel.find('.hm-status').text(
            'Select a site and date range.'
          );
        }
      };

      wrapper.machinesAvailable = {
        refresh,
        setMode,
        ready: null,
        site: controls.site,
        from_date: controls.from_date,
        to_date: controls.to_date
      };

      wrapper.machinesAvailable.ready = initialize();
      return wrapper.machinesAvailable;
  }


  if (typeof frappe !== 'undefined') frappe.pages['machines-available'].on_page_load = mountMachinesAvailable;
  if (typeof module !== 'undefined' && module.exports) module.exports = {renderMachineMatrix, matchesUnavailableRange, mountMachinesAvailable, renderBreakdowns, monthModel, renderCalendar, renderDailyView, renderMonthlyHeatmap};
})();
