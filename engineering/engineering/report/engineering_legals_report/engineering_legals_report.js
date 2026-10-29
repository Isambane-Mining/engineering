const EL_DOC_CACHE = {}; // key: site|section|fleet -> rows
frappe.query_reports["Engineering Legals Report"] = {
  filters: [
    {
      fieldname: "site",
      label: "Site",
      fieldtype: "Link",
      options: "Location"
    },
    {
      fieldname: "section",
      label: "Section",
      fieldtype: "Link",
      options: "Engineering Legals Sections"
    },
    {
      fieldname: "asset",
      label: "Asset",
      fieldtype: "Link",
      options: "Asset"
    },
    {
      fieldname: "from_expiry_date",
      label: "Start Date",
      fieldtype: "Date"
    },
    {
      fieldname: "to_expiry_date",
      label: "End Date",
      fieldtype: "Date"
    },
    // internal click-driven filters
    {
      fieldname: "view",
      label: "View",
      fieldtype: "Select",
      options: "Summary\nAssets",
      default: "Summary",
      hidden: 1
    },
    {
      fieldname: "bucket",
      label: "Bucket",
      fieldtype: "Select",
      options: "\noverdue\nd0_7\nd8_14\nd15_21\nd22_28",
      hidden: 1
    }
  ],

  onload(report) {
    bind_doc_history_lazy_loader(report);

    report.page.add_inner_button("Back to Summary", () => {
      report.set_filter_value("view", "Summary");
      report.set_filter_value("bucket", "");
      frappe.query_report.refresh();
      $(report.page.wrapper).find("#el-drilldown").remove();
    });





    report.page.add_inner_button("Export Filtered Documents", () => {
      const params = new URLSearchParams({
        site: frappe.query_report.get_filter_value("site") || "",
        section: frappe.query_report.get_filter_value("section") || "",
        asset: frappe.query_report.get_filter_value("asset") || "",
        from_expiry_date: frappe.query_report.get_filter_value("from_expiry_date") || "",
        to_expiry_date: frappe.query_report.get_filter_value("to_expiry_date") || ""
      });

      window.location.href = `/api/method/engineering.engineering.report.engineering_legals_report.fetch_second_table.export_filtered_documents?${params.toString()}`;
    });





    $(report.page.wrapper)
      .off("click.el_buckets")
      .on("click.el_buckets", ".el-bucket-pill", function () {
        const section = $(this).attr("data-section") || "";
        const bucket = $(this).attr("data-bucket") || "";

        const site = frappe.query_report.get_filter_value("site") || "";
        const asset = frappe.query_report.get_filter_value("asset") || "";
        const from_expiry_date = frappe.query_report.get_filter_value("from_expiry_date") || "";
        const to_expiry_date = frappe.query_report.get_filter_value("to_expiry_date") || "";

        frappe.call({
          method: "engineering.engineering.report.engineering_legals_report.fetch_second_table.get_assets",
          args: { site, section, asset, bucket, from_expiry_date, to_expiry_date },
          callback: (r) => {
            const rows = (r && r.message && r.message.rows) ? r.message.rows : [];
            render_drilldown(report, { site, section, asset, bucket, rows });
          }
        });
      });

    $(report.page.wrapper)
      .off("click.el_category")
      .on("click.el_category", ".el-cat-bubble", function () {
        const category = $(this).attr("data-category") || "";
        const site = frappe.query_report.get_filter_value("site") || "";
        open_category_summary(report, { site, category, section: "" });
      });
  },






  after_refresh(report) {
    const view = frappe.query_report.get_filter_value("view") || "Summary";
    if (view !== "Summary") return;

    // let datatable finish painting, then inject UI
    setTimeout(() => {
      ensure_summary_title(report);
      ensure_clean_summary_grid(report);
      refresh_dashboard(report);

      const site = frappe.query_report.get_filter_value("site") || "";
      const asset = frappe.query_report.get_filter_value("asset") || "";
      render_audit_summary(report, { site, asset });

      // NEW: collapsible tree at bottom
      const section = frappe.query_report.get_filter_value("section") || "";
      render_doc_history_tree(report, { site, section, asset });
    }, 0);
  },

  formatter(value, row, column, data, default_formatter) {
    value = default_formatter(value, row, column, data);

    // Only format summary buckets (numbers) as coloured clickable pills
    const view = frappe.query_report.get_filter_value("view") || "Summary";
    if (view !== "Summary") return value;

const bucketCols = {
  overdue: { bg: "#f6b3b3", fg: "#6b1b1b" }, // soft red
  d0_7:    { bg: "#f6c59f", fg: "#6b3a00" }, // soft orange
  d8_14:   { bg: "#f5e29a", fg: "#5c4a00" }, // soft yellow
  d15_21:  { bg: "#b8d6f6", fg: "#0b5394" }, // NOW blue
  d22_28:  { bg: "#bfe5c6", fg: "#1f5e2b" }  // NOW green
};


    const field = column.fieldname;
    if (!bucketCols[field]) return value;

    const n = (data && typeof data[field] !== "undefined") ? data[field] : 0;
const style =
  `display:inline-block; min-width:34px; text-align:center; ` +
  `padding:0; width:34px; height:34px; line-height:34px; border-radius:10px; cursor:pointer; ` +
  `background:${bucketCols[field].bg}; color:${bucketCols[field].fg}; ` +
  `border:1px solid rgba(0,0,0,0.10); font-weight:800;`;

    // clickable drilldown (no inline onclick - blocked by sanitizer)
    const section = (data && data.section) ? data.section : "";
    return `<span
      class="el-bucket-pill"
      data-section="${frappe.utils.escape_html(section)}"
      data-bucket="${field}"
      style="${style}"
      title="Click to open assets"
    >${n}</span>`;
  }
};


function ensure_summary_title(report) {
  const main = $(report.page.main);
  const reportWrapper = main.find(".report-wrapper").first();
  if (!reportWrapper.length) return;

  // stable top area ABOVE the datatable wrapper
  let top = main.find("#el-top-area");
  if (!top.length) {
    reportWrapper.before(`<div id="el-top-area" style="margin:6px 0 10px;"></div>`);
    top = main.find("#el-top-area");
  }

  // Total Fleet heading + bubbles (top)
  if (!top.find("#el-dashboard-title").length) {
    top.append(`
      <div id="el-dashboard-title" style="text-align:center; font-weight:900; font-size:14px; margin:0 0 8px;">
        Total Fleet
      </div>
    `);
  }
  if (!top.find("#el-dashboard").length) {
    top.append(`<div id="el-dashboard" style="display:flex; gap:10px; flex-wrap:wrap; margin:0 0 14px;"></div>`);
  }

  // SUMMARY centered
  if (!top.find("#el-summary-title").length) {
    top.append(`
      <div id="el-summary-title" style="text-align:center; margin:6px 0 10px; font-weight:900; font-size:14px;">
        SUMMARY
      </div>
    `);
  }

  // Legend UNDER SUMMARY, ABOVE table (dot size doubled)
  if (!top.find("#el-legend").length) {
    top.append(`
<div id="el-legend" style="display:flex; justify-content:center; gap:16px; flex-wrap:wrap; align-items:center; margin:0 0 10px; font-size:12px;">
  <span><span style="display:inline-block;width:20px;height:20px;border-radius:50%;background:#f6b3b3;border:1px solid rgba(0,0,0,.12);margin-right:6px;vertical-align:middle;"></span><b>Overdue</b></span>
  <span><span style="display:inline-block;width:20px;height:20px;border-radius:50%;background:#f6c59f;border:1px solid rgba(0,0,0,.12);margin-right:6px;vertical-align:middle;"></span><b>0–7 days</b></span>
  <span><span style="display:inline-block;width:20px;height:20px;border-radius:50%;background:#f5e29a;border:1px solid rgba(0,0,0,.12);margin-right:6px;vertical-align:middle;"></span><b>8–14 days</b></span>
<span><span style="display:inline-block;width:20px;height:20px;border-radius:50%;background:#b8d6f6;border:1px solid rgba(0,0,0,.12);margin-right:6px;vertical-align:middle;"></span><b>15–21 days</b></span>
<span><span style="display:inline-block;width:20px;height:20px;border-radius:50%;background:#bfe5c6;border:1px solid rgba(0,0,0,.12);margin-right:6px;vertical-align:middle;"></span><b>22–28 days</b></span>
</div>
    `);
  }
}



function ensure_clean_summary_grid(report) {
  const wrap = $(report.page.wrapper);
  if (wrap.find("#el-summary-style").length) return;

  wrap.append(`
    <style id="el-summary-style">
          /* Make first (Section) column bold */
      .report-wrapper .datatable .dt-cell--col-1 .dt-cell__content {
        font-weight: 900 !important;
      }
      /* Hide row index / row header */
      .report-wrapper .dt-row-header,
      .report-wrapper .dt-cell--row-header,
      .report-wrapper .datatable .dt-row-header,
      .report-wrapper .datatable .dt-cell--row-header {
        display: none !important;
      }


      /* Center the SUMMARY datatable block under the legend */
      .report-wrapper .datatable {
        margin-left: auto !important;
        margin-right: auto !important;
      }

      /* Remove any left padding that makes it look offset */
      .report-wrapper .datatable .dt-scrollable,
      .report-wrapper .datatable .dt-body,
      .report-wrapper .datatable .dt-header {
        margin-left: auto !important;
        margin-right: auto !important;
      }

      /* Make the internal table size to content, so centering is accurate */
      .report-wrapper .datatable .dt-table {
        width: auto !important;
      }     




      /* Layout: let top area + report wrapper span full width, but center content */
      #el-top-area,
      .report-wrapper {
        max-width: 1200px !important;
        margin-left: auto !important;
        margin-right: auto !important;
      }

      /* Center the Total Fleet title */
      #el-dashboard-title { text-align: center !important; width: 100% !important; }

      /* Make bubbles use full available width and center them */
      #el-dashboard {
        width: 100% !important;
        justify-content: center !important;
      }

            /* Center everything in the report area */
      #el-top-area { max-width: 1100px; margin-left: auto; margin-right: auto; }
      .report-wrapper { max-width: 1100px; margin-left: auto !important; margin-right: auto !important; }

      /* Center the summary datatable itself */
            .report-wrapper .datatable {
        margin-left: auto !important;
        margin-right: auto !important;
        width: auto !important;
      }

      /* Center drilldown block too */
      #el-drilldown { max-width: 1100px; margin-left: auto; margin-right: auto; }

      /* Hide checkbox/select first column */
      .report-wrapper .dt-cell--col-0,
      .report-wrapper .dt-header .dt-cell--col-0 {
        display: none !important;
      }

      /* Hide column filter row under headers */
      .report-wrapper .dt-row-filter,
      .report-wrapper .datatable .dt-row-filter,
      .report-wrapper .dt-filter,
      .report-wrapper .datatable .dt-filter {
        display: none !important;
      }

      /* Remove grid lines */
      .report-wrapper .datatable .dt-cell,
      .report-wrapper .datatable .dt-header {
        border: none !important;
      }

      /* Don’t cut cell text */
      .report-wrapper .datatable .dt-cell__content {
        overflow: visible !important;
        text-overflow: clip !important;
        white-space: nowrap !important;
      }

      /* Remove the “For comparison...” hint line */
      .report-wrapper .datatable .dt-scrollable__hint,
      .report-wrapper .datatable .dt-help,
      .report-wrapper .datatable .dt-ellipsis,
      .report-wrapper .datatable + .text-muted {
        display: none !important;
      }
    </style>
  `);

  // Extra safety: remove any element containing the hint text
  setTimeout(() => {
    wrap.find("*").filter(function () {
      return $(this).text().trim().startsWith("For comparison, use");
    }).remove();
  }, 0);
}

function refresh_dashboard(report) {
  const site = frappe.query_report.get_filter_value("site") || "";

  frappe.call({
    method: "engineering.engineering.report.engineering_legals_report.fetch_second_table.get_asset_category_counts",
    args: { site },
    callback: (r) => {
      const rows = (r && r.message) ? r.message : [];
      render_dashboard(report, rows, site);
    }
  });
}

function render_dashboard(report, rows, site) {
  const wrap = $(report.page.wrapper);
  const dash = wrap.find("#el-dashboard");

  if (!rows.length) {
    dash.html(`<div style="opacity:.7;">No assets found for Site=${frappe.utils.escape_html(site || "All")}</div>`);
    return;
  }

  dash.html(rows.map(x => {
    const rawCat = x.category || "Unknown";
    const cat = frappe.utils.escape_html(rawCat);
    const cnt = frappe.utils.escape_html(String(x.count ?? 0));

    const w = Math.min(260, Math.max(140, (rawCat.length * 8) + 60));

    return `
      <div
        class="el-cat-bubble"
        data-category="${frappe.utils.escape_html(rawCat)}"
        title="Click to view category summary"
        style="
          width:${w}px;
          padding:10px 12px;
          border-radius:999px;
          border:2px solid #118DFF;
          box-shadow:0 1px 2px rgba(0,0,0,0.04);
          background:#fff;
          text-align:center;
          color:#262A76;
          font-weight:900;
          cursor:pointer;
        "
      >
        <div style="font-size:12px; font-weight:900; margin-bottom:3px; color:#262A76;">${cat}</div>
        <div style="font-size:20px; font-weight:900; line-height:1; color:#262A76;">${cnt}</div>
      </div>
    `;
  }).join(""));
}

function open_category_summary(report, ctx) {
  const { site, category, section } = ctx;

  const from_expiry_date = frappe.query_report.get_filter_value("from_expiry_date") || "";
  const to_expiry_date = frappe.query_report.get_filter_value("to_expiry_date") || "";

  frappe.call({
    method: "engineering.engineering.report.engineering_legals_report.fetch_second_table.get_category_summary",
    args: {
      site,
      asset_category: category,
      section,
      from_expiry_date,
      to_expiry_date
    },
    callback: (r) => {
      const payload = (r && r.message) ? r.message : {};
      render_category_summary(report, {
        site,
        category,
        section,
        rows: payload.rows || [],
        sections: payload.sections || []
      });
    }
  });
}

function render_category_summary(report, ctx) {
  const { site, category, section, rows } = ctx;

  const wrap = $(report.page.wrapper);
  wrap.find("#el-drilldown").remove();

  const esc = frappe.utils.escape_html;

  const allSections = [
    "Brake Test",
    "Fire Suppression",
    "FRCS",
    "Lifting Equipment",
    "Machine Service Records",
    "NDT",
    "PDS",
    "Service Schedule",
    "Tyre Inspection Report",
    "Wearcheck",
    "Illumination Baseline"
  ];

  const options = [
    `<option value="">All</option>`,
    ...allSections.map(sec => `
      <option value="${esc(sec)}" ${sec === section ? "selected" : ""}>${esc(sec)}</option>
    `)
  ].join("");

  const tableRows = (rows || []).map(r => {
    const recordHref = r.record_url || `/app/engineering-legals/${encodeURIComponent(r.name || "")}`;
    const attachmentHref = (r.attach_paper || "").trim() ? encodeURI(r.attach_paper) : "";

    return `
      <tr>
        <td>
          <a href="${recordHref}" target="_blank" rel="noopener noreferrer">
            ${esc(r.fleet_number || "")}
          </a>
        </td>
        <td>${esc(r.section || "")}</td>
        <td>${esc(r.start_date ? String(r.start_date) : "")}</td>
        <td>${esc(r.expiry_date ? String(r.expiry_date) : "")}</td>
        <td>${esc(r.status || "")}</td>
        <td>
          ${attachmentHref
            ? `<a href="${attachmentHref}" target="_blank" rel="noopener noreferrer">Open</a>`
            : `<span style="opacity:.5;">No File</span>`}
        </td>
      </tr>
    `;
  }).join("");

  const html = `
    <div id="el-drilldown" style="margin-top:14px; padding:12px; border:1px solid rgba(0,0,0,0.08); border-radius:10px;">
      <div style="display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:12px; flex-wrap:wrap;">
        <div style="font-weight:900;">
          ${esc(category || "Category")} Summary
          <span style="opacity:.65;">(${esc(String((rows || []).length))} records)</span>
        </div>
        <button class="btn btn-sm btn-default" id="el-drilldown-close">Close</button>
      </div>

      <div style="display:flex; gap:12px; align-items:end; flex-wrap:wrap; margin-bottom:12px;">
        <div>
          <div style="font-size:12px; font-weight:800; margin-bottom:4px;">Section Filter</div>
          <select id="el-category-section-filter" class="form-control" style="min-width:260px;">
            ${options}
          </select>
        </div>
      </div>

      <div style="overflow:auto;">
        <table class="table table-bordered" style="margin:0;">
          <thead>
            <tr>
              <th>Fleet Number</th>
              <th>Section</th>
              <th>Start Date</th>
              <th>Expiry Date</th>
              <th>Status</th>
              <th>Document</th>
            </tr>
          </thead>
          <tbody>
            ${tableRows || `<tr><td colspan="6" style="text-align:center; padding:14px;">No records found</td></tr>`}
          </tbody>
        </table>
      </div>
    </div>
  `;

  wrap.find(".report-wrapper").append(html);

  wrap.find("#el-drilldown-close").on("click", () => {
    wrap.find("#el-drilldown").remove();
  });

  wrap.find("#el-category-section-filter").on("change", function () {
    open_category_summary(report, {
      site,
      category,
      section: $(this).val() || ""
    });
  });
}



function render_drilldown(report, ctx) {
  const { site, section, asset, bucket, rows } = ctx;

  const wrap = $(report.page.wrapper);
  wrap.find("#el-drilldown").remove();

  const title = `Assets due: Site=${site || "All"}, Section=${section || "All"}, Asset=${asset || "All"}, Bucket=${bucket}`;

  const tableRows = rows.map(r => `
    <tr>
      <td>${frappe.utils.escape_html(r.asset || "")}</td>
      <td>${frappe.utils.escape_html(r.site || "")}</td>
	<td>${frappe.utils.escape_html(r.section || "")}</td>
	<td>${frappe.utils.escape_html(r.start_date ? String(r.start_date) : "")}</td>
	<td>${frappe.utils.escape_html(r.expiry_date ? String(r.expiry_date) : "")}</td>
	<td style="text-align:right;">${frappe.utils.escape_html(String(r.days_left ?? ""))}</td>
      <td style="text-align:center; font-size:16px;">${frappe.utils.escape_html(r.status || "")}</td>
    </tr>
  `).join("");

  const html = `
    <div id="el-drilldown" style="margin-top:14px; padding:12px; border:1px solid rgba(0,0,0,0.08); border-radius:10px;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px;">
        <div style="font-weight:800;">${frappe.utils.escape_html(title)}</div>
        <button class="btn btn-sm btn-default" id="el-drilldown-close">Close</button>
      </div>

      <div style="overflow:auto;">
        <table class="table table-bordered" style="margin:0;">
          <thead>
            <tr>
              <th>Asset</th>
              <th>Site</th>
				<th>Section</th>
				<th>Start Date</th>
				<th>Expiry Date</th>
				<th style="text-align:right;">Days Left</th>
              <th style="text-align:center;">Status</th>
            </tr>
          </thead>
          <tbody>
            ${tableRows || `<tr><td colspan="7" style="text-align:center; padding:14px;">No assets found</td></tr>`}
          </tbody>
        </table>
      </div>
    </div>
  `;

  // Insert UNDER the main datatable area
  wrap.find(".report-wrapper").append(html);

  wrap.find("#el-drilldown-close").on("click", () => {
    wrap.find("#el-drilldown").remove();
  });

render_audit_summary(report, { site });
}

function render_audit_summary(report, ctx) {
  const { site, asset } = ctx;
  const as_at = frappe.datetime.get_today();

  const main = $(report.page.main);

  // stable container always at bottom
  let host = main.find("#el-audit-host");
  if (!host.length) {
    main.append(`
      <div id="el-audit-host" style="max-width:1100px; margin:18px auto 0; text-align:center;"></div>
    `);
    host = main.find("#el-audit-host");
  }

  host.html(`
    <div style="font-weight:900; font-size:18px; margin-bottom:4px;">Document Audit Summary</div>
    <div style="font-weight:800; font-size:13px; opacity:.75; margin-bottom:10px;">Legals Submitted (last 10 days)</div>
    <div style="opacity:.7;">Loading…</div>
  `);

  frappe.call({
    method: "engineering.engineering.report.engineering_legals_report.fetch_second_table.get_recent_submitted_legals",
    args: { site, asset, days: 10, as_at_date: as_at },
    callback: (r) => {
      const rows = (r && r.message) ? r.message : [];

      const links = rows.map(x => {
        const name = x.name;
        const fleet = x.fleet_number || name;
        const url = `/app/engineering-legals/${encodeURIComponent(name)}`;

return `
<a href="${url}" target="_blank" rel="noopener noreferrer" style="
            display:inline-block;
            padding:6px 12px;
            border-radius:999px;
            border:1px solid rgba(31, 94, 43, 0.25);
            background: rgba(191, 229, 198, 0.85);
            color: #1f5e2b;
            text-decoration:none;
            margin:4px;
            font-weight:900;
          ">${frappe.utils.escape_html(fleet)}</a>
        `;
      }).join("");

      host.html(`
        <div style="font-weight:900; font-size:16px; margin-bottom:4px;">Document Audit Summary</div>
        <div style="font-weight:800; font-size:13px; opacity:.75; margin-bottom:10px;">Legals Submitted (last 10 days)</div>
        <div>${links || `<div style="opacity:.7;">No submitted legals in the last 10 days</div>`}</div>
      `);
    }
  });
}



function render_doc_history_tree(report, ctx) {
  const { site, section, asset } = ctx;

  const main = $(report.page.main);

  let host = main.find("#el-doc-history");
  if (!host.length) {
    main.append(`
      <div id="el-doc-history" style="max-width:1100px; margin:18px auto 0;"></div>
    `);
    host = main.find("#el-doc-history");
  }

  host.html(`
    <div style="text-align:center; font-weight:900; font-size:16px; margin-bottom:6px;">Doc History</div>
    <div style="text-align:center; font-weight:800; font-size:13px; opacity:.75; margin-bottom:10px;">
      All records
    </div>
    <div style="text-align:center; opacity:.7;">Loading…</div>
  `);

  const from_expiry_date = frappe.query_report.get_filter_value("from_expiry_date") || "";
  const to_expiry_date = frappe.query_report.get_filter_value("to_expiry_date") || "";

  frappe.call({
    method: "engineering.engineering.report.engineering_legals_report.fetch_second_table.get_doc_history_tree_meta",
    args: { site, section, asset, from_expiry_date, to_expiry_date },
    callback: (r) => {
      const payload = (r && r.message) ? r.message : {};
      const tree = payload.tree || [];
      host.html(build_doc_history_html(tree, payload));
    }
  });
}



function build_doc_history_html(tree, payload) {
  if (!tree.length) {
    return `<div style="text-align:center; opacity:.7;">No records</div>`;
  }

  const esc = frappe.utils.escape_html;

  const siteHtml = tree.map(siteNode => {
    const siteLabel = esc(siteNode.label || "Unknown");
    const siteCount = esc(String(siteNode.count ?? 0));

    const sectionHtml = (siteNode.children || []).map(secNode => {
      const secLabel = esc(secNode.label || "Unknown");
      const secCount = esc(String(secNode.count ?? 0));

      const fleetHtml = (secNode.children || []).map(fleetNode => {
        const fleet = esc(fleetNode.label || "Unknown");
        const cnt = esc(String(fleetNode.count ?? 0));

        // IMPORTANT: no docs loaded yet (fast)
        return `
          <details
            class="el-fleet-node"
            data-site="${esc(siteNode.label || "")}"
            data-section="${esc(secNode.label || "")}"
            data-fleet="${esc(fleetNode.label || "")}"
            style="border:1px solid rgba(0,0,0,0.08); border-radius:10px; padding:8px 10px; margin:8px 0;"
          >
            <summary style="cursor:pointer; font-weight:900;">
              → ${fleet} <span style="opacity:.65;">(${cnt})</span>
            </summary>
            <div class="el-fleet-body" style="margin-top:8px; opacity:.7;">Expand to load…</div>
          </details>
        `;
      }).join("");

      return `
        <details style="border:1px solid rgba(0,0,0,0.10); border-radius:12px; padding:10px 12px; margin:10px 0;">
          <summary style="cursor:pointer; font-weight:900; font-size:14px;">
            → ${secLabel} <span style="opacity:.65;">(${secCount})</span>
          </summary>
          <div style="margin-top:8px;">
            ${fleetHtml}
          </div>
        </details>
      `;
    }).join("");


    return `
      <details class="el-site-node" style="border:1px solid rgba(0,0,0,0.12); border-radius:14px; padding:12px 14px; margin:12px 0;">
        <summary style="cursor:pointer; font-weight:900; font-size:15px; display:flex; justify-content:space-between; align-items:center;">
          <span>▼ ${siteLabel} <span style="opacity:.65;">(${siteCount})</span></span>
          <button type="button" class="btn btn-xs btn-default el-collapse-all" title="Collapse all">Collapse all</button>
        </summary>
        <div style="margin-top:10px;">
          ${sectionHtml}
        </div>
      </details>
    `;
  }).join("");

  return `
    <div style="text-align:right; margin:0 0 10px 0;">
      <button type="button" class="btn btn-sm btn-default el-collapse-all-sites" title="Collapse all sites">
        Collapse all sites
      </button>
    </div>
    ${siteHtml}
  `;
}

function render_doc_rows_table(rows) {
  if (!rows || !rows.length) {
    return `<div style="text-align:center; padding:10px;">No docs</div>`;
  }

  const esc = frappe.utils.escape_html;
  const groups = {};

  (rows || []).forEach(d => {
    const key = d.start_date ? String(d.start_date) : "No Start Date";
    groups[key] = groups[key] || [];
    groups[key].push(d);
  });

  const dateHtml = Object.keys(groups).map(dateKey => {
    const docs = groups[dateKey] || [];
    const safeDate = esc(dateKey);
    const safeCount = esc(String(docs.length));

    const trs = docs.map(d => {
      const name = esc(d.name || "");
      const exp = esc(d.expiry_date ? String(d.expiry_date) : "");
      const mod = esc(d.modified ? String(d.modified) : "");
      const fileUrl = (d.attach_paper || "").trim();
      const href = fileUrl ? encodeURI(fileUrl) : (d.record_url || `/app/engineering-legals/${encodeURIComponent(d.name || "")}`);

      return `
        <tr>
          <td><a href="${href}" target="_blank" rel="noopener noreferrer">${name}</a></td>
          <td>${exp}</td>
          <td>${mod}</td>
        </tr>
      `;
    }).join("");

    return `
      <details style="border:1px solid rgba(0,0,0,0.08); border-radius:10px; padding:8px 10px; margin:8px 0;" open>
        <summary style="cursor:pointer; font-weight:900;">
          → ${safeDate} <span style="opacity:.65;">(${safeCount})</span>
        </summary>
        <div style="margin-top:8px; overflow:auto;">
          <table class="table table-bordered" style="margin:0;">
            <thead>
              <tr>
                <th>Document</th>
                <th>Expiry</th>
                <th>Modified</th>
              </tr>
            </thead>
            <tbody>${trs}</tbody>
          </table>
        </div>
      </details>
    `;
  }).join("");

  return `<div>${dateHtml}</div>`;
}



function bind_doc_history_lazy_loader(report) {
  const wrap = $(report.page.wrapper);

  wrap.off("click.el_collapse_all_sites").on("click.el_collapse_all_sites", ".el-collapse-all-sites", function (e) {
    e.preventDefault();
    e.stopPropagation();

    wrap.find("#el-doc-history details.el-site-node").prop("open", false);
  });



  wrap.off("click.el_collapse_one_site").on("click.el_collapse_one_site", ".el-collapse-all", function (e) {
    e.preventDefault();
    e.stopPropagation();

    const siteNode = $(this).closest("details.el-site-node");
    siteNode.find("details").prop("open", false);
    siteNode.prop("open", false);
  });


  // Load docs immediately when user clicks the fleet SUMMARY (feels instant)
  wrap.off("click.el_doc_history").on("click.el_doc_history", "details.el-fleet-node > summary", function () {
    const node = $(this).closest("details.el-fleet-node");

    if (node.data("loaded") || node.data("loading")) return;

    const site = node.attr("data-site") || "";
    const section = node.attr("data-section") || "";
    const fleet = node.attr("data-fleet") || "";
    const asset = frappe.query_report.get_filter_value("asset") || "";
    const body = node.find(".el-fleet-body");
    const from_expiry_date = frappe.query_report.get_filter_value("from_expiry_date") || "";
    const to_expiry_date = frappe.query_report.get_filter_value("to_expiry_date") || "";

    const cache_key = `${site}|${section}|${fleet}`;
    if (EL_DOC_CACHE[cache_key]) {
      node.data("loaded", 1);
      body.html(render_doc_rows_table(EL_DOC_CACHE[cache_key]));
      return;
    }

    node.data("loading", 1);
    body.html("Loading…");

    frappe.call({
      method: "engineering.engineering.report.engineering_legals_report.fetch_second_table.get_doc_history_docs",
      args: { site, section, fleet_number: fleet, asset, from_expiry_date, to_expiry_date, limit: 50, offset: 0 },
      callback: (r) => {
        const rows = (r && r.message && r.message.rows) ? r.message.rows : [];
        EL_DOC_CACHE[cache_key] = rows;

        node.data("loading", 0);
        node.data("loaded", 1);

        body.html(render_doc_rows_table(rows));
      }
    });
  });


  
}