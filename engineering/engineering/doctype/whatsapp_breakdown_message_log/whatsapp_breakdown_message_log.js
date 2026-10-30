frappe.ui.form.on("WhatsApp Breakdown Message Log", {
    refresh(frm) {
        if (frm.doc.__islocal) {
            return;
        }

        frm.add_custom_button("Create/Update Breakdown", async function () {
            const submit = (problem_category) => frappe.call({
                method: "engineering.engineering.doctype.whatsapp_breakdown_message_log.whatsapp_breakdown_message_log.create_or_update_breakdown",
                args: {
                    log_name: frm.doc.name,
                    problem_category
                },
                freeze: true,
                freeze_message: "Creating/updating breakdown...",
                callback: function (r) {
                    if (r.message) {
                        frappe.msgprint(
                            "Done: " + r.message.status + "<br>Breakdown: " + r.message.breakdown
                        );
                        frm.reload_doc();
                    }
                }
            });
            const requires_category = frm.doc.detected_action === "Book Down"
                ? (await frappe.call({
                    method: "engineering.engineering.doctype.whatsapp_breakdown_message_log.whatsapp_breakdown_message_log.requires_breakdown_category",
                    args: {log_name: frm.doc.name}
                })).message : false;
            if (requires_category) {
                await frappe.model.with_doctype("Plant Breakdown or Maintenance");
                const field = frappe.meta.get_docfield("Plant Breakdown or Maintenance", "problem_category");
                frappe.prompt([{fieldname: "problem_category", fieldtype: "Select", label: __("Problem Category"),
                    options: field.options, reqd: 1}], values => submit(values.problem_category),
                    __("Categorise breakdown"), __("Create Breakdown"));
            } else {
                submit();
            }
        }).addClass("btn-primary");
    }
});
