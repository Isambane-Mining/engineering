frappe.ui.form.on("Engineering Legals Site Section Rule", {
    no_expiry(frm, cdt, cdn) {
        const row = locals[cdt][cdn];
        if (row.no_expiry) {
            frappe.model.set_value(cdt, cdn, {
                expiry_value: 0,
                expiry_unit: "",
                counting_mode: "Saved In Month"
            });
        }
    }
});
