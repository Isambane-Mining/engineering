// Copyright (c) 2026, BuFf0k and contributors
// For license information, please see license.txt

frappe.ui.form.on("Fleet Card Transaction Import", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0) {
			return;
		}

		// The real import always runs in the background (see the shared
		// controller's module docstring) - never rely on the native Submit
		// button here, it would block the request until the whole file is
		// processed. before_submit() also refuses to run it inline as a
		// second line of defense.
		const can_start_import =
			["Pending Import", "Missing Information", "Partially Imported", "Error"].includes(frm.doc.status) &&
			frm.doc.resolvable_count;

		if (can_start_import) {
			const is_full_run = frm.doc.status === "Pending Import";
			frm.page.set_primary_action(__("Start Import"), () => {
				frappe.confirm(
					is_full_run
						? __(
								"This runs in the background and will create Fleet Card Transaction records once done. Continue?"
						  )
						: __(
								"{0} of {1} rows are ready to import now - the rest will stay unresolved for a later run. This runs in the background. Continue?",
								[frm.doc.resolvable_count, frm.doc.total_rows]
						  ),
					() => {
						frm.call("queue_import").then(() => frm.reload_doc());
					}
				);
			});
		}
	},
});
