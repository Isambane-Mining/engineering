// Preserve bookmarks and the original Page permission check.
frappe.pages['machine-reliability'].on_page_show = function () {
    frappe.route_options = {...(frappe.route_options || {}), reliability_tab: 'machine'};
    return frappe.set_route('reliability-engineering');
};
