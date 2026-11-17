frappe.ui.form.on("AI Failure Classification Settings", {
    refresh(frm) {
        frm.trigger("load_available_models");
    },

    available_models(frm) {
        frm.trigger("load_available_models");
    },

    async load_available_models(frm) {
        const allowed_roles = [
            "System Manager",
            "Engineering Manager",
            "Engineering Area Manager"
        ];

        if (!allowed_roles.some(role => frappe.user.has_role(role))) {
            return;
        }

        try {
            const response = await frappe.call({
                method: "engineering.engineering.doctype.ai_failure_classification_settings.ai_failure_classification_settings.get_available_models",
                type: "POST"
            });

            const models = response.message || [];
            const selected = frm.doc.preferred_model || "";

            const options = [...new Set(
                [selected, ...models].filter(Boolean)
            )];

            frm.set_df_property(
                "preferred_model",
                "options",
                options.join("\n")
            );

            frm.refresh_field("preferred_model");

            if (!models.length) {
                frappe.show_alert({
                    message: __("No Ollama models were returned."),
                    indicator: "orange"
                });
            }
        } catch (error) {
            console.error("Ollama model discovery failed:", error);
            frappe.show_alert({
                message: __("Unable to retrieve Ollama models."),
                indicator: "red"
            });
        }
    }
});
