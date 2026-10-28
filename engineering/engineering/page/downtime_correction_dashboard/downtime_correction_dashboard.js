frappe.pages["downtime-correction-dashboard"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: __("Downtime Correction Dashboard"),
        single_column: true,
    });

    let ready = false;
    const $holder = $('<div class="dcd-dashboard-holder"></div>').appendTo(page.main);

    const fromDate = page.add_field({
        fieldname: "from_date",
        label: __("From Date"),
        fieldtype: "Date",
        default: frappe.datetime.add_days(frappe.datetime.get_today(), -7),
        reqd: 1,
        change: () => ready && refresh(),
    });

    const toDate = page.add_field({
        fieldname: "to_date",
        label: __("To Date"),
        fieldtype: "Date",
        default: frappe.datetime.get_today(),
        reqd: 1,
        change: () => ready && refresh(),
    });

    const site = page.add_field({
        fieldname: "site",
        label: __("Site"),
        fieldtype: "Link",
        options: "Location",
        change: () => ready && refresh(),
    });

    const fixedStatus = page.add_field({
        fieldname: "fixed_status",
        label: __("Fixed Status"),
        fieldtype: "Select",
        options: ["All", "Fixed", "Not Fixed"],
        default: "All",
        change: () => ready && refresh(),
    });

    const controller =
        "engineering.engineering.page.downtime_correction_dashboard.downtime_correction_dashboard";

    function refresh() {
        const from_date = fromDate.get_value();
        const to_date = toDate.get_value();

        if (!from_date || !to_date) return;

        if (from_date > to_date) {
            frappe.msgprint(__("From Date must not be after To Date."));
            return;
        }

        $holder.html(
            '<div class="dcd-empty">' +
            __("Loading downtime corrections...") +
            '</div>'
        );

        frappe.call({
            method: `${controller}.get_page_html`,
            args: {
                from_date,
                to_date,
                site: site.get_value() || "",
                fixed_status: fixedStatus.get_value() || "All",
            },
            callback: function (r) {
                if (r.exc) {
                    $holder.html("");
                    return;
                }
                $holder.html(r.message || "");
            },
        });
    }

    page.set_primary_action(__("Refresh"), refresh, "refresh");

    page.add_inner_button(__("Open Downtime"), function () {
        frappe.set_route("List", "Plant Breakdown or Maintenance");
    });

    $holder.on("click", ".dcd-fleet-link", function () {
        const btn = $(this);
        const breakdown = btn.attr("data-breakdown") || "";

        if (breakdown) {
            frappe.set_route("Form", "Plant Breakdown or Maintenance", breakdown);
            return;
        }

        const fleet = btn.attr("data-fleet") || "";
        const selected_site = btn.attr("data-site") || "";
        const correction_date = btn.attr("data-date") || "";

        frappe.call({
            method: `${controller}.get_commented_breakdown_name`,
            args: {
                fleet,
                site: selected_site,
                correction_date,
            },
            callback: function (r) {
                if (r.exc) return;

                if (!r.message) {
                    frappe.msgprint(
                        __("No matching Plant Breakdown or Maintenance record was found.")
                    );
                    return;
                }

                frappe.set_route(
                    "Form",
                    "Plant Breakdown or Maintenance",
                    r.message
                );
            },
        });
    });

    $holder.on("click", ".dcd-view", function () {
        const btn = $(this);
        let comments = [];

        try {
            comments = JSON.parse(btn.attr("data-comments") || "[]");
        } catch (e) {
            frappe.msgprint(__("Unable to read comments."));
            return;
        }

        const blocks = comments.map((row) => `
            <div class="dcd-comment-block">
                <div class="dcd-comment-source">${frappe.utils.escape_html(row.source || "")}</div>
                <div class="dcd-popup-comment">${frappe.utils.escape_html(row.comment || "").replace(/\n/g, "<br>")}</div>
            </div>
        `).join("");

        frappe.msgprint({
            title: __("Downtime Correction Comment"),
            indicator: "red",
            message: `
                <div class="dcd-popup">
                    <div><b>${__("Fleet")}:</b> ${frappe.utils.escape_html(btn.attr("data-fleet") || "")}</div>
                    <div><b>${__("Breakdown/Maintenance Start Time")}:</b> ${frappe.utils.escape_html(btn.attr("data-start") || "—")}</div>
                    <div><b>${__("Verified Date")}:</b> ${frappe.utils.escape_html(btn.attr("data-date") || "")}</div>
                    <hr>
                    ${blocks}
                </div>
            `,
        });
    });

    $holder.on("change", ".dcd-fixed-checkbox", function () {
        const checkbox = $(this);
        const fixed = checkbox.is(":checked") ? 1 : 0;

        frappe.call({
            method: `${controller}.set_fixed_status`,
            type: "POST",
            args: {
                child_row: checkbox.attr("data-row"),
                fixed_key: checkbox.attr("data-key"),
                fixed,
            },
            callback: function (r) {
                if (!r.exc) refresh();
                else checkbox.prop("checked", !fixed);
            },
            error: function () {
                checkbox.prop("checked", !fixed);
            },
        });
    });


    $holder.on("change", ".dcd-verification-fixed-checkbox", function () {
        const checkbox = $(this);
        const fixed = checkbox.is(":checked") ? 1 : 0;

        checkbox.prop("disabled", true);

        frappe.call({
            method: `${controller}.set_verification_correction_fixed`,
            type: "POST",
            args: {
                verification_entry: checkbox.attr("data-entry"),
                fixed,
            },
            callback: function (r) {
                if (!r.exc && r.message && r.message.ok) {
                    refresh();
                } else {
                    checkbox.prop("checked", !fixed);
                    checkbox.prop("disabled", false);
                }
            },
            error: function () {
                checkbox.prop("checked", !fixed);
                checkbox.prop("disabled", false);
            },
        });
    });

    ready = true;
    wrapper.dcd_refresh = refresh;

    refresh();
};

frappe.pages["downtime-correction-dashboard"].on_page_show = function (wrapper) {
    if (wrapper.dcd_refresh) wrapper.dcd_refresh();
};
