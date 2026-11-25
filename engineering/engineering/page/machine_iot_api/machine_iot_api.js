frappe.pages["machine-iot-api"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Machine IoT API Engine",
        single_column: true
    });

    const $body = $(page.body);
    let oem = "BELL";
    let dataset = "fleet";
    let start = 0;
    let search = "";
    let selected = null;
    const pageLength = 25;

    const OEMS = ["BELL", "KOBELCO", "MPI", "CTRACK", "CAT", "VOLVO"];
    let catalogue = {};

    const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({
        "&": "&amp;", "<": "&lt;", ">": "&gt;",
        '"': "&quot;", "'": "&#39;"
    })[c]);

    const display = value => {
        if (value === null || value === undefined || value === "") return "—";
        if (typeof value === "object") return JSON.stringify(value);
        return String(value);
    };

    function renderShell() {
        $body.html(`
            <style>
                .mio-shell { color: var(--text-color); }
                .mio-heading {
                    display:flex;justify-content:space-between;
                    align-items:center;gap:12px;flex-wrap:wrap;margin:8px 0 20px;
                }
                .mio-heading h2 {font-size:23px;font-weight:700;margin:0;}
                .mio-muted {color:var(--text-muted);font-size:12px;}
                .mio-tabs {display:flex;gap:7px;overflow-x:auto;margin-bottom:18px;}
                .mio-tab {
                    border:1px solid var(--border-color);background:var(--card-bg);
                    padding:10px 23px;border-radius:8px;font-weight:650;
                    white-space:nowrap;cursor:pointer;
                }
                .mio-tab.active {background:var(--primary);color:white;border-color:var(--primary);}
                .mio-meta {
                    display:flex;justify-content:space-between;align-items:center;
                    flex-wrap:wrap;gap:12px;background:var(--card-bg);
                    border:1px solid var(--border-color);padding:15px;
                    border-radius:10px;margin-bottom:18px;
                }
                .mio-meta strong {font-size:18px;}
                .mio-layout {display:grid;grid-template-columns:220px minmax(0,1fr) 310px;gap:14px;align-items:start;}
                .mio-panel {
                    background:var(--card-bg);border:1px solid var(--border-color);
                    border-radius:10px;overflow:hidden;min-width:0;
                }
                .mio-panel-title {padding:14px 15px;border-bottom:1px solid var(--border-color);font-weight:700;}
                .mio-dataset {
                    display:block;width:100%;text-align:left;padding:13px 14px;
                    border:0;border-bottom:1px solid var(--border-color);
                    background:transparent;color:var(--text-color);cursor:pointer;
                }
                .mio-dataset.active {background:var(--subtle-accent);font-weight:700;color:var(--primary);}
                .mio-content {padding:14px;}
                .mio-search {display:flex;gap:8px;margin-bottom:12px;}
                .mio-search input {flex:1;min-width:0;}
                .mio-table-wrap {overflow:auto;max-height:65vh;}
                .mio-table {width:100%;border-collapse:collapse;font-size:12px;white-space:nowrap;}
                .mio-table th {
                    position:sticky;top:0;background:var(--subtle-accent);
                    z-index:1;text-align:left;padding:11px 9px;
                    border-bottom:1px solid var(--border-color);
                }
                .mio-table td {padding:10px 9px;border-bottom:1px solid var(--border-color);max-width:240px;overflow:hidden;text-overflow:ellipsis;}
                .mio-table tr[data-name] {cursor:pointer;}
                .mio-table tr[data-name]:hover,.mio-table tr.selected {background:var(--subtle-accent);}
                .mio-pagination {display:flex;justify-content:space-between;align-items:center;padding:12px;gap:8px;}
                .mio-details {padding:13px;}
                .mio-details dl {display:grid;grid-template-columns:1fr;gap:0;margin:0;}
                .mio-details dl div {padding:8px 0;border-bottom:1px solid var(--border-color);}
                .mio-details dt {font-size:11px;color:var(--text-muted);margin-bottom:3px;}
                .mio-details dd {font-size:12px;font-weight:600;margin:0;overflow-wrap:anywhere;}
                .mio-raw {margin-top:14px;}
                .mio-raw pre {
                    background:var(--control-bg);border:1px solid var(--border-color);
                    border-radius:7px;padding:12px;max-height:350px;overflow:auto;
                    font-size:11px;white-space:pre-wrap;overflow-wrap:anywhere;
                }
                .mio-empty {padding:35px 15px;text-align:center;color:var(--text-muted);}
                .mio-status {color:var(--text-muted);font-size:12px;}
                @media(max-width:1150px) {
                    .mio-layout {grid-template-columns:190px minmax(0,1fr);}
                    .mio-right {grid-column:1/-1;}
                }
                @media(max-width:700px) {
                    .mio-layout {grid-template-columns:1fr;}
                    .mio-right {grid-column:auto;}
                    .mio-table-wrap {max-height:55vh;}
                }
            </style>

            <div class="mio-shell">
                <div class="mio-heading">
                    <div>
                        <h2>Machine IoT API Engine</h2>
                        <div class="mio-muted">OEM API results · Inspect, search and explore source data</div>
                    </div>
                    <span class="mio-status">Read-only data browser</span>
                </div>

                <div class="mio-tabs" id="mio-oems">
                    ${OEMS.map(name => `
                        <button class="mio-tab ${name === oem ? "active" : ""}" data-oem="${name}">${name}</button>
                    `).join("")}
                </div>

                <div class="mio-meta">
                    <div>
                        <strong id="mio-oem-title">BELL</strong>
                        <div class="mio-muted" id="mio-dataset-title">Fleet / Machines</div>
                    </div>
                    <div class="mio-status" id="mio-count">Loading...</div>
                </div>

                <div class="mio-layout">
                    <section class="mio-panel">
                        <div class="mio-panel-title">Datasets</div>
                        <div id="mio-datasets"></div>
                    </section>

                    <section class="mio-panel">
                        <div class="mio-panel-title" id="mio-table-title">API Results</div>
                        <div class="mio-content">
                            <div class="mio-search">
                                <input type="text" class="form-control" id="mio-search"
                                    placeholder="Search machine, serial, asset...">
                                <button class="btn btn-primary" id="mio-search-btn">Search</button>
                            </div>
                            <div class="mio-table-wrap" id="mio-table">
                                <div class="mio-empty">Loading records...</div>
                            </div>
                        </div>
                        <div class="mio-pagination">
                            <span class="mio-muted" id="mio-page-label">Page 1</span>
                            <div style="display:flex;gap:6px">
                                <button class="btn btn-default btn-sm" id="mio-prev">Previous</button>
                                <button class="btn btn-default btn-sm" id="mio-next">Next</button>
                            </div>
                        </div>
                    </section>

                    <section class="mio-panel mio-right">
                        <div class="mio-panel-title">Record details</div>
                        <div id="mio-details" class="mio-details">
                            <div class="mio-empty">Select a record to inspect its fields and source data.</div>
                        </div>
                    </section>
                </div>
            </div>
        `);

        bindEvents();
        $("#mio-datasets").html(
            '<div class="mio-empty">Loading datasets...</div>'
        );

        frappe.call({
            method: "engineering.controllers.machine_iot_api_engine.get_catalogue",
            callback: function(r) {
                if (r.exc || !r.message) {
                    $("#mio-datasets").html(
                        '<div class="mio-empty">Could not load OEM datasets.</div>'
                    );
                    return;
                }

                catalogue = r.message;
                renderDatasets();
                loadData();
            }
        });
    }

    function renderDatasets() {
        const items = (catalogue[oem] || []).map(
            item => [item.key, item.label]
        );
        if (!items.some(item => item[0] === dataset)) {
            dataset = items.length ? items[0][0] : "";
        }

        $("#mio-datasets").html(items.length
            ? items.map(([key, label]) => `
                <button class="mio-dataset ${dataset === key ? "active" : ""}" data-dataset="${key}">
                    ${esc(label)}
                </button>
            `).join("")
            : `<div class="mio-empty">No verified dataset available for ${esc(oem)} yet.</div>`
        );

        $("#mio-oem-title").text(oem);
        $("#mio-dataset-title").text(items.find(x => x[0] === dataset)?.[1] || "No dataset");
        $("#mio-count").text(items.length ? "Existing stored API records" : "Integration not yet available");
        $("#mio-table").html(`<div class="mio-empty">${items.length ? "Select a dataset." : "No stored data configured for this OEM."}</div>`);
        $("#mio-details").html(`<div class="mio-empty">Select a record to inspect its details.</div>`);
    }

    function loadData() {
        if (!dataset) return;

        $("#mio-table").html(`<div class="mio-empty">Loading API records...</div>`);

        frappe.call({
            method: "engineering.controllers.machine_iot_api_engine.get_dataset",
            args: {oem, dataset, search, start, page_length: pageLength},
            callback: function(r) {
                if (r.exc || !r.message) {
                    $("#mio-table").html(`<div class="mio-empty">Unable to load records. Check permissions and server logs.</div>`);
                    return;
                }
                renderTable(r.message);
            },
            error: function() {
                $("#mio-table").html(`<div class="mio-empty">Request failed. Check your access permissions.</div>`);
            }
        });
    }

    function renderTable(data) {
        const fields = data.fields;
        const rows = data.rows;

        $("#mio-table-title").text(data.label + " — API Results");
        $("#mio-count").text(`${data.doctype} · ${rows.length} records shown`);
        $("#mio-page-label").text(`Showing ${start + 1}–${start + rows.length}${data.has_more ? " · More available" : ""}`);
        $("#mio-prev").prop("disabled", start === 0);
        $("#mio-next").prop("disabled", !data.has_more);

        if (!rows.length) {
            $("#mio-table").html(`<div class="mio-empty">No records found.</div>`);
            return;
        }

        $("#mio-table").html(`
            <table class="mio-table">
                <thead><tr>
                    <th>#</th>
                    ${fields.map(f => `<th>${esc(f.label)}</th>`).join("")}
                </tr></thead>
                <tbody>
                    ${rows.map((row, index) => `
                        <tr data-name="${esc(row.name)}" class="${selected === row.name ? "selected" : ""}">
                            <td>${start + index + 1}</td>
                            ${fields.map(f => `<td title="${esc(display(row[f.fieldname]))}">${esc(display(row[f.fieldname]))}</td>`).join("")}
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        `);
    }

    function loadRecord(name) {
        selected = name;
        $("#mio-details").html(`<div class="mio-empty">Loading record...</div>`);

        frappe.call({
            method: "engineering.controllers.machine_iot_api_engine.get_record",
            args: {oem, dataset, name},
            callback: function(r) {
                if (r.exc || !r.message) {
                    $("#mio-details").html(`<div class="mio-empty">Record could not be loaded.</div>`);
                    return;
                }
                renderRecord(r.message);
                $("#mio-table tr[data-name]").removeClass("selected");
                $("#mio-table tr[data-name]").filter(function() {
                    return $(this).attr("data-name") === name;
                }).addClass("selected");
            },
            error: function() {
                $("#mio-details").html(`<div class="mio-empty">Access denied or record unavailable.</div>`);
            }
        });
    }

    function renderRecord(data) {
        const record = data.record;
        const raw = data.raw || {};
        const fields = Object.entries(record).filter(([key, value]) =>
            key !== "name" && value !== null && value !== undefined && value !== ""
        );

        $("#mio-details").html(`
            <div class="mio-muted" style="margin-bottom:10px">${esc(data.doctype)}</div>
            <strong>${esc(record.fleet_number || "Unmapped")}</strong>
            <dl style="margin-top:12px">
                ${fields.map(([key, value]) => `
                    <div>
                        <dt>${esc(key.replaceAll("_", " "))}</dt>
                        <dd>${esc(display(value))}</dd>
                    </div>
                `).join("")}
            </dl>
            <div class="mio-raw">
                <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
                    <strong>Original API response</strong>
                    ${Object.values(raw).some(Boolean) ? `<button class="btn btn-default btn-xs" id="mio-copy-raw">Copy</button>` : ""}
                </div>
                ${Object.entries(raw).map(([key, value]) => `
                    <div style="margin-top:10px">
                        <div class="mio-muted">${esc(key)}</div>
                        <pre>${esc(value || "No source payload stored.")}</pre>
                    </div>
                `).join("")}
                ${!Object.values(raw).some(Boolean)
                    ? `<div class="mio-empty">No original API response is stored for this record. Displayed fields are the existing processed ERPNext data.</div>`
                    : ""}
            </div>
        `);

        $("#mio-copy-raw").off("click").on("click", function() {
            const content = JSON.stringify(raw, null, 2);
            if (navigator.clipboard?.writeText) {
                navigator.clipboard.writeText(content)
                    .then(() => frappe.show_alert("Source data copied"))
                    .catch(() => frappe.msgprint("Unable to copy source data."));
            } else {
                frappe.utils.copy_to_clipboard(content);
            }
        });
    }

    function bindEvents() {
        $body.on("click", ".mio-tab", function() {
            oem = $(this).data("oem");
            dataset = "";
            start = 0;
            search = "";
            selected = null;
            $body.find(".mio-tab").removeClass("active");
            $(this).addClass("active");
            $("#mio-search").val("");
            renderDatasets();
            loadData();
        });

        $body.on("click", ".mio-dataset", function() {
            dataset = $(this).data("dataset");
            start = 0;
            selected = null;
            search = $("#mio-search").val().trim();
            renderDatasets();
            loadData();
        });

        $body.on("click", "#mio-search-btn", function() {
            search = $("#mio-search").val().trim();
            start = 0;
            selected = null;
            loadData();
        });

        $body.on("keydown", "#mio-search", function(e) {
            if (e.key === "Enter") $("#mio-search-btn").click();
        });

        $body.on("click", "#mio-prev", function() {
            start = Math.max(0, start - pageLength);
            loadData();
        });

        $body.on("click", "#mio-next", function() {
            start += pageLength;
            loadData();
        });

        $body.on("click", "#mio-table tr[data-name]", function() {
            loadRecord($(this).attr("data-name"));
        });
    }

    renderShell();
};
