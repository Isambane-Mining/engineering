frappe.listview_settings["Engineering Legals"] = {
    onload(listview) {
        const roles = frappe.user_roles || [];

        if (!roles.some(role =>
            ["System Manager", "Engineering Manager"].includes(role)
        )) return;

        listview.page.add_inner_button(
            __("Sync Unsynced to SharePoint"),
            async () => {
                const method =
                    "engineering.controllers.engineering_legals_sharepoint_retry.retry_unsynced_sharepoint";

                try {
                    const preview = await frappe.call({
                        method,
                        args: {preview: 1},
                        freeze: true
                    });

                    const count = preview.message?.eligible || 0;

                    if (!count) {
                        frappe.msgprint(__("No eligible unsynced records found."));
                        return;
                    }

                    frappe.confirm(
                        __("Queue SharePoint sync for {0} unsynced records?", [count]),
                        async () => {
                            try {
                                const result = await frappe.call({
                                    method,
                                    args: {preview: 0},
                                    freeze: true,
                                    freeze_message: __("Queueing SharePoint uploads...")
                                });

                                frappe.msgprint(
                                    __("{0} records queued. Refresh later to check sync status.", [
                                        result.message?.queued || 0
                                    ])
                                );
                            } catch (error) {
                                frappe.msgprint(__("Unable to queue SharePoint sync."));
                            }
                        }
                    );
                } catch (error) {
                    frappe.msgprint(__("Unable to check SharePoint sync eligibility."));
                }
            }
        );
    }
};
