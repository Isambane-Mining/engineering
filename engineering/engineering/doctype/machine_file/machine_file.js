
function mf_selected_period() {
    return frappe.machine_file_period || {from_date: "", to_date: "", months: [], labels: []};
}

function mf_has_period() {
    const p = mf_selected_period();
    return Boolean(p.from_date || p.to_date || (p.months || []).length);
}

function mf_period_call(frm, options) {
    if (!mf_has_period()) return frappe.call(options);
    const view = frm._mf_period_view;
    if (!view) {
        frappe.msgprint(__("The selected period is still loading. Please try again."));
        return;
    }
    const method = options.method.split(".").pop();
    let data;
    if (method === "get_machine_file_section_details") {
        data = view.sections[String(options.args.index_no)];
    } else if (method === "get_machine_registration_movement") {
        data = view.movement;
    } else if (method === "get_machine_breakdown_log_summary") {
        data = view.breakdown;
    }
    options.callback({message: data || {}});
}

const MACHINE_FILE_INDEX = [
    ["1", "Machine Registration & Movement", ""],
    ["2", "Equipment Technical Information as per TMM COP16 & Vision Diagram", ""],
    ["3", "FRC Checklist", "Quarterly"],
    ["4", "Noise Level Baseline and Periodical Measurement Report (VOHE)", "Periodical"],
    ["5", "Illumination Baseline and Periodical Measurements Report (VOHE)", "Periodical"],
    ["6", "PDS Installation COC", ""],
    ["7", "PDS Inspection Report", "Inspection"],
    ["8", "Fire Suppression Issues Base Risk Assessment (IBRA) and Installation Certificate", ""],
    ["9", "Brake Test Report", "250 Hours / After Brake Work"],
    ["10", "C Track Inspection Report", ""],
    ["11", "Breakdown Log Sheet", "Continuous"],
    ["12", "Service Record / Job Card", "Every Service"],
    ["12.1", "Brake Wear Measurements", "Every Service"],
    ["13", "Tyre Inspection Report and Survey", "Inspection"],
    ["14", "Machine Support Post or Locking Pin", "6 Months NDT"],
    ["15", "Pre-use Checklist", "Refer to Pre-use File"],
    ["16", "Maintenance Inspection", "Inspection"],
    ["17", "PR's", ""],
    ["18", "Wear Check Job Cards", ""],
    ["19", "Component Replacement Reports & Warranty", ""],
    ["20", "Aircon & Heater Repairs", ""],
    ["21", "Pressure Vessel Inspection / Certificate", "As per Legal Expiry"]
];


function escape_html(value) {
    return frappe.utils.escape_html(
        String(value || "")
    );
}


function format_date(value) {
    if (!value) {
        return "-";
    }

    try {
        return frappe.datetime.str_to_user(
            value
        );
    } catch (e) {
        return value;
    }
}


function populate_machine_file_index(frm) {
    frm.clear_table(
        "index_items"
    );

    MACHINE_FILE_INDEX.forEach(
        item => {
            const row = frm.add_child(
                "index_items"
            );

            row.index_no = item[0];
            row.description = item[1];
            row.frequency = item[2];
            row.status = "Missing";
            row.record_count = 0;
        }
    );

    frm.refresh_field(
        "index_items"
    );

    render_machine_file_dashboard(
        frm
    );
}


function apply_machine_filter(frm) {
    frm.set_query(
        "machine",
        function() {
            const filters = {};

            if (frm.doc.site) {
                filters.location =
                    frm.doc.site;
            }

            if (
                frm.doc.machine_category
            ) {
                filters.asset_category =
                    frm.doc.machine_category;
            }

            return {
                filters: filters
            };
        }
    );
}


function get_status_style(status) {
    const styles = {
        "Current": {
            bg: "#d1f4dd",
            fg: "#137333"
        },
        "ERP Records": {
            bg: "#dbeafe",
            fg: "#1d4ed8"
        },
        "Due Soon": {
            bg: "#fff3cd",
            fg: "#8a6116"
        },
        "Overdue": {
            bg: "#f8d7da",
            fg: "#b42318"
        },
        "Missing": {
            bg: "#eeeeee",
            fg: "#5f6368"
        }
    };

    return (
        styles[status]
        || styles["Missing"]
    );
}


function status_badge(status) {
    const style =
        get_status_style(status);

    return `
        <span
            style="
                display:inline-block;
                padding:5px 10px;
                border-radius:14px;
                background:${style.bg};
                color:${style.fg};
                font-weight:600;
                font-size:12px;
                white-space:nowrap;
            "
        >
            ${escape_html(status)}
        </span>
    `;
}




function set_machine_file_full_width(frm) {
    /*
     * Machine File dashboard should use the full available
     * form width instead of Frappe's normal narrow column.
     */

    const dashboard =
        frm.fields_dict.index_dashboard;

    if (!dashboard || !dashboard.$wrapper) {
        return;
    }

    const $wrapper =
        dashboard.$wrapper;

    const $control =
        $wrapper.closest(".frappe-control");

    const $column =
        $wrapper.closest(".form-column");

    const $section =
        $wrapper.closest(".form-section");

    const $sectionBody =
        $section.find(".section-body").first();

    /*
     * Make the HTML field span the complete section.
     */
    if ($control.length) {
        $control.css({
            "width": "100%",
            "max-width": "100%",
            "flex": "0 0 100%"
        });
    }

    if ($column.length) {
        $column.css({
            "width": "100%",
            "max-width": "100%",
            "flex": "0 0 100%",
            "padding-left": "0",
            "padding-right": "0"
        });

        $column.removeClass(
            "col-sm-6 col-md-6 col-lg-6"
        );

        $column.addClass(
            "col-sm-12"
        );
    }

    if ($sectionBody.length) {
        $sectionBody.css({
            "display": "block",
            "width": "100%",
            "max-width": "100%"
        });
    }

    /*
     * Expand the main form area.
     */
    const $mainSection =
        frm.$wrapper.closest(
            ".layout-main-section"
        );

    if ($mainSection.length) {
        $mainSection.css({
            "width": "100%",
            "max-width": "100%"
        });
    }

    /*
     * Dashboard itself.
     */
    $wrapper.css({
        "width": "100%",
        "max-width": "100%"
    });

    $wrapper
        .find(".mf-dashboard")
        .css({
            "width": "100%",
            "max-width": "100%"
        });

    $wrapper
        .find(".mf-table-wrap")
        .css({
            "width": "100%",
            "max-width": "100%"
        });

    $wrapper
        .find(".mf-table")
        .css({
            "width": "100%",
            "min-width": "1100px"
        });
}

function render_machine_file_dashboard(frm) {
    if (mf_has_period() && !frm.is_new()) {
        const period = mf_selected_period();
        const key = JSON.stringify([frm.doc.name, frm.doc.modified, period]);
        if (frm._mf_period_key !== key) {
            const wrapper = frm.fields_dict.index_dashboard.$wrapper;
            wrapper.empty().append($('<div class="text-muted"></div>').text(
                __("Loading records for the selected period...")
            ));
            if (frm._mf_period_pending === key) return;
            frm._mf_period_view = null;
            frm._mf_period_pending = key;
            frappe.call({
                method: "engineering.engineering.doctype.machine_file.machine_file.get_period_view",
                args: {name: frm.doc.name, period: JSON.stringify(period)},
                callback(r) {
                    if (frm._mf_period_pending !== key) return;
                    frm._mf_period_pending = null;
                    if (r.exc || !r.message) return;
                    frm._mf_period_view = r.message;
                    frm._mf_period_key = key;
                    frm._mf_period_rendering = true;
                    frm.trigger("refresh");
                },
                error() {
                    if (frm._mf_period_pending !== key) return;
                    frm._mf_period_pending = null;
                    wrapper.empty().append($('<div class="text-danger"></div>').text(
                        __("Could not load the selected period. Return to the register and check the filters.")
                    ));
                }
            });
            return;
        }
    }

    const field =
        frm.fields_dict.index_dashboard;

    if (!field) {
        return;
    }

    const $wrapper =
        field.$wrapper;

    if (!frm.doc.machine) {
        $wrapper.html(`
            <div
                style="
                    padding:30px;
                    text-align:center;
                    border:1px dashed #d1d5db;
                    border-radius:8px;
                    background:#fafafa;
                "
            >
                <div
                    style="
                        font-size:16px;
                        font-weight:600;
                        margin-bottom:6px;
                    "
                >
                    Select a Machine
                </div>

                <div
                    style="
                        color:#6b7280;
                    "
                >
                    The Machine File Index will populate automatically.
                </div>
            </div>
        `);

        return;
    }

    const rows = mf_has_period() && frm._mf_period_view
        ? frm._mf_period_view.rows : (frm.doc.index_items || []);

    let current = 0;
    let dueSoon = 0;
    let overdue = 0;
    let missing = 0;
    let erp = 0;

    rows.forEach(row => {
        const status =
            row.status || "Missing";

        if (status === "Current") {
            current++;
        } else if (
            status === "Due Soon"
        ) {
            dueSoon++;
        } else if (
            status === "Overdue"
        ) {
            overdue++;
        } else if (
            status === "ERP Records"
        ) {
            erp++;
        } else {
            missing++;
        }
    });

    const body = rows.map(
        row => {
            const status =
                row.status || "Missing";

            let erpButton = "";

            if (
                row.source_doctype
                && row.source_asset_field
            ) {
                erpButton = `
                    <button
                        type="button"
                        class="
                            btn
                            btn-xs
                            btn-default
                            mf-view-records
                        "
                        data-doctype="${
                            escape_html(
                                row.source_doctype
                            )
                        }"
                        data-field="${
                            escape_html(
                                row.source_asset_field
                            )
                        }"
                    >
                        View ERP Records
                    </button>
                `;
            }

            return `
                <tr>
                    <td
                        style="
                            width:65px;
                            font-weight:700;
                            vertical-align:middle;
                        "
                    >
                        ${escape_html(
                            row.index_no
                        )}
                    </td>

                    <td
                        style="
                            min-width:280px;
                            vertical-align:middle;
                        "
                    >
                        <div
                            style="
                                font-weight:600;
                            "
                        >
                            ${escape_html(
                                row.description
                            )}
                        </div>

                        ${
                            row.source_doctype
                            ? `
                                <div
                                    style="
                                        font-size:11px;
                                        color:#6b7280;
                                        margin-top:3px;
                                    "
                                >
                                    ERP Source:
                                    ${escape_html(
                                        row.source_doctype
                                    )}
                                </div>
                            `
                            : ""
                        }
                    </td>

                    <td
                        style="
                            vertical-align:middle;
                            white-space:nowrap;
                        "
                    >
                        ${
                            escape_html(
                                row.frequency
                            ) || "-"
                        }
                    </td>

                    <td
                        style="
                            vertical-align:middle;
                        "
                    >
                        ${status_badge(
                            status
                        )}
                    </td>

                    <td
                        style="
                            text-align:center;
                            vertical-align:middle;
                            font-weight:700;
                        "
                    >
                        ${
                            row.record_count || 0
                        }
                    </td>

                    <td
                        style="
                            vertical-align:middle;
                            white-space:nowrap;
                        "
                    >
                        ${format_date(
                            row.last_record_date
                        )}
                    </td>

                    <td
                        style="
                            vertical-align:middle;
                            white-space:nowrap;
                        "
                    >
                        ${format_date(
                            row.next_due_date
                        )}
                    </td>

                    <td
                        style="
                            min-width:210px;
                            vertical-align:middle;
                            white-space:nowrap;
                        "
                    >
                        ${erpButton}

                        <button
                            type="button"
                            class="
                                btn
                                btn-xs
                                btn-primary
                                mf-add-document
                            "
                            data-index="${
                                escape_html(
                                    row.index_no
                                )
                            }"
                            data-description="${
                                escape_html(
                                    row.description
                                )
                            }"
                            style="
                                margin-left:4px;
                            "
                        >
                            Add Document
                        </button>
                    </td>
                </tr>
            `;
        }
    ).join("");

    $wrapper.html(`
        <style>
            .mf-dashboard {
                margin-top: 8px;
            }

            .mf-summary {
                display: grid;
                grid-template-columns:
                    repeat(
                        5,
                        minmax(110px, 1fr)
                    );
                gap: 10px;
                margin-bottom: 14px;
            }

            .mf-card {
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 12px;
                background: #ffffff;
            }

            .mf-card-number {
                font-size: 22px;
                font-weight: 700;
                line-height: 1;
            }

            .mf-card-label {
                margin-top: 5px;
                color: #6b7280;
                font-size: 12px;
            }

            .mf-table-wrap {
                overflow-x: auto;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                background: #ffffff;
            }

            .mf-table {
                width: 100%;
                border-collapse: collapse;
                margin: 0;
            }

            .mf-table th {
                background: #f8f9fa;
                padding: 10px;
                border-bottom: 1px solid #e5e7eb;
                text-align: left;
                font-size: 12px;
                white-space: nowrap;
            }

            .mf-table td {
                padding: 10px;
                border-bottom: 1px solid #eeeeee;
                font-size: 13px;
            }

            .mf-table tr:last-child td {
                border-bottom: 0;
            }

            .mf-header {
                display:flex;
                justify-content:
                    space-between;
                align-items:center;
                gap:10px;
                margin-bottom:12px;
            }

            .mf-machine {
                font-size:18px;
                font-weight:700;
            }

            .mf-machine-detail {
                color:#6b7280;
                font-size:12px;
                margin-top:2px;
            }

            @media (
                max-width: 900px
            ) {
                .mf-summary {
                    grid-template-columns:
                        repeat(
                            2,
                            minmax(
                                110px,
                                1fr
                            )
                        );
                }
            }
        </style>

        <div class="mf-dashboard">

            <div class="mf-header">

                <div>
                    <div
                        class="mf-machine"
                    >
                        ${
                            escape_html(
                                frm.doc.machine
                            )
                        }
                        ${
                            frm.doc.machine_name
                            ? " - "
                                + escape_html(
                                    frm.doc.machine_name
                                )
                            : ""
                        }
                    </div>

                    <div
                        class="mf-machine-detail"
                    >
                        Site:
                        ${
                            escape_html(
                                frm.doc.site
                            ) || "-"
                        }
                        &nbsp; | &nbsp;
                        Category:
                        ${
                            escape_html(
                                frm.doc.machine_category
                            ) || "-"
                        }

                        &nbsp; | &nbsp;

                        Model:
                        ${
                            escape_html(
                                frm.doc.item_code
                            ) || "-"
                        }
                    </div>
                </div>

                <button
                    type="button"
                    class="
                        btn
                        btn-sm
                        btn-primary
                        mf-refresh-file
                    "
                    ${
                        frm.is_new()
                        ? "disabled"
                        : ""
                    }
                >
                    Refresh Machine File
                </button>

            </div>

            <div class="mf-summary">

                <div class="mf-card">
                    <div
                        class="mf-card-number"
                    >
                        ${current}
                    </div>
                    <div
                        class="mf-card-label"
                    >
                        Current
                    </div>
                </div>

                <div class="mf-card">
                    <div
                        class="mf-card-number"
                    >
                        ${erp}
                    </div>
                    <div
                        class="mf-card-label"
                    >
                        ERP Records
                    </div>
                </div>

                <div class="mf-card">
                    <div
                        class="mf-card-number"
                    >
                        ${dueSoon}
                    </div>
                    <div
                        class="mf-card-label"
                    >
                        Due Soon
                    </div>
                </div>

                <div class="mf-card">
                    <div
                        class="mf-card-number"
                    >
                        ${overdue}
                    </div>
                    <div
                        class="mf-card-label"
                    >
                        Overdue
                    </div>
                </div>

                <div class="mf-card">
                    <div
                        class="mf-card-number"
                    >
                        ${missing}
                    </div>
                    <div
                        class="mf-card-label"
                    >
                        ${mf_has_period() ? "No records in period" : "Missing"}
                    </div>
                </div>

            </div>

            <div class="mf-table-wrap">

                <table class="mf-table">

                    <thead>
                        <tr>
                            <th>No.</th>
                            <th>
                                Machine File Section
                            </th>
                            <th>Frequency</th>
                            <th>Status</th>
                            <th>Records</th>
                            <th>Last Record</th>
                            <th>Next Due</th>
                            <th>Action</th>
                        </tr>
                    </thead>

                    <tbody>
                        ${body}
                    </tbody>

                </table>

            </div>

        </div>
    `);


    if (mf_has_period()) {
        const period = mf_selected_period();
        const description = [
            ...(period.labels || []),
            period.from_date ? __("From") + " " + frappe.datetime.str_to_user(period.from_date) : "",
            period.to_date ? __("To") + " " + frappe.datetime.str_to_user(period.to_date) : ""
        ].filter(Boolean).join(" | ");
        $wrapper.prepend($('<div class="alert alert-info"></div>').text(
            __("Selected period") + ": " + description + ". " +
            __("Dates and counts reflect this period; expiry status is evaluated today.")
        ));
        $wrapper.find(".mf-view-records").hide();
    }

    $wrapper
        .find(".mf-refresh-file")
        .on(
            "click",
            function() {
                refresh_machine_file(frm);
            }
        );


    $wrapper
        .find(".mf-view-records")
        .on(
            "click",
            function() {
                const doctype =
                    $(this).data(
                        "doctype"
                    );

                const field =
                    $(this).data(
                        "field"
                    );

                if (
                    !doctype
                    || !field
                    || !frm.doc.machine
                ) {
                    return;
                }

                frappe.route_options = {
                    [field]:
                        frm.doc.machine
                };

                frappe.set_route(
                    "List",
                    doctype
                );
            }
        );


    $wrapper
        .find(".mf-add-document")
        .on(
            "click",
            function() {
                const indexNo =
                    String(
                        $(this).data(
                            "index"
                        )
                    );

                const description =
                    $(this).data(
                        "description"
                    );

                const row =
                    frm.add_child(
                        "documents"
                    );

                row.index_no =
                    indexNo;

                row.document_type =
                    description;

                row.document_date =
                    frappe.datetime
                        .get_today();

                frm.refresh_field(
                    "documents"
                );

                const docField =
                    frm.fields_dict
                        .documents;

                if (
                    docField
                    && docField.$wrapper
                    && docField.$wrapper[0]
                ) {
                    docField
                        .$wrapper[0]
                        .scrollIntoView({
                            behavior:
                                "smooth",
                            block:
                                "center"
                        });
                }

                frappe.show_alert({
                    message:
                        __(
                            "Document row added for Index {0}",
                            [indexNo]
                        ),
                    indicator:
                        "blue"
                });
            }
        );
}


function refresh_machine_file(frm) {
    if (frm.is_new()) {
        frappe.msgprint(
            __(
                "Please save the Machine File first."
            )
        );

        return;
    }

    frappe.call({
        method:
            "engineering.engineering.doctype.machine_file.machine_file.refresh_machine_file",
        args: {
            name: frm.doc.name
        },
        freeze: true,
        freeze_message:
            __(
                "Refreshing Machine File..."
            ),
        callback(r) {
            if (!r.exc) {
                frm.reload_doc();

                frappe.show_alert({
                    message:
                        __(
                            "Machine File refreshed"
                        ),
                    indicator:
                        "green"
                });
            }
        }
    });
}




function set_machine_file_clean_layout(frm) {
    /*
     * Saved Machine Files are opened from the fleet register,
     * so the Asset selection/details fields are not required
     * on the normal Machine File screen.
     *
     * Keep them visible only while creating a new document.
     */

    const show_selection = frm.is_new();

    const fields = [
        "filter_section",
        "site",
        "machine_category",
        "machine",
        "asset_details_section",
        "machine_name",
        "item_code",
        "serial_no",
        "refresh_index",
        "last_refreshed"
    ];

    fields.forEach(fieldname => {
        if (frm.fields_dict[fieldname]) {
            frm.toggle_display(
                fieldname,
                show_selection
            );
        }
    });
}

frappe.ui.form.on(
    "Machine File",
    {

        setup(frm) {
            apply_machine_filter(
                frm
            );
        },

        refresh(frm) {
            if (frm._mf_period_rendering) {
                frm._mf_period_rendering = false;
            } else {
                frm._mf_period_key = null;
            }
            apply_machine_filter(
                frm
            );

            set_machine_file_clean_layout(
                frm
            );

            render_machine_file_dashboard(
                frm
            );
            setTimeout(function() {
                set_machine_file_full_width(frm);
            }, 100);

            if (
                !frm.is_new()
                && frm.doc.machine
            ) {
                frm.add_custom_button(
                    __("Open Asset"),
                    function() {
                        frappe.set_route(
                            "Form",
                            "Asset",
                            frm.doc.machine
                        );
                    },
                    __("Machine")
                );

                frm.add_custom_button(
                    __("Refresh Machine File"),
                    function() {
                        refresh_machine_file(
                            frm
                        );
                    },
                    __("Machine")
                );
            }
        },

        site(frm) {
            apply_machine_filter(
                frm
            );
        },

        machine_category(frm) {
            apply_machine_filter(
                frm
            );
        },

        machine(frm) {
            if (!frm.doc.machine) {
                frm.set_value(
                    "machine_name",
                    ""
                );

                frm.set_value(
                    "item_code",
                    ""
                );

                frm.set_value(
                    "serial_no",
                    ""
                );

                frm.clear_table(
                    "index_items"
                );

                frm.refresh_field(
                    "index_items"
                );

                render_machine_file_dashboard(
                    frm
                );

                return;
            }

            frappe.db.get_value(
                "Asset",
                frm.doc.machine,
                [
                    "asset_name",
                    "asset_category",
                    "location",
                    "item_code"
                ]
            ).then(r => {
                if (!r.message) {
                    return;
                }

                frm.set_value(
                    "machine_name",
                    r.message.asset_name
                    || ""
                );

                frm.set_value(
                    "machine_category",
                    r.message.asset_category
                    || ""
                );

                frm.set_value(
                    "site",
                    r.message.location
                    || ""
                );

                frm.set_value(
                    "item_code",
                    r.message.item_code
                    || ""
                );

                frm.set_value(
                    "serial_no",
                    ""
                );

                populate_machine_file_index(
                    frm
                );
            });
        },

        refresh_index(frm) {
            refresh_machine_file(
                frm
            );
        },

        documents_add(frm) {
            render_machine_file_dashboard(
                frm
            );
        },

        documents_remove(frm) {
            render_machine_file_dashboard(
                frm
            );
        }
    }
);



// MACHINE FILE ALL SECTION ACCORDION START

(function () {

    function mfsec_escape(value) {
        return frappe.utils.escape_html(
            String(value || "")
        );
    }


    function mfsec_date(value) {
        if (!value) {
            return "-";
        }

        try {
            return frappe.datetime.str_to_user(
                value
            );
        } catch (e) {
            return value;
        }
    }


    function mfsec_status(status) {

        const map = {
            "Submitted": {
                bg: "#d1f4dd",
                fg: "#137333"
            },

            "Draft": {
                bg: "#fff3cd",
                fg: "#8a6116"
            },

            "Cancelled": {
                bg: "#f8d7da",
                fg: "#b42318"
            },

            "Open": {
                bg: "#fff3cd",
                fg: "#8a6116"
            },

            "Closed": {
                bg: "#d1f4dd",
                fg: "#137333"
            }
        };

        const style =
            map[status]
            || {
                bg: "#eeeeee",
                fg: "#5f6368"
            };

        if (!status) {
            return "-";
        }

        return `
            <span style="
                display:inline-block;
                padding:4px 9px;
                border-radius:12px;
                background:${style.bg};
                color:${style.fg};
                font-size:11px;
                font-weight:600;
                white-space:nowrap;
            ">
                ${mfsec_escape(status)}
            </span>
        `;
    }


    

function mfsec_private_download_url(file_url) {
    const url = String(
        file_url || ""
    ).trim();

    if (!url) {
        return "#";
    }

    /*
     * Public files continue to open normally.
     */
    if (
        !url.startsWith(
            "/private/files/"
        )
    ) {
        return url;
    }

    /*
     * Private Machine File / Engineering Legals documents
     * go through our own authenticated endpoint.
     */
    return (
        "/api/method/"
        + "engineering.engineering.doctype."
        + "machine_file.machine_file."
        + "open_machine_file_attachment"
        + "?file_url="
        + encodeURIComponent(
            url
        )
    );
}


function mfsec_attachments(files) {

        if (
            !files
            || !files.length
        ) {
            return "-";
        }

        return files
            .map(function (file) {

                return `
                    <a
                        href="${
                            mfsec_escape(mfsec_private_download_url(file.file_url))
                        }"
                        target="_blank"
                        rel="noopener noreferrer"
                        style="
                            display:block;
                            margin-bottom:4px;
                        "
                    >
                        📎 ${
                            mfsec_escape(
                                file.file_name
                            )
                        }
                    </a>
                `;
            })
            .join("");
    }


    function mfsec_add_document(
        frm,
        data,
        $content
    ) {
        window.mfdoc_open_dialog(
            frm,
            String(
                data.index_no
            ),
            data.description
            || "Machine File Document"
        );
    }


    function mfsec_new_movement(
        frm,
        movement_data
    ) {

        frappe.new_doc(
            "Asset Movement",
            {},
            function (doc) {

                if (
                    movement_data
                    && movement_data
                        .child_table_field
                    && movement_data
                        .asset_field
                ) {

                    const row =
                        frappe.model
                            .add_child(
                                doc,
                                "Asset Movement Item",
                                movement_data
                                    .child_table_field
                            );

                    frappe.model
                        .set_value(
                            row.doctype,
                            row.name,
                            movement_data
                                .asset_field,
                            frm.doc.machine
                        );
                }
            }
        );
    }


    function mfsec_render_movement(
        frm,
        data
    ) {

        const movement =
            data.movement || {};

        const rows =
            movement.rows || [];

        let html = "";


        if (rows.length) {

            let body = "";

            rows.forEach(function (row) {

                body += `
                    <tr>

                        <td>
                            <button
                                type="button"
                                class="
                                    btn
                                    btn-link
                                    btn-xs
                                    mfsec-open-record
                                "
                                data-doctype="
                                    Asset Movement
                                "
                                data-name="${
                                    mfsec_escape(
                                        row.name
                                    )
                                }"
                                style="
                                    padding:0;
                                    font-weight:700;
                                "
                            >
                                ${
                                    mfsec_escape(
                                        row.name
                                    )
                                }
                            </button>
                        </td>

                        <td>
                            ${
                                mfsec_date(
                                    row.date
                                )
                            }
                        </td>

                        <td>
                            ${
                                mfsec_escape(
                                    row.purpose
                                ) || "-"
                            }
                        </td>

                        <td>
                            ${
                                mfsec_escape(
                                    row.from_location
                                ) || "-"
                            }
                        </td>

                        <td>
                            ${
                                mfsec_escape(
                                    row.to_location
                                ) || "-"
                            }
                        </td>

                        <td>
                            ${
                                mfsec_escape(
                                    row.from_employee
                                ) || "-"
                            }
                        </td>

                        <td>
                            ${
                                mfsec_escape(
                                    row.to_employee
                                ) || "-"
                            }
                        </td>

                        <td>
                            ${
                                mfsec_status(
                                    row.status
                                )
                            }
                        </td>

                        <td>
                            ${
                                mfsec_attachments(
                                    row.attachments
                                )
                            }
                        </td>

                    </tr>
                `;
            });


            html += `
                <div
                    class="
                        mfsec-table-wrap
                    "
                >
                    <table
                        class="
                            mfsec-detail-table
                        "
                        style="
                            min-width:1200px;
                        "
                    >
                        <thead>
                            <tr>
                                <th>Movement</th>
                                <th>Date</th>
                                <th>Purpose</th>
                                <th>From Location</th>
                                <th>To Location</th>
                                <th>From Employee</th>
                                <th>To Employee</th>
                                <th>Status</th>
                                <th>Attachment</th>
                            </tr>
                        </thead>

                        <tbody>
                            ${body}
                        </tbody>
                    </table>
                </div>
            `;

        } else {

            html += `
                <div
                    class="
                        mfsec-empty
                    "
                >
                    No machine movement captured.
                </div>
            `;
        }


        if (
            movement.can_create
        ) {

            html += `
                <div style="
                    margin-top:12px;
                ">
                    <button
                        type="button"
                        class="
                            btn
                            btn-sm
                            btn-primary
                            mfsec-add-movement
                        "
                    >
                        + Add Machine Movement
                    </button>
                </div>
            `;
        }

        return html;
    }


    function mfsec_render_erp(
        data
    ) {

        const rows =
            data.source_records || [];

        if (!rows.length) {
            return "";
        }

        let body = "";

        rows.forEach(function (row) {

            body += `
                <tr>

                    <td>
                        <button
                            type="button"
                            class="
                                btn
                                btn-link
                                btn-xs
                                mfsec-open-record
                            "
                            data-doctype="${
                                mfsec_escape(
                                    data.source_doctype
                                )
                            }"
                            data-name="${
                                mfsec_escape(
                                    row.name
                                )
                            }"
                            style="
                                padding:0;
                                font-weight:700;
                            "
                        >
                            ${
                                mfsec_escape(
                                    row.name
                                )
                            }
                        </button>
                    </td>

                    <td>
                        ${
                            mfsec_date(
                                row.date
                            )
                        }
                    </td>

                    <td>
                        ${
                            mfsec_status(
                                row.status
                            )
                        }
                    </td>

                    <td>
                        ${
                            mfsec_escape(
                                row.purpose
                            ) || "-"
                        }
                    </td>

                    <td>
                        ${
                            mfsec_escape(
                                row.remarks
                            ) || "-"
                        }
                    </td>

                    <td>
                        ${
                            mfsec_attachments(
                                row.attachments
                            )
                        }
                    </td>

                </tr>
            `;
        });


        return `
            <div
                style="
                    font-weight:700;
                    margin-bottom:8px;
                "
            >
                ERP Records
                ${
                    data.source_doctype
                        ? " - "
                            + mfsec_escape(
                                data.source_doctype
                            )
                        : ""
                }
            </div>

            <div
                class="
                    mfsec-table-wrap
                "
            >
                <table
                    class="
                        mfsec-detail-table
                    "
                >
                    <thead>
                        <tr>
                            <th>Record</th>
                            <th>Date</th>
                            <th>Status</th>
                            <th>Purpose</th>
                            <th>Details</th>
                            <th>Attachment</th>
                        </tr>
                    </thead>

                    <tbody>
                        ${body}
                    </tbody>
                </table>
            </div>
        `;
    }


    function mfsec_render_documents(
        data
    ) {

        const rows =
            data.manual_documents || [];

        if (!rows.length) {
            return "";
        }

        let body = "";

        rows.forEach(function (row) {

            const attachment =
                row.attachment
                    ? `
                        <a
                            href="${
                                mfsec_escape(mfsec_private_download_url(row.attachment))
                            }"
                            target="_blank"
                            rel="noopener noreferrer"
                        >
                            📎 Open Attachment
                        </a>
                    `
                    : "-";


            body += `
                <tr>

                    <td>
                        ${
                            mfsec_escape(
                                row.document_type
                            )
                        }
                    </td>

                    <td>
                        ${
                            mfsec_date(
                                row.document_date
                            )
                        }
                    </td>

                    <td>
                        ${
                            mfsec_date(
                                row.expiry_date
                            )
                        }
                    </td>

                    <td>
                        ${attachment}
                    </td>

                    <td>
                        ${
                            mfsec_escape(
                                row.notes
                            ) || "-"
                        }
                    </td>

                </tr>
            `;
        });


        return `
            <div
                style="
                    font-weight:700;
                    margin-top:14px;
                    margin-bottom:8px;
                "
            >
                Machine File Documents
            </div>

            <div
                class="
                    mfsec-table-wrap
                "
            >
                <table
                    class="
                        mfsec-detail-table
                    "
                >
                    <thead>
                        <tr>
                            <th>Document / Report</th>
                            <th>Document Date</th>
                            <th>Expiry / Next Due</th>
                            <th>Attachment</th>
                            <th>Notes</th>
                        </tr>
                    </thead>

                    <tbody>
                        ${body}
                    </tbody>
                </table>
            </div>
        `;
    }


    function mfsec_render(
        frm,
        $content,
        data
    ) {
        if (data.period_filtered && !(data.source_records || []).length &&
                !(data.manual_documents || []).length && !((data.movement || {}).rows || []).length) {
            $content.empty().append($('<div class="text-muted p-3"></div>').text(
                __("No records for the selected period.")
            ));
            return;
        }


        const has_movement =
            data.movement
            && (
                (
                    data.movement.rows
                    || []
                ).length
                || data.movement
                    .can_create
            );

        const has_erp =
            (
                data.source_records
                || []
            ).length > 0;

        const has_documents =
            (
                data.manual_documents
                || []
            ).length > 0;


        let body = "";


        if (data.index_no === "1") {
            body += (
                mfsec_render_movement(
                    frm,
                    data
                )
            );
        }


        if (
            data.index_no !== "1"
            && has_erp
        ) {
            body += (
                mfsec_render_erp(
                    data
                )
            );
        }


        if (has_documents) {
            body += (
                mfsec_render_documents(
                    data
                )
            );
        }


        if (
            !has_movement
            && !has_erp
            && !has_documents
        ) {

            body += `
                <div
                    class="
                        mfsec-empty
                    "
                >
                    No records captured for this section.
                </div>
            `;
        }


        let buttons = "";


        if (
            data.source_doctype
            && data.source_asset_field
        ) {

            buttons += `
                <button
                    type="button"
                    class="
                        btn
                        btn-sm
                        btn-default
                        mfsec-view-erp
                    "
                >
                    View ERP Records
                </button>
            `;
        }


        if (
            data.can_add_document
        ) {

            buttons += `
                <button
                    type="button"
                    class="
                        btn
                        btn-sm
                        btn-primary
                        mfsec-add-document
                    "
                >
                    + Add Document
                </button>
            `;
        }


        $content.html(`
            <style>
                .mfsec-panel {
                    padding:14px;
                    background:#f8f9fa;
                    border:1px solid #dfe3e8;
                    border-radius:7px;
                }

                .mfsec-header {
                    display:flex;
                    align-items:center;
                    justify-content:
                        space-between;
                    gap:10px;
                    flex-wrap:wrap;
                    margin-bottom:12px;
                }

                .mfsec-title {
                    font-size:15px;
                    font-weight:700;
                }

                .mfsec-meta {
                    font-size:12px;
                    color:#6b7280;
                    margin-top:3px;
                }

                .mfsec-actions {
                    display:flex;
                    gap:6px;
                    flex-wrap:wrap;
                }

                .mfsec-table-wrap {
                    width:100%;
                    overflow-x:auto;
                    background:#fff;
                    border:1px solid #e5e7eb;
                    border-radius:6px;
                }

                .mfsec-detail-table {
                    width:100%;
                    min-width:800px;
                    border-collapse:collapse;
                }

                .mfsec-detail-table th {
                    padding:9px;
                    text-align:left;
                    background:#eef3f8;
                    border-bottom:
                        1px solid #dfe3e8;
                    white-space:nowrap;
                }

                .mfsec-detail-table td {
                    padding:9px;
                    border-bottom:
                        1px solid #e5e7eb;
                    vertical-align:top;
                }

                .mfsec-detail-table
                tr:last-child td {
                    border-bottom:0;
                }

                .mfsec-empty {
                    padding:18px;
                    background:#fff;
                    border:1px dashed #d1d5db;
                    border-radius:6px;
                    color:#6b7280;
                }
            </style>

            <div class="mfsec-panel">

                <div class="mfsec-header">

                    <div>
                        <div
                            class="mfsec-title"
                        >
                            ${
                                mfsec_escape(
                                    data.index_no
                                )
                            }.
                            ${
                                mfsec_escape(
                                    data.description
                                )
                            }
                        </div>

                        <div
                            class="mfsec-meta"
                        >
                            Machine:
                            <b>
                                ${
                                    mfsec_escape(
                                        data.machine
                                    )
                                }
                            </b>

                            ${
                                data.frequency
                                    ? `
                                        &nbsp; | &nbsp;
                                        Frequency:
                                        <b>
                                            ${
                                                mfsec_escape(
                                                    data.frequency
                                                )
                                            }
                                        </b>
                                    `
                                    : ""
                            }
                        </div>
                    </div>

                    <div
                        class="mfsec-actions"
                    >
                        ${buttons}
                    </div>

                </div>

                ${body}

            </div>
        `);


        $content
            .off(
                ".mfsecActions"
            )


            .on(
                "click.mfsecActions",
                ".mfsec-open-record",
                function () {

                    const doctype =
                        $(this).data(
                            "doctype"
                        );

                    const name =
                        $(this).data(
                            "name"
                        );

                    if (
                        doctype
                        && name
                    ) {
                        frappe.set_route(
                            "Form",
                            doctype,
                            name
                        );
                    }
                }
            )


            .on(
                "click.mfsecActions",
                ".mfsec-view-erp",
                function () {

                    if (
                        !data.source_doctype
                        || !data
                            .source_asset_field
                    ) {
                        return;
                    }

                    frappe.route_options = {
                        [data.source_asset_field]:
                            frm.doc.machine
                    };

                    frappe.set_route(
                        "List",
                        data.source_doctype
                    );
                }
            )


            .on(
                "click.mfsecActions",
                ".mfsec-add-document",
                function () {

                    mfsec_add_document(
                        frm,
                        data,
                        $content
                    );
                }
            )


            .on(
                "click.mfsecActions",
                ".mfsec-add-movement",
                function () {

                    mfsec_new_movement(
                        frm,
                        data.movement
                    );
                }
            );
    }


    function mfsec_load_section(
        frm,
        index_no,
        $content
    ) {

        // MACHINE FILE MOVEMENT SPECIAL CALL
        if (
            String(index_no) === "1"
            && window.mfmv_load_movement_section
        ) {
            window.mfmv_load_movement_section(
                frm,
                $content
            );
            return;
        }



        // MACHINE FILE BREAKDOWN SPECIAL CALL
        if (
            String(index_no) === "11"
            && window.mfbd_load_breakdown_log
        ) {
            window.mfbd_load_breakdown_log(
                frm,
                $content
            );

            return;
        }



        $content.html(`
            <div style="
                padding:20px;
                color:#6b7280;
            ">
                Loading section records...
            </div>
        `);


        mf_period_call(frm, {

            method:
                "engineering.engineering.doctype.machine_file.machine_file.get_machine_file_section_details",

            args: {
                name:
                    frm.doc.name,

                index_no:
                    index_no
            },

            callback(r) {

                if (r.exc) {

                    $content.html(`
                        <div
                            class="
                                alert
                                alert-danger
                            "
                        >
                            Could not load this
                            Machine File section.
                        </div>
                    `);

                    return;
                }


                const data =
                    r.message || {};


                $content.data(
                    "loaded",
                    true
                );


                mfsec_render(
                    frm,
                    $content,
                    data
                );
            }
        });
    }


    function mfsec_install(frm) {

        if (
            !frm
            || frm.is_new()
            || !frm.doc.machine
        ) {
            return;
        }


        const field =
            frm.fields_dict
                .index_dashboard;


        if (
            !field
            || !field.$wrapper
        ) {
            return;
        }


        const $dashboard =
            field.$wrapper;


        const description_map = {};

        (
            frm.doc.index_items
            || []
        ).forEach(function (row) {

            description_map[
                String(
                    row.index_no
                )
            ] = row.description;
        });


        $dashboard
            .find(
                ".mf-table tbody tr"
            )
            .not(
                ".mfsec-detail-row"
            )
            .each(function () {

                const $row =
                    $(this);

                const $cells =
                    $row.children(
                        "td"
                    );


                if (
                    $cells.length < 2
                ) {
                    return;
                }


                const index_no =
                    $cells
                        .eq(0)
                        .text()
                        .trim();


                if (
                    !index_no
                    || !description_map[
                        index_no
                    ]
                ) {
                    return;
                }


                const description =
                    description_map[
                        index_no
                    ];


                const $description =
                    $cells.eq(1);


                $description.html(`
                    <button
                        type="button"
                        class="
                            btn
                            btn-link
                            mfsec-toggle
                        "
                        data-index="${
                            mfsec_escape(
                                index_no
                            )
                        }"
                        style="
                            padding:0;
                            text-align:left;
                            font-weight:700;
                            text-decoration:none;
                        "
                    >

                        <span
                            class="
                                mfsec-arrow
                            "
                            style="
                                display:inline-block;
                                width:18px;
                            "
                        >
                            ▶
                        </span>

                        ${
                            mfsec_escape(
                                description
                            )
                        }

                    </button>
                `);


                let $detail =
                    $row.next(
                        ".mfsec-detail-row"
                    );


                if (!$detail.length) {

                    $detail = $(`
                        <tr
                            class="
                                mfsec-detail-row
                            "
                            style="
                                display:none;
                            "
                        >
                            <td
                                colspan="8"
                                style="
                                    padding:
                                    12px 16px;
                                    background:#fff;
                                "
                            >
                                <div
                                    class="
                                        mfsec-content
                                    "
                                ></div>
                            </td>
                        </tr>
                    `);


                    $detail.insertAfter(
                        $row
                    );
                }
            });


        $dashboard
            .off(
                "click.mfsecAccordion"
            )


            .on(
                "click.mfsecAccordion",
                ".mfsec-toggle",
                function () {

                    const $button =
                        $(this);

                    const index_no =
                        String(
                            $button.data(
                                "index"
                            )
                        );

                    const $row =
                        $button.closest(
                            "tr"
                        );

                    const $detail =
                        $row.next(
                            ".mfsec-detail-row"
                        );

                    const $arrow =
                        $button.find(
                            ".mfsec-arrow"
                        );


                    if (
                        $detail.is(
                            ":visible"
                        )
                    ) {

                        $detail.hide();

                        $arrow.text(
                            "▶"
                        );

                        return;
                    }


                    $detail.show();

                    $arrow.text(
                        "▼"
                    );


                    const $content =
                        $detail.find(
                            ".mfsec-content"
                        );


                    if (
                        $content.data(
                            "loaded"
                        )
                    ) {
                        return;
                    }


                    mfsec_load_section(
                        frm,
                        index_no,
                        $content
                    );
                }
            );
    }


    frappe.ui.form.on(
        "Machine File",
        {

            refresh(frm) {

                setTimeout(
                    function () {

                        mfsec_install(
                            frm
                        );

                    },
                    300
                );
            },


            onload_post_render(frm) {

                setTimeout(
                    function () {

                        mfsec_install(
                            frm
                        );

                    },
                    400
                );
            }
        }
    );

})();

// MACHINE FILE ALL SECTION ACCORDION END



// MACHINE FILE HIDE MAIN ACTION COLUMN START

(function () {

    function mf_hide_main_action_column(frm) {

        if (
            !frm
            || !frm.fields_dict
            || !frm.fields_dict.index_dashboard
            || !frm.fields_dict.index_dashboard.$wrapper
        ) {
            return;
        }

        const $wrapper =
            frm.fields_dict
                .index_dashboard
                .$wrapper;

        const $table =
            $wrapper
                .find(".mf-table")
                .first();

        if (!$table.length) {
            return;
        }

        /*
         * Find the column labelled Action.
         */
        let actionIndex = -1;

        $table
            .find("thead th")
            .each(function (index) {

                const text =
                    $(this)
                        .text()
                        .trim()
                        .toLowerCase();

                if (text === "action") {
                    actionIndex = index;
                    $(this).hide();
                }
            });


        if (actionIndex === -1) {
            return;
        }


        /*
         * Hide Action cell on normal Machine File rows.
         * Do NOT hide cells inside expanded detail sections.
         */
        $table
            .find("tbody > tr")
            .not(
                ".mfsec-detail-row, " +
                ".mfma-detail-row, " +
                ".mf-movement-detail-row, " +
                ".mf-registration-detail-row"
            )
            .each(function () {

                $(this)
                    .children("td")
                    .eq(actionIndex)
                    .hide();
            });


        /*
         * Expanded sections now span 7 visible columns.
         */
        $table
            .find(
                ".mfsec-detail-row > td, " +
                ".mfma-detail-row > td, " +
                ".mf-movement-detail-row > td, " +
                ".mf-registration-detail-row > td"
            )
            .attr(
                "colspan",
                "7"
            );
    }


    frappe.ui.form.on(
        "Machine File",
        {

            refresh(frm) {

                setTimeout(
                    function () {
                        mf_hide_main_action_column(
                            frm
                        );
                    },
                    350
                );

                setTimeout(
                    function () {
                        mf_hide_main_action_column(
                            frm
                        );
                    },
                    800
                );
            },


            onload_post_render(frm) {

                setTimeout(
                    function () {
                        mf_hide_main_action_column(
                            frm
                        );
                    },
                    450
                );
            }
        }
    );

})();

// MACHINE FILE HIDE MAIN ACTION COLUMN END



// MACHINE FILE BREAKDOWN REASONS UI START

(function () {

    function mfbd_escape(value) {
        return frappe.utils.escape_html(
            String(value || "")
        );
    }


    function mfbd_datetime(value) {

        if (!value) {
            return "-";
        }

        let text = String(
            value
        ).replace(
            "T",
            " "
        );

        if (text.length >= 16) {
            text = text.slice(
                0,
                16
            );
        }

        return mfbd_escape(
            text
        );
    }


    function mfbd_minutes(value) {

        let minutes = parseInt(
            value || 0,
            10
        );

        if (
            !Number.isFinite(minutes)
            || minutes < 0
        ) {
            minutes = 0;
        }

        const hours = Math.floor(
            minutes / 60
        );

        const remainder =
            minutes % 60;

        if (
            hours
            && remainder
        ) {
            return (
                `${hours}h ${remainder}m`
            );
        }

        if (hours) {
            return `${hours}h`;
        }

        return `${remainder}m`;
    }


    function mfbd_add_document(
        frm,
        $container
    ) {
        window.mfdoc_open_dialog(
            frm,
            "11",
            "Breakdown Log Sheet"
        );
    }


    function mfbd_render_table(
        frm,
        data
    ) {

        const rows =
            data.rows || [];

        const totals =
            data.totals || {};

        let body = "";


        if (!rows.length) {

            body = `
                <tr>
                    <td
                        colspan="7"
                        style="
                            padding:20px;
                            text-align:center;
                            color:#6b7280;
                        "
                    >
                        ${mf_has_period() ? "No records for the selected period." :
                            "No qualifying breakdown or maintenance records found."}
                    </td>
                </tr>
            `;

        } else {

            rows.forEach(
                function (row) {

                    body += `
                        <tr>

                            <td>
                                ${
                                    mfbd_datetime(
                                        row.start_datetime
                                    )
                                }
                            </td>

                            <td>
                                ${
                                    mfbd_datetime(
                                        row.resolved_datetime
                                    )
                                }
                            </td>

                            <td
                                style="
                                    font-weight:600;
                                "
                            >
                                ${
                                    mfbd_minutes(
                                        row.total_minutes
                                    )
                                }
                            </td>

                            <td
                                style="
                                    color:#c2410c;
                                    font-weight:700;
                                "
                            >
                                ${
                                    mfbd_minutes(
                                        row.startup_fatigue_minutes
                                    )
                                }
                            </td>

                            <td
                                style="
                                    color:#7c3aed;
                                    font-weight:700;
                                "
                            >
                                ${
                                    mfbd_minutes(
                                        row.sunday_minutes
                                    )
                                }
                            </td>

                            <td
                                style="
                                    color:#047857;
                                    font-weight:700;
                                "
                            >
                                ${
                                    mfbd_minutes(
                                        row.au_minutes
                                    )
                                }
                            </td>

                            <td>
                                ${
                                    mfbd_escape(
                                        row.reason
                                    ) || "-"
                                }
                            </td>

                        </tr>
                    `;
                }
            );
        }


        return `
            <div
                class="
                    mfbd-reason-box
                "
            >

                <div
                    class="
                        mfbd-reason-title
                    "
                >
                    Breakdown Reasons for
                    ${
                        mfbd_escape(
                            data.machine
                            || frm.doc.machine
                        )
                    }
                </div>


                <div
                    style="
                        width:100%;
                        overflow-x:auto;
                    "
                >

                    <table
                        class="
                            mfbd-reason-table
                        "
                    >

                        <thead>
                            <tr>

                                <th>
                                    Start
                                </th>

                                <th>
                                    Resolved
                                </th>

                                <th>
                                    Total Time
                                </th>

                                <th>
                                    Start-up + Fatigue
                                </th>

                                <th>
                                    Sunday Hours
                                </th>

                                <th>
                                    A&amp;U Time
                                </th>

                                <th>
                                    Reason
                                </th>

                            </tr>
                        </thead>


                        <tbody>

                            ${body}

                            ${
                                rows.length
                                    ? `
                                        <tr
                                            class="
                                                mfbd-total-row
                                            "
                                        >

                                            <td
                                                colspan="2"
                                                style="
                                                    text-align:right;
                                                "
                                            >
                                                Totals
                                            </td>

                                            <td>
                                                ${
                                                    mfbd_minutes(
                                                        totals.total_minutes
                                                    )
                                                }
                                            </td>

                                            <td
                                                style="
                                                    color:#c2410c;
                                                "
                                            >
                                                ${
                                                    mfbd_minutes(
                                                        totals
                                                        .startup_fatigue_minutes
                                                    )
                                                }
                                            </td>

                                            <td
                                                style="
                                                    color:#7c3aed;
                                                "
                                            >
                                                ${
                                                    mfbd_minutes(
                                                        totals.sunday_minutes
                                                    )
                                                }
                                            </td>

                                            <td
                                                style="
                                                    color:#047857;
                                                "
                                            >
                                                ${
                                                    mfbd_minutes(
                                                        totals.au_minutes
                                                    )
                                                }
                                            </td>

                                            <td></td>

                                        </tr>
                                    `
                                    : ""
                            }

                        </tbody>

                    </table>

                </div>

            </div>
        `;
    }


    function mfbd_render(
        frm,
        $container,
        data
    ) {

        const count =
            (
                data.rows || []
            ).length;

        const tableHtml =
            mfbd_render_table(
                frm,
                data
            );


        $container.html(`
            <style>

                .mfbd-toolbar {
                    display:flex;
                    align-items:center;
                    justify-content:flex-end;
                    gap:8px;
                    flex-wrap:wrap;
                    margin-bottom:10px;
                }


                .mfbd-reason-box {
                    border:
                        1px solid #3b82f6;

                    border-radius:
                        8px;

                    overflow:
                        hidden;

                    background:
                        #ffffff;
                }


                .mfbd-reason-title {
                    padding:
                        11px 12px;

                    background:
                        #dbeafe;

                    color:
                        #1d4ed8;

                    font-weight:
                        700;
                }


                .mfbd-reason-table {
                    width:
                        100%;

                    min-width:
                        1000px;

                    border-collapse:
                        collapse;
                }


                .mfbd-reason-table th {
                    padding:
                        10px 9px;

                    text-align:
                        left;

                    color:
                        #1d4ed8;

                    background:
                        #eff6ff;

                    border-bottom:
                        1px solid #dbeafe;

                    white-space:
                        nowrap;
                }


                .mfbd-reason-table td {
                    padding:
                        10px 9px;

                    border-bottom:
                        1px solid #dbeafe;

                    vertical-align:
                        top;
                }


                .mfbd-total-row td {
                    background:
                        #eaf3ff;

                    color:
                        #1d4ed8;

                    font-weight:
                        700;
                }

            </style>


            <div
                class="
                    mfbd-toolbar
                "
            >

                <button
                    type="button"
                    class="
                        btn
                        btn-sm
                        btn-default
                        mfbd-toggle-reasons
                    "
                >
                    <span
                        class="
                            mfbd-toggle-arrow
                        "
                    >
                        ▶
                    </span>

                    Breakdown Reasons
                    (${count})
                </button>


                <button
                    type="button"
                    class="
                        btn
                        btn-sm
                        btn-primary
                        mfbd-add-document
                    "
                >
                    + Add Document
                </button>

            </div>


            <div
                class="
                    mfbd-table-container
                "
                style="
                    display:none;
                "
            >
                ${tableHtml}
            </div>
        `);


        $container
            .off(
                ".mfbdSimpleActions"
            )


            .on(
                "click.mfbdSimpleActions",
                ".mfbd-toggle-reasons",
                function () {

                    const $button =
                        $(this);

                    const $arrow =
                        $button.find(
                            ".mfbd-toggle-arrow"
                        );

                    const $table =
                        $container.find(
                            ".mfbd-table-container"
                        );


                    if (
                        $table.is(
                            ":visible"
                        )
                    ) {

                        $table.hide();

                        $arrow.text(
                            "▶"
                        );

                    } else {

                        $table.show();

                        $arrow.text(
                            "▼"
                        );
                    }
                }
            )


            .on(
                "click.mfbdSimpleActions",
                ".mfbd-add-document",
                function () {

                    mfbd_add_document(
                        frm,
                        $container
                    );
                }
            );
    }


    window.mfbd_load_breakdown_log =
        function (
            frm,
            $container
        ) {

            $container.html(`
                <div style="
                    padding:15px;
                    color:#6b7280;
                ">
                    Loading Breakdown Reasons...
                </div>
            `);


            mf_period_call(frm, {

                method:
                    "engineering.engineering.doctype.machine_file.machine_file.get_machine_breakdown_log_summary",

                args: {
                    name:
                        frm.doc.name
                },

                callback:
                    function (r) {

                        if (r.exc) {

                            $container.html(`
                                <div
                                    class="
                                        alert
                                        alert-danger
                                    "
                                >
                                    Could not load
                                    Breakdown Reasons.
                                </div>
                            `);

                            return;
                        }


                        mfbd_render(
                            frm,
                            $container,
                            r.message || {}
                        );
                    }
            });
        };

})();

// MACHINE FILE BREAKDOWN REASONS UI END

// MACHINE FILE MOVEMENT UI START

(function () {

    function mfmv_escape(value) {
        return frappe.utils.escape_html(
            String(value || "")
        );
    }


    function mfmv_datetime(value) {

        if (!value) {
            return "-";
        }

        let text = String(
            value
        ).replace(
            "T",
            " "
        );

        if (text.length >= 16) {
            text = text.slice(
                0,
                16
            );
        }

        return mfmv_escape(text);
    }


    function mfmv_status(status) {

        const value = String(
            status || ""
        );

        let bg = "#eeeeee";
        let fg = "#5f6368";

        if (
            value === "Submitted"
            || value === "Closed"
        ) {
            bg = "#d1f4dd";
            fg = "#137333";
        } else if (
            value === "Draft"
            || value === "Open"
        ) {
            bg = "#fff3cd";
            fg = "#8a6116";
        } else if (
            value === "Cancelled"
        ) {
            bg = "#f8d7da";
            fg = "#b42318";
        }

        return `
            <span style="
                display:inline-block;
                padding:4px 10px;
                border-radius:12px;
                background:${bg};
                color:${fg};
                font-size:11px;
                font-weight:700;
                white-space:nowrap;
            ">
                ${mfmv_escape(value || "-")}
            </span>
        `;
    }


    function mfmv_attachment_url(file_url) {

        const url = String(
            file_url || ""
        ).trim();

        if (!url) {
            return "#";
        }

        if (
            !url.startsWith(
                "/private/files/"
            )
        ) {
            return url;
        }

        return (
            "/api/method/"
            + "engineering.engineering.doctype."
            + "machine_file.machine_file."
            + "open_machine_file_attachment"
            + "?file_url="
            + encodeURIComponent(url)
        );
    }


    function mfmv_attachments(files) {

        if (
            !Array.isArray(files)
            || !files.length
        ) {
            return "-";
        }

        return files.map(function (file) {
            return `
                <a
                    href="${
                        mfmv_escape(
                            mfmv_attachment_url(
                                file.file_url
                            )
                        )
                    }"
                    target="_blank"
                    rel="noopener noreferrer"
                    style="
                        display:block;
                        margin-bottom:4px;
                    "
                >
                    View Attachment
                </a>
            `;
        }).join("");
    }


    function mfmv_add_document(frm) {
        window.mfdoc_open_dialog(
            frm,
            "1",
            "Machine Registration & Movement"
        );
    }


    function mfmv_render_table(data) {

        const rows =
            data.rows
            || data.records
            || data.movements
            || [];

        if (!rows.length) {
            return `
                <div style="
                    padding:18px;
                    text-align:center;
                    color:#6b7280;
                    border:1px dashed #d1d5db;
                    border-radius:6px;
                    background:#fff;
                ">
                    ${mf_has_period() ? "No records for the selected period." : "No movement records found."}
                </div>
            `;
        }

        let body = "";

        rows.forEach(function (row) {

            const name =
                row.name
                || row.movement
                || row.record
                || "-";

            const date =
                row.date
                || row.transaction_date
                || row.posting_date
                || row.creation
                || "";

            const purpose =
                row.purpose
                || row.transaction_type
                || row.movement_type
                || "-";

            const from_location =
                row.from_location
                || row.source_location
                || row.current_location
                || "-";

            const to_location =
                row.to_location
                || row.target_location
                || row.new_location
                || "-";

            const from_employee =
                row.from_employee
                || "-";

            const to_employee =
                row.to_employee
                || "-";

            const status =
                row.status
                || row.docstatus_label
                || "-";

            body += `
                <tr>
                    <td style="font-weight:700;">
                        ${mfmv_escape(name)}
                    </td>

                    <td>
                        ${mfmv_datetime(date)}
                    </td>

                    <td>
                        ${mfmv_escape(purpose)}
                    </td>

                    <td>
                        ${mfmv_escape(from_location)}
                    </td>

                    <td>
                        ${mfmv_escape(to_location)}
                    </td>

                    <td>
                        ${mfmv_escape(from_employee)}
                    </td>

                    <td>
                        ${mfmv_escape(to_employee)}
                    </td>

                    <td>
                        ${mfmv_status(status)}
                    </td>

                    <td>
                        ${mfmv_attachments(row.attachments || [])}
                    </td>
                </tr>
            `;
        });

        return `
            <div class="mfmv-box">
                <div class="mfmv-title">
                    Machine Registration & Movement
                </div>

                <div style="
                    width:100%;
                    overflow-x:auto;
                ">
                    <table class="mfmv-table">
                        <thead>
                            <tr>
                                <th>Movement</th>
                                <th>Date</th>
                                <th>Purpose</th>
                                <th>From Location</th>
                                <th>To Location</th>
                                <th>From Employee</th>
                                <th>To Employee</th>
                                <th>Status</th>
                                <th>Attachment</th>
                            </tr>
                        </thead>

                        <tbody>
                            ${body}
                        </tbody>
                    </table>
                </div>
            </div>
        `;
    }


    function mfmv_render(frm, $container, data) {

        const rows =
            data.rows
            || data.records
            || data.movements
            || [];

        const count =
            data.count != null
                ? data.count
                : rows.length;

        const tableHtml =
            mfmv_render_table(data);

        $container.html(`
            <style>

                .mfmv-toolbar {
                    display:flex;
                    align-items:center;
                    justify-content:flex-end;
                    gap:8px;
                    flex-wrap:wrap;
                    margin-bottom:10px;
                }

                .mfmv-box {
                    border:1px solid #dfe3e8;
                    border-radius:8px;
                    overflow:hidden;
                    background:#fff;
                }

                .mfmv-title {
                    padding:11px 12px;
                    background:#f3f6fa;
                    font-weight:700;
                }

                .mfmv-table {
                    width:100%;
                    min-width:1200px;
                    border-collapse:collapse;
                }

                .mfmv-table th {
                    padding:10px 9px;
                    text-align:left;
                    color:#1f4fa3;
                    background:#eef3f8;
                    border-bottom:1px solid #dfe3e8;
                    white-space:nowrap;
                }

                .mfmv-table td {
                    padding:10px 9px;
                    border-bottom:1px solid #e5e7eb;
                    vertical-align:top;
                }

            </style>

            <div class="mfmv-toolbar">

                <button
                    type="button"
                    class="btn btn-sm btn-default mfmv-toggle-records"
                >
                    <span class="mfmv-toggle-arrow">▶</span>
                    Movement Records (${count})
                </button>

                <button
                    type="button"
                    class="btn btn-sm btn-primary mfmv-add-document"
                >
                    + Add Document
                </button>

            </div>

            <div
                class="mfmv-table-container"
                style="display:none;"
            >
                ${tableHtml}
            </div>
        `);

        $container
            .off(".mfmvActions")

            .on(
                "click.mfmvActions",
                ".mfmv-toggle-records",
                function () {

                    const $button = $(this);
                    const $arrow = $button.find(
                        ".mfmv-toggle-arrow"
                    );
                    const $table = $container.find(
                        ".mfmv-table-container"
                    );

                    if ($table.is(":visible")) {
                        $table.hide();
                        $arrow.text("▶");
                    } else {
                        $table.show();
                        $arrow.text("▼");
                    }
                }
            )

            .on(
                "click.mfmvActions",
                ".mfmv-add-document",
                function () {
                    mfmv_add_document(frm);
                }
            );
    }


    window.mfmv_load_movement_section =
        function (frm, $container) {

            $container.html(`
                <div style="
                    padding:15px;
                    color:#6b7280;
                ">
                    Loading movement records...
                </div>
            `);

            mf_period_call(frm, {
                method:
                    "engineering.engineering.doctype.machine_file.machine_file.get_machine_registration_movement",

                args: {
                    name: frm.doc.name
                },

                callback: function (r) {

                    if (r.exc) {
                        $container.html(`
                            <div class="alert alert-danger">
                                Could not load movement records.
                            </div>
                        `);
                        return;
                    }

                    mfmv_render(
                        frm,
                        $container,
                        r.message || {}
                    );
                }
            });
        };

})();

// MACHINE FILE MOVEMENT UI END



// MACHINE FILE CENTRAL DOCUMENT DIALOG START

(function () {

    function mfdoc_index_row(
        frm,
        indexNo
    ) {

        return (
            frm.doc.index_items
            || []
        ).find(
            function (row) {
                return (
                    String(
                        row.index_no
                        || ""
                    ).trim()
                    ===
                    String(
                        indexNo
                        || ""
                    ).trim()
                );
            }
        );
    }


    function mfdoc_frequency_months(
        indexNo,
        frequency
    ) {

        const index =
            String(
                indexNo || ""
            );

        const value =
            String(
                frequency || ""
            ).toLowerCase();


        if (
            value.includes(
                "quarter"
            )
        ) {
            return 3;
        }


        const match =
            value.match(
                /(\d+)\s*months?/
            );

        if (match) {
            return parseInt(
                match[1],
                10
            );
        }


        if (
            value.includes(
                "annual"
            )
            || value.includes(
                "yearly"
            )
        ) {
            return 12;
        }


        if (index === "21") {
            return 12;
        }


        return null;
    }


    function mfdoc_add_months(
        value,
        months
    ) {

        if (
            !value
            || !months
        ) {
            return "";
        }

        const parts =
            String(value)
                .split("-")
                .map(Number);

        if (parts.length !== 3) {
            return "";
        }

        const year =
            parts[0];

        const month =
            parts[1];

        const day =
            parts[2];


        const target =
            new Date(
                Date.UTC(
                    year,
                    month - 1 + months,
                    1
                )
            );


        const targetYear =
            target.getUTCFullYear();

        const targetMonth =
            target.getUTCMonth();


        const lastDay =
            new Date(
                Date.UTC(
                    targetYear,
                    targetMonth + 1,
                    0
                )
            ).getUTCDate();


        const safeDay =
            Math.min(
                day,
                lastDay
            );


        const yyyy =
            String(
                targetYear
            );

        const mm =
            String(
                targetMonth + 1
            ).padStart(
                2,
                "0"
            );

        const dd =
            String(
                safeDay
            ).padStart(
                2,
                "0"
            );


        return (
            `${yyyy}-${mm}-${dd}`
        );
    }


    window.mfdoc_open_dialog =
        function (
            frm,
            indexNo,
            defaultDescription
        ) {

            const indexRow =
                mfdoc_index_row(
                    frm,
                    indexNo
                );


            const frequency =
                indexRow
                    ? (
                        indexRow.frequency
                        || "-"
                    )
                    : "-";


            const months =
                mfdoc_frequency_months(
                    indexNo,
                    frequency
                );


            const dialog =
                new frappe.ui.Dialog({

                    title:
                        `Add Document - ${
                            defaultDescription
                            || "Machine File"
                        }`,

                    fields: [

                        {
                            fieldname:
                                "frequency",

                            fieldtype:
                                "Data",

                            label:
                                "Frequency",

                            default:
                                frequency,

                            read_only:
                                1
                        },


                        {
                            fieldname:
                                "document_type",

                            fieldtype:
                                "Data",

                            label:
                                "Document / Report",

                            default:
                                defaultDescription
                                || "",

                            reqd:
                                1
                        },


                        {
                            fieldname:
                                "document_date",

                            fieldtype:
                                "Date",

                            label:
                                "Document Start Date",

                            default:
                                frappe.datetime
                                    .get_today(),

                            reqd:
                                1,

                            onchange:
                                function () {

                                    if (!months) {
                                        return;
                                    }

                                    const value =
                                        dialog.get_value(
                                            "document_date"
                                        );

                                    const due =
                                        mfdoc_add_months(
                                            value,
                                            months
                                        );

                                    dialog.set_value(
                                        "next_due_date",
                                        due
                                    );
                                }
                        },


                        {
                            fieldname:
                                "next_due_date",

                            fieldtype:
                                "Date",

                            label:
                                "Expiry / Next Due Date",

                            description:
                                months
                                    ? (
                                        "Calculated automatically "
                                        + "from Frequency."
                                    )
                                    : (
                                        "Enter only when this "
                                        + "frequency has a defined "
                                        + "next due date."
                                    )
                        },


                        {
                            fieldname:
                                "attachment",

                            fieldtype:
                                "Attach",

                            label:
                                "Attachment",

                            reqd:
                                1
                        },


                        {
                            fieldname:
                                "notes",

                            fieldtype:
                                "Small Text",

                            label:
                                "Notes"
                        }

                    ],


                    primary_action_label:
                        "Save Document",


                    primary_action(
                        values
                    ) {

                        if (
                            !values.attachment
                        ) {
                            frappe.msgprint(
                                "Please attach the document."
                            );

                            return;
                        }


                        dialog
                            .get_primary_btn()
                            .prop(
                                "disabled",
                                true
                            );


                        frappe.call({

                            method:
                                "engineering.engineering.doctype.machine_file.machine_file.save_machine_file_document",

                            args: {

                                name:
                                    frm.doc.name,

                                index_no:
                                    String(
                                        indexNo
                                    ),

                                document_type:
                                    values.document_type,

                                document_date:
                                    values.document_date,

                                next_due_date:
                                    values.next_due_date
                                    || "",

                                attachment:
                                    values.attachment,

                                notes:
                                    values.notes
                                    || ""
                            },


                            callback:
                                function (r) {

                                    dialog
                                        .get_primary_btn()
                                        .prop(
                                            "disabled",
                                            false
                                        );


                                    if (r.exc) {
                                        return;
                                    }


                                    const result =
                                        r.message
                                        || {};


                                    dialog.hide();


                                    frappe.show_alert({
                                        message:
                                            result
                                                .next_due_date
                                                ? (
                                                    "Document saved. "
                                                    + "Next Due: "
                                                    + result
                                                        .next_due_date
                                                )
                                                : (
                                                    "Document saved successfully."
                                                ),

                                        indicator:
                                            "green"
                                    });


                                    frm.reload_doc();
                                },


                            error:
                                function () {

                                    dialog
                                        .get_primary_btn()
                                        .prop(
                                            "disabled",
                                            false
                                        );
                                }
                        });
                    }
                });


            dialog.show();


            /*
             * Fixed calendar frequencies cannot be overridden.
             * Server is still the final authority.
             */
            if (months) {

                const dueField =
                    dialog.get_field(
                        "next_due_date"
                    );

                if (dueField) {

                    dueField.df.read_only =
                        1;

                    dueField.refresh();
                }


                const startDate =
                    dialog.get_value(
                        "document_date"
                    );

                dialog.set_value(
                    "next_due_date",
                    mfdoc_add_months(
                        startDate,
                        months
                    )
                );
            }
        };

})();

// MACHINE FILE CENTRAL DOCUMENT DIALOG END

