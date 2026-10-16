function mf_escape_html(value) {
    return frappe.utils.escape_html(String(value || ""));
}

function mf_get_filter_value(listview, fieldname) {
    const filters = (listview.filter_area && listview.filter_area.get())
        ? listview.filter_area.get()
        : [];

    for (const f of filters) {
        if (Array.isArray(f)) {
            if (f[1] === fieldname) {
                return f[3];
            }
        } else if (f && typeof f === "object") {
            if (f.fieldname === fieldname) {
                return f.value;
            }

            if (f[1] === fieldname) {
                return f[3];
            }
        }
    }

    return "";
}

function mf_get_wrapper(listview) {
    if (!listview.$machine_file_grouped_view) {
        listview.$machine_file_grouped_view = $(
            '<div class="machine-file-grouped-view" style="margin-top: 12px;"></div>'
        );

        listview.$machine_file_grouped_view.insertAfter(listview.$result);
    }

    return listview.$machine_file_grouped_view;
}


function mf_get_category_config(category) {
    /*
     * Raw ERP Asset Categories remain unchanged.
     * This only controls display label and order.
     */

    const raw = String(category || "").trim();
    const key = raw.toLowerCase();

    const config = {
        "excavator": {
            order: 1,
            label: "Excavators"
        },
        "excavators": {
            order: 1,
            label: "Excavators"
        },

        "dozer": {
            order: 2,
            label: "Dozers"
        },
        "dozers": {
            order: 2,
            label: "Dozers"
        },

        "adt": {
            order: 3,
            label: "ADTS"
        },
        "adts": {
            order: 3,
            label: "ADTS"
        },

        "diesel bowser": {
            order: 4,
            label: "Diesel Bowsers"
        },
        "diesel bowsers": {
            order: 4,
            label: "Diesel Bowsers"
        },

        "service truck": {
            order: 5,
            label: "Service Truck"
        },
        "service trucks": {
            order: 5,
            label: "Service Truck"
        },

        "water bowser": {
            order: 6,
            label: "Water Bowser"
        },
        "water bowsers": {
            order: 6,
            label: "Water Bowser"
        },

        "grader": {
            order: 7,
            label: "Grader"
        },
        "graders": {
            order: 7,
            label: "Grader"
        },

        "tlb": {
            order: 8,
            label: "TLB"
        },

        "drill": {
            order: 9,
            label: "Drills"
        },
        "drills": {
            order: 9,
            label: "Drills"
        },

        "ldv": {
            order: 10,
            label: "LDV"
        },

        "water pump": {
            order: 11,
            label: "Water pump"
        },
        "water pumps": {
            order: 11,
            label: "Water pump"
        },

        "lighting plant": {
            order: 12,
            label: "Lightning Plant"
        },
        "lighting plants": {
            order: 12,
            label: "Lightning Plant"
        },
        "lightning plant": {
            order: 12,
            label: "Lightning Plant"
        },
        "lightning plants": {
            order: 12,
            label: "Lightning Plant"
        }
    };

    return config[key] || {
        order: 999,
        label: raw || "Uncategorised"
    };
}
// END MACHINE FILE CATEGORY CONFIG


function mf_position_period_controls(listview) {
    const $row = listview.$machine_file_period_controls;
    if (!$row) return;

    const machineControl = listview.page.fields_dict.machine;
    const $machine = machineControl
        ? machineControl.$wrapper
        : $(listview.page.wrapper)
            .find('.frappe-control[data-fieldname="machine"]').first();

    if ($machine && $machine.length) {
        $row.insertAfter($machine);
    }
}

function mf_render_grouped_register(listview) {
    mf_position_period_controls(listview);
    const wrapper = mf_get_wrapper(listview);

    const site = mf_get_filter_value(listview, "site") || "";
    const machine_category = mf_get_filter_value(listview, "machine_category") || "";
    const machine = mf_get_filter_value(listview, "machine") || "";

    if (listview.$result) {
        listview.$result.hide();
    }

    if (listview.$paging_area) {
        listview.$paging_area.hide();
    }

    wrapper.html(`
        <div style="
            padding: 24px;
            border: 1px solid #d9e4ef;
            background: #fff;
            border-radius: 8px;
            color: #6b7280;
        ">
            Loading machine register...
        </div>
    `);

    frappe.call({
        method: "engineering.engineering.doctype.machine_file.machine_file.get_machine_file_register",
        args: {
            site: site,
            machine_category: machine_category,
            machine: machine
        },
        callback: function(r) {
            const rows = r.message || [];

            if (!rows.length) {
                wrapper.html(`
                    <style>
                        .mf-register-empty {
                            padding: 30px;
                            text-align: center;
                            border: 1px solid #d9e4ef;
                            background: #fff;
                            border-radius: 8px;
                        }
                    </style>

                    <div class="mf-register-empty">
                        <div style="font-size:18px;font-weight:700;margin-bottom:8px;">
                            No Machine File records found
                        </div>
                        <div style="color:#6b7280;">
                            Try clearing the filters or click Sync Machines.
                        </div>
                    </div>
                `);
                return;
            }

            const grouped = {};

            rows.forEach(row => {
                const rawCategory =
                    row.machine_category || "Uncategorised";

                const cfg =
                    mf_get_category_config(rawCategory);

                const groupKey =
                    cfg.label;

                if (!grouped[groupKey]) {
                    grouped[groupKey] = {
                        label: cfg.label,
                        order: cfg.order,
                        rows: []
                    };
                }

                grouped[groupKey].rows.push(row);
            });

            const title_site =
                site
                ? ` for ${mf_escape_html(site)}`
                : "";

            const ordered_categories =
                Object.values(grouped).sort(
                    (a, b) => {
                        if (a.order !== b.order) {
                            return a.order - b.order;
                        }

                        return a.label.localeCompare(
                            b.label
                        );
                    }
                );

            let html = `
                <style>
                    .mf-register-main {
                        border: 1px solid #d9e4ef;
                        border-radius: 8px;
                        background: #fff;
                        overflow: hidden;
                    }

                    .mf-register-top {
                        background: #dfeaf5;
                        color: #0b66c3;
                        font-weight: 700;
                        padding: 14px 18px;
                        border-bottom: 1px solid #d9e4ef;
                    }

                    .mf-register-meta {
                        padding: 10px 18px 0 18px;
                        color: #6b7280;
                        font-size: 12px;
                    }

                    .mf-category-card {
                        margin: 14px 18px;
                        border: 1px solid #d9e4ef;
                        border-radius: 8px;
                        overflow: hidden;
                        background: #fff;
                    }

                    .mf-category-title {
                        background: #eef3f8;
                        color: #0b66c3;
                        font-weight: 700;
                        padding: 12px 14px;
                        border-bottom: 1px solid #d9e4ef;
                    }

                    .mf-table-wrap {
                        overflow-x: auto;
                    }

                    .mf-table {
                        width: 100%;
                        border-collapse: collapse;
                    }

                    .mf-table th {
                        background: #f5f7fa;
                        color: #0b66c3;
                        font-weight: 700;
                        text-align: left;
                        padding: 11px 12px;
                        border-bottom: 1px solid #d9e4ef;
                        font-size: 13px;
                    }

                    .mf-table td {
                        padding: 11px 12px;
                        border-bottom: 1px solid #e8edf3;
                        font-size: 14px;
                        vertical-align: middle;
                    }

                    .mf-table tr:last-child td {
                        border-bottom: 0;
                    }

                    .mf-machine-link {
                        color: #2f3b52;
                        font-weight: 700;
                        text-decoration: none;
                        cursor: pointer;
                    }

                    .mf-machine-link:hover {
                        color: #0b66c3;
                        text-decoration: underline;
                    }

                    .mf-count {
                        color: #6b7280;
                        font-size: 12px;
                        font-weight: 500;
                        margin-left: 8px;
                    }
                </style>

                <div class="mf-register-main">
                    <div class="mf-register-top">
                        Total Fleet${title_site}
                    </div>

                    <div class="mf-register-meta">
                        Total Machines: <b>${rows.length}</b>
                        ${machine_category ? `&nbsp; | &nbsp; Category Filter: <b>${mf_escape_html(machine_category)}</b>` : ""}
                        ${machine ? `&nbsp; | &nbsp; Machine Filter: <b>${mf_escape_html(machine)}</b>` : ""}
                    </div>
            `;

            ordered_categories.forEach(group => {
                const category = group.label;
                const items = group.rows;

                html += `
                    <div class="mf-category-card">
                        <div class="mf-category-title">
                            ${mf_escape_html(category)}
                            <span class="mf-count">(${items.length})</span>
                        </div>

                        <div class="mf-table-wrap">
                            <table class="mf-table">
                                <thead>
                                    <tr>
                                        <th style="width: 36%;">Plant Number</th>
                                        <th style="width: 44%;">Machine Model</th>
                                        <th style="width: 20%;">Location</th>
                                    </tr>
                                </thead>
                                <tbody>
                `;

                items.forEach(row => {
                    const item_name = row.item_code || row.machine_name || row.machine || "";

                    html += `
                        <tr>
                            <td>
                                <a href="#"
                                   class="mf-machine-link"
                                   data-name="${mf_escape_html(row.name)}">
                                    ${mf_escape_html(row.machine)}
                                </a>
                            </td>
                            <td>${mf_escape_html(item_name)}</td>
                            <td>${mf_escape_html(row.site || "")}</td>
                        </tr>
                    `;
                });

                html += `
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            });

            html += `</div>`;

            wrapper.html(html);

            wrapper.find(".mf-machine-link").on("click", function(e) {
                e.preventDefault();

                const name = $(this).data("name");

                if (name) {
                    frappe.set_route("Form", "Machine File", name);
                }
            });
        }
    });
}



function mf_hide_id_filter(listview) {
    /*
     * Hide the standard Frappe ID/name filter from
     * the Machine File register only.
     *
     * This does NOT remove the document ID from ERP.
     */

    try {
        if (
            listview.page
            && listview.page.fields_dict
            && listview.page.fields_dict.name
            && listview.page.fields_dict.name.$wrapper
        ) {
            listview.page.fields_dict.name.$wrapper.hide();
        }

        const $page =
            listview.page && listview.page.main
                ? $(listview.page.main)
                : $(".layout-main-section");

        $page
            .find(
                'input[data-fieldname="name"], ' +
                'input[placeholder="ID"]'
            )
            .each(function() {
                const $input = $(this);

                const $wrapper =
                    $input.closest(
                        ".frappe-control, " +
                        ".form-group, " +
                        ".field-area"
                    );

                if ($wrapper.length) {
                    $wrapper.hide();
                } else {
                    $input.parent().hide();
                }
            });

    } catch (e) {
        console.warn(
            "Machine File: could not hide ID filter",
            e
        );
    }
}


function mf_add_period_controls(listview) {
    if (listview.machine_file_period_controls) {
        return;
    }

    // Period state is carried into Machine File without creating database filters.
    const $row = $('<div class="row machine-file-period-controls"></div>');
    listview.$machine_file_period_controls = $row;
    $row.insertBefore(mf_get_wrapper(listview));
    mf_position_period_controls(listview);

    function addControl(df) {
        df.placeholder = df.label;
        df.onchange = () => {
            const controls = listview.machine_file_period_controls;
            const labels = controls.month_year ? controls.month_year.get_value() || [] : [];
            const months = labels.map(label => {
                const parts = String(label).split(" - ");
                const month = Array.from({length: 12}, (_, n) =>
                    new Date(2000, n, 1).toLocaleString("en-GB", {month: "long"})
                ).indexOf(parts[0]) + 1;
                return `${parts[1]}-${String(month).padStart(2, "0")}`;
            });
            frappe.machine_file_period = {
                from_date: controls.from_date ? controls.from_date.get_value() || "" : "",
                to_date: controls.to_date ? controls.to_date.get_value() || "" : "",
                months: months,
                labels: labels
            };
        };
        const $column = $('<div class="machine-file-period-control"></div>').appendTo($row);
        return frappe.ui.form.make_control({
            parent: $column,
            df: df,
            render_input: true
        });
    }

    const controls = {};
    listview.machine_file_period_controls = controls;

    controls.from_date = addControl({
        fieldname: "mf_from_date",
        label: __("From Date"),
        fieldtype: "Date"
    });

    controls.to_date = addControl({
        fieldname: "mf_to_date",
        label: __("To Date"),
        fieldtype: "Date"
    });

    controls.month_year = addControl({
        fieldname: "mf_month_year",
        label: __("Month and Year"),
        fieldtype: "MultiSelectList",
        get_data(txt) {
            const search = String(txt || "").trim();
            const yearMatch = search.match(/\b\d{4}\b/);
            const year = yearMatch
                ? Number(yearMatch[0])
                : new Date().getFullYear();

            if (year < 1000 || year > 9999) {
                return [];
            }

            const monthSearch = search
                .replace(/\b\d{4}\b/g, "")
                .replace(/[-–]/g, "")
                .trim()
                .toLowerCase();

            return Array.from({ length: 12 }, (_, month) => {
                const monthName = new Date(year, month, 1)
                    .toLocaleString("en-GB", { month: "long" });
                return {
                    value: `${monthName} - ${year}`,
                    description: ""
                };
            }).filter(option =>
                !monthSearch ||
                option.value.toLowerCase().includes(monthSearch)
            );
        }
    });
}

frappe.listview_settings["Machine File"] = {
    add_fields: [
        "machine",
        "machine_name",
        "item_code",
        "machine_category",
        "site"
    ],

    onload(listview) {

        mf_add_period_controls(listview);

        mf_hide_id_filter(listview);

        setTimeout(function() {
            mf_hide_id_filter(listview);
        }, 200);

        listview.page.add_inner_button(__("Sync Machines"), function() {
            frappe.call({
                method: "engineering.engineering.doctype.machine_file.machine_file.sync_machine_files",
                freeze: true,
                freeze_message: __("Checking Assets and Machine Files..."),
                callback(r) {
                    if (r.exc) {
                        return;
                    }

                    const result = r.message || {};

                    frappe.msgprint({
                        title: __("Machine File Register"),
                        indicator: "green",
                        message: `
                            <b>Total submitted Assets:</b> ${result.total_assets || 0}<br>
                            <b>New Machine Files created:</b> ${result.created || 0}<br>
                            <b>Already existed:</b> ${result.existing || 0}<br>
                            <b>Failed:</b> ${result.failed_count || 0}
                        `
                    });

                    listview.refresh();
                }
            });
        });
    },

    refresh(listview) {

        mf_hide_id_filter(listview);

        setTimeout(function() {
            mf_hide_id_filter(listview);
        }, 200);

        mf_render_grouped_register(listview);
    }
};





// MACHINE FILE LDV SUPPLIER ACCORDION V2 START

(function () {

    let requestRunning = false;


    function mfldv_escape(value) {

        return frappe.utils.escape_html(
            String(
                value || ""
            )
        );
    }


    function mfldv_supplier_label(
        supplier
    ) {

        const raw = String(
            supplier || ""
        ).trim();

        const value =
            raw.toLowerCase();


        /*
         * Do NOT automatically classify
         * blank suppliers as Isambane.
         */
        if (!raw) {
            return "Unassigned LDVs";
        }


        /*
         * Company-owned Isambane assets.
         */
        if (
            value.includes(
                "isambane"
            )
        ) {
            return "Isambane LDV";
        }


        /*
         * SAMU supplier variants.
         */
        if (
            value.includes(
                "samu"
            )
        ) {
            return "SAMU LDVs";
        }


        const cleaned =
            raw.replace(
                /\s+ldvs?$/i,
                ""
            ).trim();


        return (
            cleaned
            + " LDVs"
        );
    }


    function mfldv_find_card() {

        let result = null;


        $(".mf-category-card").each(
            function () {

                const $card =
                    $(this);


                const $title =
                    $card.find(
                        ".mf-category-title"
                    ).first();


                if (!$title.length) {
                    return;
                }


                /*
                 * Actual Machine File HTML is:
                 *
                 * <div class="mf-category-title">
                 *     LDV
                 *     <span class="mf-count">(50)</span>
                 * </div>
                 *
                 * Remove child elements before reading
                 * category text.
                 */
                const category =
                    $title
                        .clone()
                        .children()
                        .remove()
                        .end()
                        .text()
                        .trim()
                        .toUpperCase();


                if (
                    category !== "LDV"
                    && category !== "LDVS"
                ) {
                    return;
                }


                const $tableWrap =
                    $card.find(
                        ".mf-table-wrap"
                    ).first();


                const $table =
                    $card.find(
                        ".mf-table"
                    ).first();


                if (
                    !$table.length
                    || !$tableWrap.length
                ) {
                    return;
                }


                result = {
                    $card:
                        $card,

                    $title:
                        $title,

                    $tableWrap:
                        $tableWrap,

                    $table:
                        $table
                };


                return false;
            }
        );


        return result;
    }


    function mfldv_read_rows(
        $table
    ) {

        const rows = [];


        $table
            .find(
                "tbody tr"
            )
            .each(
                function () {

                    const $cells =
                        $(this)
                            .children(
                                "td"
                            );


                    if (
                        $cells.length < 3
                    ) {
                        return;
                    }


                    const machine =
                        $cells
                            .eq(0)
                            .text()
                            .trim();


                    if (!machine) {
                        return;
                    }


                    rows.push({

                        machine:
                            machine,

                        plant_html:
                            $cells
                                .eq(0)
                                .html(),

                        model:
                            $cells
                                .eq(1)
                                .text()
                                .trim(),

                        location:
                            $cells
                                .eq(2)
                                .text()
                                .trim()

                    });
                }
            );


        return rows;
    }


    function mfldv_group_rows(
        visibleRows,
        supplierRows
    ) {

        const supplierMap = {};


        (
            supplierRows || []
        ).forEach(
            function (source) {

                const machine =
                    String(
                        source.machine
                        || ""
                    ).trim();


                if (!machine) {
                    return;
                }


                /*
                 * Correct Asset ownership value:
                 *
                 * Asset Owner = Supplier
                 *     -> Supplier
                 *
                 * Asset Owner = Company
                 *     -> Company
                 */
                const supplier =
                    String(
                        source.display_supplier
                        || source.supplier
                        || source.company
                        || ""
                    ).trim();


                supplierMap[
                    machine
                ] = supplier;
            }
        );


        const groups = {};


        visibleRows.forEach(
            function (row) {

                const actualSupplier =
                    supplierMap[
                        row.machine
                    ]
                    || "";


                const label =
                    mfldv_supplier_label(
                        actualSupplier
                    );


                if (!groups[label]) {
                    groups[label] = [];
                }


                /*
                 * Keep supplier value on the row
                 * so the table can display it.
                 */
                groups[label].push(
                    Object.assign(
                        {},
                        row,
                        {
                            supplier:
                                actualSupplier
                                || "-"
                        }
                    )
                );
            }
        );


        return groups;
    }


    function mfldv_group_sort(
        a,
        b
    ) {

        const aa =
            String(a)
                .toLowerCase();

        const bb =
            String(b)
                .toLowerCase();


        if (
            aa.startsWith(
                "isambane"
            )
            && !bb.startsWith(
                "isambane"
            )
        ) {
            return -1;
        }


        if (
            bb.startsWith(
                "isambane"
            )
            && !aa.startsWith(
                "isambane"
            )
        ) {
            return 1;
        }


        if (
            aa.startsWith(
                "samu"
            )
            && !bb.startsWith(
                "samu"
            )
        ) {
            return -1;
        }


        if (
            bb.startsWith(
                "samu"
            )
            && !aa.startsWith(
                "samu"
            )
        ) {
            return 1;
        }


        return a.localeCompare(
            b
        );
    }


    function mfldv_machine_table(
        rows
    ) {

        let body = "";


        rows.forEach(
            function (row) {

                body += `
                    <tr>

                        <td
                            style="
                                width:28%;
                            "
                        >
                            ${
                                row.plant_html
                                || mfldv_escape(
                                    row.machine
                                )
                            }
                        </td>


                        <td
                            style="
                                width:34%;
                            "
                        >
                            ${
                                mfldv_escape(
                                    row.model
                                )
                            }
                        </td>


                        <td
                            style="
                                width:18%;
                            "
                        >
                            ${
                                mfldv_escape(
                                    row.location
                                )
                            }
                        </td>


                        <td
                            style="
                                width:20%;
                            "
                        >
                            ${
                                mfldv_escape(
                                    row.supplier
                                    || "-"
                                )
                            }
                        </td>

                    </tr>
                `;
            }
        );


        return `
            <div
                class="
                    mf-ldv-supplier-table-wrap
                "
                style="
                    overflow-x:auto;
                "
            >

                <table
                    class="
                        mf-table
                        mf-ldv-supplier-table
                    "
                    style="
                        width:100%;
                        border-collapse:collapse;
                    "
                >

                    <thead>

                        <tr>

                            <th
                                style="
                                    width:28%;
                                "
                            >
                                Plant Number
                            </th>


                            <th
                                style="
                                    width:34%;
                                "
                            >
                                Machine Model
                            </th>


                            <th
                                style="
                                    width:18%;
                                "
                            >
                                Location
                            </th>


                            <th
                                style="
                                    width:20%;
                                "
                            >
                                Supplier
                            </th>

                        </tr>

                    </thead>


                    <tbody>
                        ${body}
                    </tbody>

                </table>

            </div>
        `;
    }


    function mfldv_render(
        block,
        visibleRows,
        supplierRows,
        supplierField
    ) {

        const groups =
            mfldv_group_rows(
                visibleRows,
                supplierRows
            );


        const names =
            Object.keys(
                groups
            ).sort(
                mfldv_group_sort
            );


        let suppliersHtml = "";


        names.forEach(
            function (
                supplierName,
                index
            ) {

                const rows =
                    groups[
                        supplierName
                    ];


                suppliersHtml += `
                    <div
                        class="
                            mf-ldv-supplier-group
                        "
                        style="
                            margin-top:8px;
                            border:
                                1px solid #d9e4ef;
                            border-radius:
                                6px;
                            overflow:hidden;
                            background:#fff;
                        "
                    >

                        <button
                            type="button"
                            class="
                                mf-ldv-supplier-button
                            "
                            data-index="${index}"
                            style="
                                border:0;
                                width:100%;
                                padding:
                                    11px 14px;
                                background:
                                    #f5f9fc;
                                display:flex;
                                justify-content:
                                    space-between;
                                align-items:center;
                                cursor:pointer;
                                text-align:left;
                            "
                        >

                            <span
                                style="
                                    color:#0b66c3;
                                    font-weight:700;
                                "
                            >

                                <span
                                    class="
                                        mf-ldv-supplier-arrow
                                    "
                                >
                                    ▶
                                </span>

                                ${
                                    mfldv_escape(
                                        supplierName
                                    )
                                }

                                <span
                                    style="
                                        color:#6b7280;
                                        font-size:12px;
                                        font-weight:500;
                                        margin-left:6px;
                                    "
                                >
                                    (${rows.length})
                                </span>

                            </span>


                            <span
                                class="
                                    mf-ldv-supplier-action
                                "
                                style="
                                    color:#6b7280;
                                    font-size:12px;
                                "
                            >
                                Show
                            </span>

                        </button>


                        <div
                            class="
                                mf-ldv-supplier-body
                            "
                            data-index="${index}"
                            style="
                                display:none;
                            "
                        >

                            ${
                                mfldv_machine_table(
                                    rows
                                )
                            }

                        </div>

                    </div>
                `;
            }
        );


        const html = `
            <div
                class="
                    mf-ldv-grouped-view
                "
            >

                <button
                    type="button"
                    class="
                        mf-ldv-main-button
                    "
                    style="
                        border:0;
                        width:100%;
                        padding:
                            12px 14px;
                        background:#eef3f8;
                        display:flex;
                        justify-content:
                            space-between;
                        align-items:center;
                        cursor:pointer;
                        text-align:left;
                    "
                >

                    <span
                        style="
                            color:#0b66c3;
                            font-weight:700;
                        "
                    >

                        <span
                            class="
                                mf-ldv-main-arrow
                            "
                        >
                            ▶
                        </span>

                        LDV

                        <span
                            style="
                                color:#6b7280;
                                font-size:12px;
                                font-weight:500;
                                margin-left:6px;
                            "
                        >
                            (${visibleRows.length})
                        </span>

                    </span>


                    <span
                        class="
                            mf-ldv-main-action
                        "
                        style="
                            color:#6b7280;
                            font-size:12px;
                        "
                    >
                        Show Suppliers
                    </span>

                </button>


                <div
                    class="
                        mf-ldv-supplier-list
                    "
                    style="
                        display:none;
                        padding:
                            0 8px 8px 8px;
                    "
                >

                    ${suppliersHtml}

                </div>

            </div>
        `;


        /*
         * Hide ONLY the original flat LDV view.
         */
        block.$title.hide();

        block.$tableWrap.hide();


        /*
         * Prevent duplicate grouping.
         */
        block.$card
            .children(
                ".mf-ldv-grouped-view"
            )
            .remove();


        block.$card.prepend(
            html
        );


        block.$card.attr(
            "data-mf-ldv-grouped",
            "1"
        );


        const $root =
            block.$card
                .children(
                    ".mf-ldv-grouped-view"
                )
                .first();


        /*
         * Main LDV Show / Hide
         */
        $root.on(
            "click",
            ".mf-ldv-main-button",
            function () {

                const $list =
                    $root.find(
                        ".mf-ldv-supplier-list"
                    );


                const $arrow =
                    $(this).find(
                        ".mf-ldv-main-arrow"
                    );


                const $action =
                    $(this).find(
                        ".mf-ldv-main-action"
                    );


                if (
                    $list.is(
                        ":visible"
                    )
                ) {

                    $list.hide();

                    $arrow.text(
                        "▶"
                    );

                    $action.text(
                        "Show Suppliers"
                    );

                } else {

                    $list.show();

                    $arrow.text(
                        "▼"
                    );

                    $action.text(
                        "Hide Suppliers"
                    );
                }
            }
        );


        /*
         * Supplier Show / Hide
         */
        $root.on(
            "click",
            ".mf-ldv-supplier-button",
            function () {

                const index =
                    String(
                        $(this).attr(
                            "data-index"
                        )
                    );


                const $body =
                    $root.find(
                        '.mf-ldv-supplier-body'
                        + '[data-index="'
                        + index
                        + '"]'
                    );


                const $arrow =
                    $(this).find(
                        ".mf-ldv-supplier-arrow"
                    );


                const $action =
                    $(this).find(
                        ".mf-ldv-supplier-action"
                    );


                if (
                    $body.is(
                        ":visible"
                    )
                ) {

                    $body.hide();

                    $arrow.text(
                        "▶"
                    );

                    $action.text(
                        "Show"
                    );

                } else {

                    $body.show();

                    $arrow.text(
                        "▼"
                    );

                    $action.text(
                        "Hide"
                    );
                }
            }
        );


        /*
         * Re-bind machine links because these rows are
         * newly rendered HTML.
         */
        $root.on(
            "click",
            ".mf-machine-link",
            function (event) {

                event.preventDefault();


                const name =
                    $(this).attr(
                        "data-name"
                    );


                if (name) {

                    frappe.set_route(
                        "Form",
                        "Machine File",
                        name
                    );
                }
            }
        );


        console.log(
            "Machine File LDV supplier grouping ready",
            {
                supplier_field:
                    supplierField,

                groups:
                    Object.fromEntries(
                        Object.entries(
                            groups
                        ).map(
                            function (
                                [key, value]
                            ) {
                                return [
                                    key,
                                    value.length
                                ];
                            }
                        )
                    )
            }
        );
    }


    function mfldv_apply() {

        if (requestRunning) {
            return;
        }


        const block =
            mfldv_find_card();


        if (!block) {
            return;
        }


        if (
            block.$card.attr(
                "data-mf-ldv-grouped"
            ) === "1"
        ) {
            return;
        }


        const visibleRows =
            mfldv_read_rows(
                block.$table
            );


        if (!visibleRows.length) {
            return;
        }


        requestRunning = true;


        frappe.call({

            method:
                "engineering.engineering.doctype.machine_file.machine_file.get_machine_supplier_details",

            args: {

                machines:
                    JSON.stringify(
                        visibleRows.map(
                            function (row) {
                                return row.machine;
                            }
                        )
                    )

            },


            callback:
                function (r) {

                    requestRunning =
                        false;


                    if (
                        r.exc
                        || !r.message
                    ) {
                        return;
                    }


                    if (
                        r.message.error
                    ) {

                        console.warn(
                            "Machine File LDV supplier error:",
                            r.message.error,
                            r.message
                        );

                        return;
                    }


                    mfldv_render(
                        block,
                        visibleRows,
                        r.message.rows
                        || [],
                        r.message.field
                        || ""
                    );
                },


            error:
                function () {

                    requestRunning =
                        false;
                }

        });
    }


    /*
     * Machine File register renders asynchronously.
     */
    function mfldv_schedule() {

        [
            100,
            250,
            500,
            900,
            1500
        ].forEach(
            function (delay) {

                setTimeout(
                    mfldv_apply,
                    delay
                );
            }
        );
    }


    mfldv_schedule();


    /*
     * Watch only the actual Machine File grouped register.
     */
    const register =
        document.querySelector(
            ".machine-file-grouped-view"
        );


    if (register) {

        const observer =
            new MutationObserver(
                function () {

                    mfldv_apply();
                }
            );


        observer.observe(
            register,
            {
                childList:
                    true,

                subtree:
                    true
            }
        );

    } else {

        /*
         * Register may not exist yet.
         */
        const bodyObserver =
            new MutationObserver(
                function () {

                    if (
                        document.querySelector(
                            ".machine-file-grouped-view"
                        )
                    ) {

                        mfldv_apply();
                    }
                }
            );


        bodyObserver.observe(
            document.body,
            {
                childList:
                    true,

                subtree:
                    true
            }
        );
    }


    /*
     * Site / category / machine filter refresh.
     */
    $(document)
        .off(
            "click.mfldvActual"
        )
        .on(
            "click.mfldvActual",
            ".filter-button, "
            + ".clear-filters, "
            + ".list-refresh",
            function () {

                setTimeout(
                    mfldv_apply,
                    500
                );
            }
        );

})();

// MACHINE FILE LDV SUPPLIER ACCORDION V2 END







// MACHINE FILE ALL CATEGORY SUPPLIER COLUMN START

(function () {

    let mf_supplier_request_running = false;


    function mf_supplier_escape(value) {

        return frappe.utils.escape_html(
            String(
                value || ""
            )
        );
    }


    function mf_supplier_collect_tables() {

        const tables = [];


        $(".mf-category-card").each(
            function () {

                const $card =
                    $(this);


                /*
                 * Use only the normal category table.
                 *
                 * This avoids accidentally modifying any
                 * nested/custom table.
                 */
                const $tableWrap =
                    $card
                        .children(
                            ".mf-table-wrap"
                        )
                        .first();


                if (!$tableWrap.length) {
                    return;
                }


                const $table =
                    $tableWrap
                        .children(
                            ".mf-table"
                        )
                        .first();


                if (!$table.length) {
                    return;
                }


                const $title =
                    $card
                        .children(
                            ".mf-category-title"
                        )
                        .first();


                const category =
                    $title
                        .clone()
                        .children()
                        .remove()
                        .end()
                        .text()
                        .trim();


                tables.push({
                    category:
                        category,

                    $card:
                        $card,

                    $table:
                        $table
                });
            }
        );


        return tables;
    }


    function mf_supplier_get_machines(
        tables
    ) {

        const machines = [];


        tables.forEach(
            function (entry) {

                entry.$table
                    .find(
                        "tbody tr"
                    )
                    .each(
                        function () {

                            const machine =
                                $(this)
                                    .children(
                                        "td"
                                    )
                                    .eq(0)
                                    .text()
                                    .trim();


                            if (
                                machine
                                && !machines.includes(
                                    machine
                                )
                            ) {
                                machines.push(
                                    machine
                                );
                            }
                        }
                    );
            }
        );


        return machines;
    }


    function mf_supplier_apply_to_table(
        entry,
        supplierMap
    ) {

        const $table =
            entry.$table;


        const $headerRow =
            $table
                .find(
                    "thead tr"
                )
                .first();


        if (!$headerRow.length) {
            return;
        }


        /*
         * ADD / REPAIR HEADER
         */

        if (
            !$headerRow
                .find(
                    'th[data-mf-column="supplier"]'
                )
                .length
        ) {

            /*
             * Rebalance widths:
             *
             * Plant Number   28%
             * Machine Model  34%
             * Location       18%
             * Supplier       20%
             */

            $headerRow
                .children("th")
                .eq(0)
                .css(
                    "width",
                    "28%"
                );


            $headerRow
                .children("th")
                .eq(1)
                .css(
                    "width",
                    "34%"
                );


            $headerRow
                .children("th")
                .eq(2)
                .css(
                    "width",
                    "18%"
                );


            $headerRow.append(`
                <th
                    data-mf-column="supplier"
                    style="
                        width:20%;
                    "
                >
                    Supplier
                </th>
            `);
        }


        /*
         * ADD SUPPLIER VALUE TO EVERY MACHINE
         */

        $table
            .find(
                "tbody tr"
            )
            .each(
                function () {

                    const $row =
                        $(this);


                    const machine =
                        $row
                            .children(
                                "td"
                            )
                            .eq(0)
                            .text()
                            .trim();


                    if (!machine) {
                        return;
                    }


                    let supplier =
                        supplierMap[
                            machine
                        ] || "";


                    /*
                     * Blank supplier means Isambane-owned.
                     */
                    if (!supplier) {
                        supplier = "-";
                    }


                    const $existing =
                        $row.find(
                            'td[data-mf-column="supplier"]'
                        );


                    if ($existing.length) {

                        $existing.html(
                            mf_supplier_escape(
                                supplier
                            )
                        );

                    } else {

                        $row.append(`
                            <td
                                data-mf-column="supplier"
                            >
                                ${
                                    mf_supplier_escape(
                                        supplier
                                    )
                                }
                            </td>
                        `);
                    }
                }
            );


        $table.attr(
            "data-mf-supplier-ready",
            "1"
        );
    }


    function mf_supplier_apply() {

        if (
            mf_supplier_request_running
        ) {
            return;
        }


        const tables =
            mf_supplier_collect_tables();


        if (!tables.length) {
            return;
        }


        /*
         * If every current table is already processed,
         * do nothing.
         */
        const needsUpdate =
            tables.some(
                function (entry) {

                    return (
                        entry.$table.attr(
                            "data-mf-supplier-ready"
                        )
                        !== "1"
                    );
                }
            );


        if (!needsUpdate) {
            return;
        }


        const machines =
            mf_supplier_get_machines(
                tables
            );


        if (!machines.length) {
            return;
        }


        mf_supplier_request_running =
            true;


        frappe.call({

            /*
             * Existing server method is generic enough
             * to resolve Asset supplier/owner for any
             * machine, not only LDVs.
             */
            method:
                "engineering.engineering.doctype.machine_file.machine_file.get_machine_supplier_details",

            args: {

                machines:
                    JSON.stringify(
                        machines
                    )

            },


            callback:
                function (r) {

                    mf_supplier_request_running =
                        false;


                    if (
                        r.exc
                        || !r.message
                    ) {
                        return;
                    }


                    if (
                        r.message.error
                    ) {

                        console.warn(
                            "Machine File Supplier:",
                            r.message.error,
                            r.message
                        );

                        return;
                    }


                    const supplierMap =
                        {};


                    (
                        r.message.rows
                        || []
                    ).forEach(
                        function (row) {

                            const machine =
                                String(
                                    row.machine
                                    || ""
                                ).trim();


                            if (!machine) {
                                return;
                            }


                            supplierMap[
                                machine
                            ] =
                                String(
                                    row.display_supplier
                                    || ""
                                ).trim();
                        }
                    );


                    tables.forEach(
                        function (entry) {

                            mf_supplier_apply_to_table(
                                entry,
                                supplierMap
                            );
                        }
                    );


                    console.log(
                        "Machine File Supplier column added to all categories.",
                        {
                            field:
                                r.message.field,

                            machine_count:
                                machines.length
                        }
                    );
                },


            error:
                function () {

                    mf_supplier_request_running =
                        false;
                }

        });
    }


    function mf_supplier_schedule() {

        [
            100,
            300,
            600,
            1000,
            1600
        ].forEach(
            function (delay) {

                setTimeout(
                    mf_supplier_apply,
                    delay
                );
            }
        );
    }


    /*
     * First load.
     */
    mf_supplier_schedule();


    /*
     * Machine File register redraws whenever
     * site/category/machine filters change.
     */
    const observer =
        new MutationObserver(
            function () {

                mf_supplier_apply();
            }
        );


    observer.observe(
        document.body,
        {
            childList:
                true,

            subtree:
                true
        }
    );


    /*
     * Also explicitly rerun after common
     * list/filter actions.
     */
    $(document)
        .off(
            "click.mfSupplierAll"
        )
        .on(
            "click.mfSupplierAll",
            ".filter-button, "
            + ".clear-filters, "
            + ".list-refresh",
            function () {

                setTimeout(
                    mf_supplier_apply,
                    500
                );
            }
        );

})();

// MACHINE FILE ALL CATEGORY SUPPLIER COLUMN END
