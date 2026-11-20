/* Kobelco timestamps are UTC at rest, independent of the site's timezone. */
frappe.provide("frappe.kobelco_telemetry");
frappe.kobelco_telemetry.format_datetime = (value) => {
    if (!value) return "";
    const text = String(value).replace(" ", "T");
    const utc = new Date(/[zZ]$|[+-]\d\d:\d\d$/.test(text) ? text : text + "Z");
    if (Number.isNaN(utc.getTime())) return "";
    const parts = new Intl.DateTimeFormat("en-GB", {
        timeZone: "Africa/Johannesburg", year: "numeric", month: "2-digit", day: "2-digit",
        hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23",
    }).formatToParts(utc);
    const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day} ${values.hour}:${values.minute}:${values.second}`;
};
