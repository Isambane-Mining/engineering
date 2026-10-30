// Expiry and capture requirements come only from the authoritative server resolver.
frappe.ui.form.on("Engineering Legals", {
    refresh(frm) {
        apply_asset_filter(frm);
        add_eng_legals_report_button(frm);
        return refresh_legal_policy(frm);
    },
    async site(frm) {
        await frm.set_value("fleet_number", null);
        apply_asset_filter(frm);
        return refresh_legal_policy(frm);
    },
    async sections(frm) {
        if (frm.__legal_applying) return;
        await frm.set_value({vehicle_type: null, lifting_type: null, brake_wear_type: null});
        return refresh_legal_policy(frm);
    },
    vehicle_type: refresh_legal_policy,
    lifting_type: refresh_legal_policy,
    brake_wear_type: refresh_legal_policy,
    start_date: refresh_legal_policy,
    fleet_number: refresh_legal_policy
});

function legal_inputs(frm) {
    const result = {};
    for (const field of ["site", "sections", "fleet_number", "start_date", "vehicle_type", "lifting_type", "brake_wear_type"]) {
        result[field] = frm.doc[field] || null;
    }
    return result;
}

function refresh_legal_policy(frm) {
    if (frm.__legal_applying) return;
    const values = legal_inputs(frm);
    const key = JSON.stringify(values);
    const request = (frm.__legal_request || 0) + 1;
    frm.__legal_request = request;
    return frappe.call({
        method: "engineering.controllers.engineering_legals_rules.get_capture_preview",
        args: {values: JSON.stringify(values), docname: frm.is_new() ? null : frm.doc.name},
        callback: async (response) => {
            if (request !== frm.__legal_request || key !== JSON.stringify(legal_inputs(frm))) return;
            const result = response.message;
            if (!result) return;
            frm.set_query("sections", () => ({filters: {name: ["in", result.sections || []]}}));
            const rule = result.rule;
            if (!rule) return;
            for (const [field, options] of [["vehicle_type", rule.vehicle_options], ["lifting_type", rule.lifting_options]]) {
                frm.toggle_display(field, !!(options || []).length);
                frm.toggle_reqd(field, !!rule[field]);
            }
            frm.toggle_display("brake_wear_type", !!rule.brake_wear_required);
            frm.toggle_reqd("brake_wear_type", !!rule.brake_wear_required);
            frm.toggle_reqd("fleet_number", !!rule.fleet_required);
            frm.toggle_reqd("start_date", rule.start_date_policy === "Required");
            frm.toggle_display("start_date", rule.start_date_policy !== "Clear");
            frm.toggle_display("expiry_date", !rule.no_expiry);
            if (result.preserved) return;
            const changes = {};
            for (const field of ["expiry_date", "start_date", "vehicle_type", "lifting_type", "brake_wear_type"]) {
                if (Object.prototype.hasOwnProperty.call(result, field) && (frm.doc[field] || null) !== (result[field] || null)) {
                    changes[field] = result[field] || null;
                }
            }
            if (Object.keys(changes).length) {
                const expectedInputs = {...values};
                for (const field of Object.keys(expectedInputs)) {
                    if (Object.prototype.hasOwnProperty.call(changes, field)) expectedInputs[field] = changes[field] || null;
                }
                frm.__legal_applying = true;
                try { await frm.set_value(changes); }
                finally { frm.__legal_applying = false; }
                // A user edit may have fired while asynchronous field triggers were guarded.
                if (JSON.stringify(legal_inputs(frm)) !== JSON.stringify(expectedInputs)) {
                    return refresh_legal_policy(frm);
                }
            }
        }
    });
}

function apply_asset_filter(frm) {
  frm.set_query('fleet_number', () => {
    return {
      filters: {
        docstatus: 1,
        location: frm.doc.site || ''
      }
    };
  });
}

function add_eng_legals_report_button(frm) {
  frm.remove_custom_button("Open Engineering Legals Report");

  frm.add_custom_button("Open Engineering Legals Report", () => {
    const params = new URLSearchParams({
      report_name: "Engineering Legals Report",
      as_at_date: frappe.datetime.get_today(),
      view: "Summary"
    });

    if (frm.doc.site) {
      params.set("site", frm.doc.site);
    }

    const url = `/desk/query-report/Engineering%20Legals%20Report?${params.toString()}`;
    window.open(url, "_blank");
  });
}
