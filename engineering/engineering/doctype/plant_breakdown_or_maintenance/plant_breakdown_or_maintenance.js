
function set_asset_name_query(frm) {
    frm.set_query("asset_name", function () {
        return {
            query: "engineering.engineering.doctype.plant_breakdown_or_maintenance.plant_breakdown_or_maintenance.get_submitted_assets_by_location",
            filters: {
                location: frm.doc.location || ""
            }
        };
    });
}

// Copyright (c) 2025, Isambane Mining (Pty) Ltd
// For license information, please see license.txt

function render_breakdown_duration(frm) {
  const field = frm.fields_dict.breakdown_duration_display;
  const wrapper = field && field.$wrapper;

  if (!wrapper) return;

  const start = frm.doc.breakdown_start_datetime;
  const end = frm.doc.resolved_datetime;

  let totalMinutes = 0;

  if (start) {
    const startTime = moment(start);
    const endTime = end ? moment(end) : moment();

    if (
      startTime.isValid() &&
      endTime.isValid() &&
      !endTime.isBefore(startTime)
    ) {
      totalMinutes = Math.max(
        0,
        endTime.diff(startTime, "minutes")
      );
    }
  }

  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;

  wrapper.html(`
    <div style="
      margin-bottom:12px;
      padding:12px 15px;
      border:1px solid #d1d8dd;
      border-radius:6px;
      background:#f8f9fa;
    ">
      <div style="
        color:#6c7680;
        font-size:12px;
        margin-bottom:4px;
      ">
        ${__("Breakdown/Maintenance Duration")}
      </div>

      <div style="
        color:#1f272e;
        font-size:18px;
        font-weight:600;
      ">
        ${days} ${days === 1 ? __("day") : __("days")}
        -
        ${hours} ${hours === 1 ? __("hour") : __("hours")}
        -
        ${minutes} ${__("mins")}
      </div>
    </div>
  `);
}

frappe.ui.form.on("Plant Breakdown or Maintenance", {
  setup(frm) {
    set_asset_name_query(frm);
  },

  onload(frm) {
    set_asset_name_query(frm);
  },

  location(frm) {
    set_asset_name_query(frm);
    frm.set_value("asset_name", "");
    frm.set_value("item_name", "");
    frm.set_value("asset_category", "");
  },

  breakdown_start_datetime(frm) {
    frm.trigger("set_breakdown_start_key");
    frm.trigger("calculate_hours");
    render_breakdown_duration(frm);
  },

  resolved_datetime(frm) {
    frm.trigger("calculate_hours");
    render_breakdown_duration(frm);
    frm.trigger("set_open_closed");
  },


  // Build YYYYMMDD from breakdown_start_datetime
  set_breakdown_start_key(frm) {
    const dt = frm.doc.breakdown_start_datetime;
    if (!dt) {
      frm.set_value("breakdown_start_key", "");
      return;
    }
    frm.set_value("breakdown_start_key", moment(dt).format("YYYYMMDD"));
  },


  set_open_closed(frm) {
    frm.set_value("open_closed", frm.doc.resolved_datetime ? "Closed" : "Open");
  },



  calculate_hours(frm) {
    const start = frm.doc.breakdown_start_datetime;
    const end = frm.doc.resolved_datetime;

    if (start && end) {
      const startTime = moment(start);
      const endTime = moment(end);

      if (endTime.isBefore(startTime)) {
        frappe.msgprint(__("Resolved time cannot be earlier than breakdown start."));
        frm.set_value("breakdown_hours", 0);
        return;
      }

      const diffHours = endTime.diff(startTime, "hours", true);
      frm.set_value("breakdown_hours", diffHours.toFixed(2));
    } else {
      frm.set_value("breakdown_hours", 0);
    }
  },

  async validate(frm) {
    frm.trigger("set_breakdown_start_key");
    frm.trigger("set_open_closed");
    await frm.trigger("enforce_single_open_breakdown");
  },

  async enforce_single_open_breakdown(frm) {
    if (!frm.is_new() || !frm.doc.asset_name) return;

    const r = await frappe.call({
      method: "frappe.client.get_list",
      args: {
        doctype: "Plant Breakdown or Maintenance",
        filters: {
          asset_name: frm.doc.asset_name,
          open_closed: "Open",
        },
        fields: ["name", "breakdown_start_datetime"],
        order_by: "breakdown_start_datetime desc",
        limit_page_length: 1,
      },
    });

    const row = (r.message || [])[0];
    if (!row) return;

    const link = frappe.utils.get_form_link(
      "Plant Breakdown or Maintenance",
      row.name,
      true
    );

    frappe.msgprint(
      `Cannot create a new record. Last record for this asset is still Open: ${link}`
    );
    frappe.validated = false;
  },





  refresh(frm) {
    set_asset_name_query(frm);
    // Make breakdown_hours read-only
    frm.set_df_property("breakdown_hours", "read_only", 1);

    // Make open_closed read-only + sync value
    frm.set_df_property("open_closed", "read_only", 1);
    frm.trigger("set_open_closed");
    render_breakdown_duration(frm);

    // Show alert if excluded from A&U
    if (frm.doc.exclude_from_au) {
      frappe.show_alert({
        message: __("⚠️ This record is excluded from A&U downtime calculations."),
        indicator: "blue",
      });
    }
  },
});

// --- PBOM SIGNATURE ROLE PERMISSION START ---
(function () {
    const signature_rules = {
        information_officer_signature: ["Information Officer", "System Manager"],
        production_manager_signature: ["Production Manager", "Production Foreman"],
        engineering_manager_signature: ["Engineering Manager", "Engineering Foreman"]
    };

    const signature_labels = {
        information_officer_signature: "Information Officer Signature",
        production_manager_signature: "Production Manager Signature",
        engineering_manager_signature: "Engineering Manager Signature"
    };

    const signature_meta = {
        information_officer_signature: {
            datetime: "information_officer_date_and_time",
            shift: "information_officer_shift",
            user: "information_officer_user"
        },
        production_manager_signature: {
            datetime: "production_manager_date_and_time",
            shift: "production_manager_shift",
            user: "production_manager_user"
        },
        engineering_manager_signature: {
            datetime: "engineering_manager_date_and_time",
            shift: "engineering_manager_shift",
            user: "engineering_manager_user"
        }
    };

    function has_allowed_role(fieldname) {
        const allowed_roles = signature_rules[fieldname] || [];
        return allowed_roles.some(role => frappe.user.has_role(role));
    }

    function show_permission_message(fieldname) {
        const label = signature_labels[fieldname] || fieldname;
        const roles = (signature_rules[fieldname] || []).join(", ");

        frappe.msgprint({
            title: __("Permission Denied"),
            indicator: "red",
            message: __("You don't have permission to sign {0}.<br><br>Allowed roles: {1}", [label, roles])
        });
    }

    function apply_signature_role_permissions(frm) {
        Object.keys(signature_rules).forEach(function (fieldname) {
            if (!frm.fields_dict[fieldname]) {
                return;
            }

            const allowed = has_allowed_role(fieldname);

            frm.set_df_property(fieldname, "read_only", allowed ? 0 : 1);

            if (allowed) {
                frm.set_df_property(fieldname, "description", "");
            } else {
                frm.set_df_property(
                    fieldname,
                    "description",
                    "You don't have permission to sign this field. Allowed roles: " + signature_rules[fieldname].join(", ")
                );
            }

            setTimeout(function () {
                const field = frm.fields_dict[fieldname];

                if (!field || !field.$wrapper) {
                    return;
                }

                field.$wrapper.off("click.pbom_signature_permission");
                field.$wrapper.on("click.pbom_signature_permission", function () {
                    if (!has_allowed_role(fieldname)) {
                        show_permission_message(fieldname);
                    }
                });
            }, 300);
        });
    }

    function clear_signature_meta(frm, fieldname) {
        const meta = signature_meta[fieldname];
        if (!meta) return;

        frm.set_value(meta.datetime, "");
        frm.set_value(meta.shift, "");
        frm.set_value(meta.user, "");
    }

    function fill_signature_meta(frm, fieldname) {
        const meta = signature_meta[fieldname];
        if (!meta) return;

        if (!frm.doc[meta.datetime]) {
            frm.set_value(meta.datetime, frappe.datetime.now_datetime());
        }

        if (!frm.doc[meta.shift]) {
            frm.set_value(meta.shift, frm.doc.shift || "");
        }

        if (!frm.doc[meta.user]) {
            frm.set_value(meta.user, frappe.session.user_fullname || frappe.session.user);
        }
    }

    function handle_signature_change(frm, fieldname) {
        const value = frm.doc[fieldname];

        if (!value) {
            clear_signature_meta(frm, fieldname);
            return;
        }

        if (!has_allowed_role(fieldname)) {
            frm.set_value(fieldname, "");
            clear_signature_meta(frm, fieldname);
            show_permission_message(fieldname);
            return;
        }

        fill_signature_meta(frm, fieldname);
    }

    frappe.ui.form.on("Plant Breakdown or Maintenance", {
        onload: function (frm) {
            apply_signature_role_permissions(frm);
        },

        refresh: function (frm) {
            apply_signature_role_permissions(frm);
        },

        information_officer_signature: function (frm) {
            handle_signature_change(frm, "information_officer_signature");
        },

        production_manager_signature: function (frm) {
            handle_signature_change(frm, "production_manager_signature");
        },

        engineering_manager_signature: function (frm) {
            handle_signature_change(frm, "engineering_manager_signature");
        }
    });
})();
// --- PBOM SIGNATURE ROLE PERMISSION END ---

// --- PBOM AUTO FAILURE CLASSIFICATION START ---
(function () {
    const METHOD =
        "engineering.engineering.doctype." +
        "plant_breakdown_or_maintenance." +
        "auto_failure_classification.classify_breakdown";

    function cancel_pending(frm) {
        frm._pbom_ai_request = (frm._pbom_ai_request || 0) + 1;
        clearTimeout(frm._pbom_ai_timer);
    }

    async function clear_previous_suggestion(frm) {
        const previous = frm._pbom_ai_auto_value;

        if (!previous) return;
        frm._pbom_ai_auto_value = null;

        if (frm.doc.failure_classification !== previous) return;

        frm._pbom_ai_writing = true;
        try {
            await frm.set_value("failure_classification", "");
        } finally {
            frm._pbom_ai_writing = false;
        }
    }

    function reason_changed(frm) {
        cancel_pending(frm);

        // An old suggestion must not apply to a new description.
        if (frm.doc.ai_classification_audit && !frm.is_new()) {
            // Existing audit references must remain intact.
            // The server validates historical descriptions.
            return;
        }

        if (frm.doc.ai_classification_audit) {
            frm.set_value("ai_classification_audit", "")
                .catch(error => console.warn(
                    "Could not clear AI audit reference:", error
                ));
        }

        // Never overwrite an existing manual selection.
        if (frm._pbom_ai_manual) return;

        const previous = frm._pbom_ai_auto_value;

        if (previous &&
            frm.doc.failure_classification === previous) {
            clear_previous_suggestion(frm);
        }

        if (frm.doc.failure_classification &&
            frm.doc.failure_classification !== previous) {
            return;
        }

        frm._pbom_ai_timer = setTimeout(function () {
            suggest_classification(frm);
        }, 700);
    }

    async function suggest_classification(frm) {
        if (frm.doc.downtime_type !== "Breakdown") return;
        if (frm._pbom_ai_manual || frm._pbom_ai_writing) return;
        if (frm.doc.failure_classification) return;

        const reason = (frm.doc.breakdown_reason || "").trim();
        if (!reason || reason.length > 1000) return;

        const request_id = ++frm._pbom_ai_request;
        const document_name = frm.doc.name;

        try {
            const response = await frappe.call({
                method: METHOD,
                args: { reason },
                freeze: false
            });

            if (request_id !== frm._pbom_ai_request) return;
            if (frm.doc.name !== document_name) return;
            if (frm._pbom_ai_manual || frm._pbom_ai_writing) return;
            if (frm.doc.downtime_type !== "Breakdown") return;
            if (frm.doc.failure_classification) return;

            if ((frm.doc.breakdown_reason || "").trim() !== reason) {
                return;
            }

            const classification =
                (response.message || {}).classification;
            const audit_id =
                (response.message || {}).audit_id;

            // Never apply an unaudited AI suggestion.
            if (!classification || !audit_id) return;

            frm._pbom_ai_auto_value = classification;
            frm._pbom_ai_writing = true;

            try {
                await frm.set_value(
                    "ai_classification_audit",
                    audit_id
                );

                // The operator may have changed the form while
                // the audit reference was being applied.
                const still_current =
                    request_id === frm._pbom_ai_request &&
                    frm.doc.name === document_name &&
                    frm.doc.downtime_type === "Breakdown" &&
                    (frm.doc.breakdown_reason || "").trim() === reason &&
                    !frm._pbom_ai_manual &&
                    !frm.doc.failure_classification &&
                    frm.doc.ai_classification_audit === audit_id;

                if (!still_current) {
                    // Only remove our own stale reference on
                    // an unsaved record. Never touch a newer audit.
                    if (frm.is_new() &&
                        frm.doc.ai_classification_audit === audit_id) {
                        await frm.set_value(
                            "ai_classification_audit",
                            ""
                        );
                    }
                    return;
                }

                await frm.set_value(
                    "failure_classification",
                    classification
                );
            } finally {
                frm._pbom_ai_writing = false;
            }

        } catch (error) {
            console.warn(
                "AI classification unavailable:",
                error
            );
        }
    }

    function attach_reason_listener(frm) {
        const field = frm.fields_dict.breakdown_reason;
        if (!field || !field.$input) return;

        field.$input.off("input.pbom_ai");

        field.$input.on("input.pbom_ai", function () {
            reason_changed(frm);
        });
    }

    frappe.ui.form.on("Plant Breakdown or Maintenance", {
        onload(frm) {
            frm._pbom_ai_request = 0;
            frm._pbom_ai_manual = false;
            frm._pbom_ai_auto_value = null;
            frm._pbom_ai_writing = false;
        },

        refresh(frm) {
            attach_reason_listener(frm);
        },

        breakdown_reason(frm) {
            reason_changed(frm);
        },

        failure_classification(frm) {
            if (frm._pbom_ai_writing) return;

            frm._pbom_ai_manual = true;
            frm._pbom_ai_auto_value = null;
            cancel_pending(frm);
        },

        downtime_type(frm) {
            cancel_pending(frm);

            if (frm.doc.downtime_type === "Breakdown") {
                reason_changed(frm);
                return;
            }

            // Only discard pending AI suggestions on new records.
            // Existing saved audit references must be preserved.
            if (!frm.is_new()) return;

            if (frm.doc.ai_classification_audit) {
                frm.set_value("ai_classification_audit", "")
                    .catch(error => console.warn(
                        "Could not clear pending AI audit:", error
                    ));
            }

            if (frm._pbom_ai_auto_value) {
                clear_previous_suggestion(frm);
            }
        }
    });
})();
// --- PBOM AUTO FAILURE CLASSIFICATION END ---
