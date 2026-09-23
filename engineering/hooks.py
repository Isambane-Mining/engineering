app_name = "engineering"
app_title = "Engineering"
app_publisher = "BuFf0k"
app_description = "Engineering Workflows and Maintenance Tasks"
app_email = "buff0k@buff0k.co.za"
app_license = "mit"
required_apps = ["frappe/erpnext"]
source_link = "http://github.com/buff0k/engineering"
app_logo_url = "/assets/engineering/images/is-logo.png"
app_home = "/desk/engineering"


standard_portal_menu_items = [
    {
        "title": "Engineering Legals",
        "route": "/engineering_legals_sup",
        "reference_doctype": "Engineering Legals",
        "role": "Supplier",
    },
    {
        "title": "My Engineering Legals",
        "route": "/engineering_legals_list",
        "reference_doctype": "Engineering Legals",
        "role": "Supplier",
    }
]


add_to_apps_screen = [
    {
        "name": app_name,
        "logo": "/assets/engineering/images/is-logo.png",
        "title": app_title,
        "route": app_home,
        "has_permission": "engineering.engineering.utils.check_app_permission",
    }
]

fixtures = [
    {"dt": "Role", "filters": [["name", "in", ["Engineering Manager", "Engineering User", "Information Officer", "Mechanic", "Engineering Foreman", "Engineering Plant Manager", "Parts Driver", "Engineering Area Manager"]]]},
    {"dt": "Custom DocPerm", "filters": [["role", "in", ["Engineering Manager", "Engineering User", "Information Officer", "Mechanic", "Engineering Foreman", "Engineering Plant Manager", "Parts Driver", "Engineering Area Manager"]]]},
    {"dt": "Custom Field", "filters": [["dt", "in", ["Asset Movement"]]]},
    {"dt": "Asset Category", "filters": [["name", "in", ["Dozer", "ADT", "RDT", "Excavator", "LDV"]]]},
    {"dt": "Service Interval", "filters": [["name", "in", ["250 Hours", "500 Hours", "750 Hours", "1000 Hours", "2000 Hours"]]]},
    # Driver's licence competencies (Employee Induction is owned by the ir app,
    # but these 6 licence codes back Vehicle Allocation, so they are fixtured
    # here rather than in ir).
    {"dt": "Employee Induction", "filters": [["name", "in", [
        "Drivers Licence - Code B",
        "Drivers Licence - Code EB",
        "Drivers Licence - Code C",
        "Drivers Licence - Code EC",
        "Drivers Licence - Code C1",
        "Drivers Licence - Code EC1",
    ]]]},
    # Company Vehicle Undertaking record type (Employee File Record is owned
    # by the ir app; this backs the addendum-on-file check on Vehicle
    # Allocation, read from Employee.ir_employee_records).
    {"dt": "Employee File Record", "filters": [["name", "in", ["Company Vehicle Undertaking"]]]},
]


# ---------------------------------------------------------------------
# Website route rules
# ---------------------------------------------------------------------
website_route_rules = [
    {"from_route": "/engineering_legals_sup", "to_route": "engineering_legals_sup"},
    {"from_route": "/engineering_legals_list", "to_route": "engineering_legals_list"},
]


# ---------------------------------------------------------------------
# Doctype-specific client JS
# ---------------------------------------------------------------------
doctype_js = {
    "Plant Breakdown": "engineering/doctype/plant_breakdown/plant_breakdown.js",
    "Engineering Control Panel": "engineering/doctype/engineering_control_panel/engineering_control_panel.js",
    "Service Schedule": "engineering/engineering/doctype/service_schedule/service_schedule.js",
    "Engineering Legals": "engineering/engineering/doctype/engineering_legals/engineering_legals.js",
    "Daily Downtime Summary": "engineering/engineering/doctype/daily_downtime_summary/daily_downtime_summary.js",
}

app_include_css = [
    "/assets/engineering/css/engineering.css"
]

# ---------------------------------------------------------------------
# Scheduled jobs
# ---------------------------------------------------------------------
scheduler_events = {
    "hourly": [
        "engineering.controllers.notifications.send_open_breakdowns_digest_hourly_gate",
        "engineering.engineering.doctype.availability_and_utilisation.availability_and_utilisation.run_hourly_gate",
        "engineering.controllers.importer.run_scheduled_wearcheck_sync",
    ],
    "cron": {
        "0 6 * * *": [
            "engineering.api.deviation_email.send_open_deviation_emails",
            "engineering.engineering.report.down_time.down_time.send_daily_downtime_night_shift",
            "engineering.engineering.report.down_time.down_time.send_full_daily_downtime_summary",
        ],
        "0 18 * * *": [
            "engineering.engineering.report.down_time.down_time.send_daily_downtime_day_shift"
        ],
        "0 * * * *": [
            "engineering.engineering.doctype.hourly_downtime_summary.hourly_downtime_summary.create_all_hourly_downtime_summaries"
        ],
        # ==========================================================
        # OPEN BREAKDOWN DIGEST + A&U DAILY RUN
        # Weekdays: 06:00 and 18:00
        # Weekends: 06:00 and 15:00
        # ==========================================================
        "0 6,18 * * 1-5": [
            "engineering.controllers.notifications.send_open_breakdowns_digest"
        ],
        "0 6,15 * * 0,6": [
            "engineering.controllers.notifications.send_open_breakdowns_digest"
        ],
        "5 0 * * *": [
            "engineering.engineering.doctype.availability_and_utilisation.availability_and_utilisation.run_daily",
        ],
        # ==========================================================
        # NEW — SERVICE SCHEDULE DAILY UPDATE (Runs at 01:00)
        # ==========================================================
        "0 1 * * *": [
            "engineering.engineering.doctype.service_schedule.service_schedule.queue_service_schedule_update"
        ],
        "0 2 * * *": [
            "engineering.engineering.doctype.engineering_legals.engineering_legals.queue_unsynced_engineering_legals"
        ],
        "15 3 * * *": [
            "engineering.engineering.doctype.engineering_legals.sharepoint_monthly_frequency.run_current_month_frequency_sync"
        ],
    },
}

# ---------------------------------------------------------------------
# DocType event hooks
# ---------------------------------------------------------------------
doc_events = {
    "WhatsApp Message": {
        "after_insert": "engineering.controllers.whatsapp_breakdown_import.whatsapp_message_after_insert",
    },
    "Plant Breakdown or Maintenance": {
        "on_update": "engineering.engineering.doctype.plant_breakdown_or_maintenance.plant_breakdown_or_maintenance.on_update",
    },
    "Engineering Legals": {
        "after_insert": "engineering.engineering.doctype.engineering_legals.engineering_legals.sync_engineering_legals_from_doc",
        "on_update": "engineering.engineering.doctype.engineering_legals.engineering_legals.sync_engineering_legals_from_doc",
        "on_trash": "engineering.engineering.doctype.engineering_legals.engineering_legals.on_trash",
    },
    "OEM Booking": {
        "on_update": "engineering.controllers.notifications.oem_booking_on_update",
    },
    "WearCheck Results": {
        "after_insert": "engineering.controllers.notifications.wearcheck_results_after_insert",
        "on_update": "engineering.controllers.notifications.wearcheck_results_on_update",
    },
    "Component Replacement Report": {
        "on_update": "engineering.controllers.isambane_sample_input.component_replacement_report_on_update"
    },
    "Asset Movement": {
        # Asset Movement's own on_submit/on_cancel already updates
        # Asset.location first — this just carries that across onto the
        # current Vehicle Licence for each moved Asset, so licensing
        # doesn't go stale relative to where the vehicle actually is.
        "on_submit": "engineering.engineering.doctype.vehicle_licence.vehicle_licence.sync_location_from_asset_movement",
        "on_cancel": "engineering.engineering.doctype.vehicle_licence.vehicle_licence.sync_location_from_asset_movement",
    },

}

# ---------------------------------------------------------------------
# Whitelisted method overrides
# ---------------------------------------------------------------------
override_whitelisted_methods = {
}

# Engineering Legals monthly SharePoint folders
scheduler_events = globals().get("scheduler_events", {})

scheduler_events.setdefault("daily", [])

if "engineering.engineering.doctype.engineering_legals.sharepoint_monthly_folders.create_current_month_sharepoint_folders" not in scheduler_events["daily"]:
    scheduler_events["daily"].append(
        "engineering.engineering.doctype.engineering_legals.sharepoint_monthly_folders.create_current_month_sharepoint_folders"
    )

# ==========================================================
# FLEET MANAGEMENT (Vehicle Allocation / Vehicle Licence) — weekly compliance
# digest, plus two daily alerts (terminated/pending-termination drivers,
# temporary loans). Compliance/expiry status is computed live (virtual
# fields, never stored), so there is nothing to recalculate on a schedule —
# each gate below just checks its own enable flag on Fleet Management
# Settings and, if on, sends with freshly computed values. Registered
# directly against Frappe's own native "weekly"/"daily" scheduler buckets
# (Weekly = Sundays 00:00 server time, Daily = 00:00 server time) rather
# than a custom day/hour field — Frappe's Scheduled Job Type already
# guarantees each of these runs at most once per its period.
# ==========================================================
scheduler_events.setdefault("weekly", [])

if "engineering.controllers.fleet_notifications.send_weekly_fleet_digest_gate" not in scheduler_events["weekly"]:
    scheduler_events["weekly"].append(
        "engineering.controllers.fleet_notifications.send_weekly_fleet_digest_gate"
    )

for _fleet_job in (
    "engineering.controllers.fleet_notifications.send_terminated_driver_alert_gate",
    "engineering.controllers.fleet_notifications.send_temporary_loan_digest_gate",
):
    if _fleet_job not in scheduler_events["daily"]:
        scheduler_events["daily"].append(_fleet_job)


# Breakdown History global public List View
doctype_list_js = dict(
    globals().get("doctype_list_js", {}),
    **{
        "Breakdown History": "public/js/breakdown_history_list.js"
    }
)
