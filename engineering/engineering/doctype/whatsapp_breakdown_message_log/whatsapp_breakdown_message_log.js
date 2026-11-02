frappe.ui.form.on("WhatsApp Breakdown Message Log", {
    refresh(frm) {
        if (frm.doc.__islocal) {
            return;
        }

        frm.add_custom_button("Create/Update Breakdown", async function () {
            const submit = (failure_classification) => frappe.call({
                method: "engineering.engineering.doctype.whatsapp_breakdown_message_log.whatsapp_breakdown_message_log.create_or_update_breakdown",
                args: {
                    log_name: frm.doc.name,
                    failure_classification
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
                const field = frappe.meta.get_docfield("Plant Breakdown or Maintenance", "failure_classification");
                frappe.prompt([{fieldname: "failure_classification", fieldtype: "Link", label: __("Failure Classification"),
                    options: field.options, reqd: 0}], values => submit(values.failure_classification),
                    __("Classify breakdown (optional)"), __("Create Breakdown"));
            } else {
                submit();
            }
        }).addClass("btn-primary");
    }
});
