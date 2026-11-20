// Offline form behavior: status refresh must preserve dirty user edits.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
let handlers;
const buttons = {};
const refreshed = [];
const frm = {
    doc: {username: "unsaved-user", api_password: "fake-unsaved-password", endpoint: "unsaved-endpoint",
        vehicles: [{imei: "123", asset: "USER-CHOICE"}], __unsaved: 1, modified: "original-revision"},
    perm: [{write: true}], is_new: () => false, is_dirty: () => true,
    add_custom_button: (label, fn) => {buttons[label] = fn;},
    refresh_field: field => refreshed.push(field),
    reload_doc: () => {throw new Error("Status refresh must not reload unsaved edits");},
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../engineering/doctype/api_mpi_settings/api_mpi_settings.js"), "utf8"), {
    __: value => value,
    frappe: {ui: {form: {on: (name, value) => {handlers = value;}}}, call: async () => ({message: {
        last_error: "New safe status", last_attempt: "now", username: "must not apply",
        vehicles: [], modified: "must not apply", api_password: "must not apply",
    }})},
});
(async () => {
    const before = JSON.stringify(frm.doc);
    handlers.refresh(frm);
    await buttons["Refresh Sync Status"]();
    const original = JSON.parse(before);
    for (const key of Object.keys(original)) assert.deepEqual(frm.doc[key], original[key]);
    assert.equal(frm.doc.last_error, "New safe status");
    assert.deepEqual(refreshed, ["last_error", "last_attempt"]);
    console.log("MPI form status refresh preserves dirty configuration, credentials, mappings and revision: OK");
})().catch(error => {console.error(error); process.exitCode = 1;});
