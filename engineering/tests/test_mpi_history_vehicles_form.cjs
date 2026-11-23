const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const handlers = {}, buttons = {}, calls = [];
let dialog;
const mappings = [
    {imei: "111", plate: "ONE", asset: "ASSET-A"},
    {imei: "222", plate: "TWO", asset: "ASSET-B"},
    {imei: "333", plate: "REVIEW", asset: null},
];
const context = {
    __: value => value,
    frappe: {
        ui: {form: {on: (doctype, value) => {handlers[doctype] = value;}}, Dialog: class {
            constructor(options) {dialog = options;}
            show() {} hide() {}
        }},
        call: async args => {
            calls.push(args);
            return {message: args.method.endsWith("get_history_vehicle_options") ? mappings : {
                status: "Running", records_processed: 4, vehicles: [
                    {name: "saved", imei: "111", status: "Completed", records_processed: 4, asset: "must-not-apply"},
                    {name: "edited", imei: "222", status: "Failed", records_processed: 0},
                    {name: "removed", imei: "333", status: "Completed"},
                ],
            }};
        },
        msgprint: () => {},
    },
};
vm.runInNewContext(fs.readFileSync(path.join(__dirname,
    "../engineering/doctype/mpi_history_import/mpi_history_import.js"), "utf8"), context);
const frm = {
    doc: {name: "parent", status: "Draft", start_date: "2026-11-18", vehicles: [
        {name: "saved", imei: "111", plate: "ONE", asset: "MANUAL-EDIT"}], modified: "original", __unsaved: 1},
    perm: [{write: true}], is_new: () => false, is_dirty: () => true,
    add_custom_button: (name, action) => {buttons[name] = action;},
    add_child: (field, values) => {const child = {...values}; frm.doc[field].push(child); return child;},
    refresh_field: () => {}, dirty: () => {frm.doc.__unsaved = 1;},
};
(async () => {
    handlers["MPI History Import"].refresh(frm);
    assert.equal(typeof buttons["Add All Mapped Vehicles"], "function");
    await buttons["Add All Mapped Vehicles"]();
    assert.deepEqual(frm.doc.vehicles.map(r => r.imei), ["111", "222"]);
    assert.equal(frm.doc.vehicles[0].asset, "MANUAL-EDIT");
    await buttons["Add All Mapped Vehicles"]();
    assert.equal(frm.doc.vehicles.length, 2, "Repeated add-all must skip selected vehicles");
    await buttons["Add Selected Vehicles"]();
    assert.equal(dialog.fields[0].get_data("review")[0].value, "333");
    dialog.primary_action({imeis: ["333", "111"]});
    assert.deepEqual(frm.doc.vehicles.map(r => r.imei), ["111", "222", "333"]);
    assert.equal(frm.doc.vehicles[2].plate, "REVIEW");
    assert.equal(frm.doc.__unsaved, 1);
    frm.doc.vehicles = [frm.doc.vehicles[0], {name: "edited", imei: "999", status: "Draft"},
        {name: "local-new", imei: "444", status: "Draft"}];
    await buttons["Refresh Import Status"]();
    assert.equal(frm.doc.vehicles.length, 3, "Refresh cannot restore deleted selections");
    assert.equal(frm.doc.vehicles[0].status, "Completed");
    assert.equal(frm.doc.vehicles[0].records_processed, 4);
    assert.equal(frm.doc.vehicles[0].asset, "MANUAL-EDIT");
    assert.equal(frm.doc.vehicles[1].status, "Draft", "Edited identity must not receive another vehicle's status");
    assert.equal(frm.doc.vehicles[2].status, "Draft");
    assert.equal(frm.doc.modified, "original");
    assert.equal(frm.doc.__unsaved, 1);
    const count = frm.doc.vehicles.length;
    await buttons["Add All Mapped Vehicles"]();
    assert.equal(frm.doc.vehicles.length, count, "Queued/running selections are frozen");
    console.log("MPI history selected/all mappings and edit-preserving child status refresh: OK");
})().catch(error => {console.error(error); process.exitCode = 1;});
