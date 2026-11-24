const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
let handlers;
const buttons = {};
const calls = [];
const messages = [];
class FixedDate extends Date {
    constructor(...args) { super(...(args.length ? args : [Date.UTC(2026, 10, 19, 23, 30)])); }
}
const context = {
    Date: FixedDate, __: text => text,
    frappe: {
        ui: {form: {on: (doctype, value) => {handlers = value;}}},
        msgprint: message => messages.push(message),
        call: async options => {
            calls.push(options);
            return {message: options.method.endsWith("get_import_status") ? {
                status: "Queued", records_processed: 2, imei: "must-not-overwrite",
                start_date: "must-not-overwrite", modified: "must-not-overwrite",
            } : {queued: true}};
        },
    },
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../engineering/doctype/mpi_history_import/mpi_history_import.js"), "utf8"), context);
(async () => {
    let defaults;
    handlers.onload({is_new: () => true, doc: {}, set_value: value => {defaults = value;}});
    // UTC is still November 19 while Johannesburg is already November 20.
    assert.equal(defaults.start_date, "2026-11-18");
    assert.equal(defaults.end_date, "2026-11-18");
    const frm = {
        doc: {name: "request-1", imei: "123", start_date: "2026-11-18", end_date: "2026-11-18",
            include_report: 0, modified: "original-revision", __unsaved: 1},
        is_new: () => false, perm: [{write: true}], is_dirty() {return !!this.doc.__unsaved;},
        add_custom_button: (label, callback) => {buttons[label] = callback;}, refresh_field: () => {},
        reload_doc: () => {throw new Error("Status refresh must not discard edits");},
    };
    const before = JSON.stringify(frm.doc);
    handlers.refresh(frm);
    await buttons["Refresh Import Status"]();
    for (const [key, value] of Object.entries(JSON.parse(before))) assert.equal(frm.doc[key], value);
    assert.equal(frm.doc.status, "Queued");
    const count = calls.length;
    await buttons["Import History"]();
    assert.equal(calls.length, count, "Dirty requests must not enqueue");
    frm.doc.__unsaved = 0;
    await buttons["Import History"]();
    assert.equal(calls[count].method, "engineering.controllers.mpi_history.enqueue_import");
    assert.equal(calls[count].args.request_name, "request-1");
    console.log("MPI history manual action, UTC defaults and edit-preserving status refresh: OK");
})().catch(error => {console.error(error); process.exitCode = 1;});
