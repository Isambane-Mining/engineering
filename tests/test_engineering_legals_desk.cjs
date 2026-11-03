const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

async function main() {
    let handlers;
    const requests = [];
    const writes = [];
    const frappe = {
        ui: {form: {on: (_doctype, events) => { handlers = events; }}},
        call: (args) => { requests.push(args); },
        datetime: {add_months: () => "2027-01-31"}
    };
    const frm = {
        doc: {name: "historic", site: "Gwab", sections: "NDT", fleet_number: "EX001",
              start_date: "2026-01-31", expiry_date: "2026-07-31"},
        is_new: () => false,
        set_value: async (field, val) => {
            const changes = typeof field === "object" ? field : {[field]: val};
            writes.push(changes); Object.assign(frm.doc, changes);
        },
        set_query() {}, toggle_display() {}, toggle_reqd() {}, refresh_field() {},
        set_df_property() {}, remove_custom_button() {}, add_custom_button() {}
    };
    const file = path.join(__dirname, "../engineering/engineering/doctype/engineering_legals/engineering_legals.js");
    vm.runInNewContext(fs.readFileSync(file, "utf8"), {frappe, window: {}, URLSearchParams});
    await handlers.refresh(frm);
    assert.equal(frm.doc.expiry_date, "2026-07-31", "refresh must not recalculate history locally");
    assert.equal(requests.length, 1, "refresh must request the server policy");
    const policy = {vehicle_options: [], lifting_options: [], start_date_policy: "Required", no_expiry: 0};
    await requests[0].callback({message: {preserved: true, expiry_date: "2026-07-31", sections: ["NDT"], rule: policy}});
    assert.equal(writes.length, 0, "historical preview must not dirty the document");
    frm.doc.start_date = "2026-02-01";
    await handlers.start_date(frm);
    frm.doc.start_date = "2026-03-01";
    await handlers.start_date(frm);
    const current = requests.at(-1), stale = requests.at(-2);
    await current.callback({message: {preserved: false, start_date: "2026-03-01", expiry_date: "2027-03-01", sections: ["NDT"], rule: policy}});
    await stale.callback({message: {preserved: false, expiry_date: "2027-02-01", sections: ["NDT"], rule: policy}});
    assert.equal(frm.doc.expiry_date, "2027-03-01", "stale preview must not overwrite the latest calculation");
    const originalSet = frm.set_value;
    let finishWrite;
    frm.set_value = changes => {
        Object.assign(frm.doc, changes);
        return new Promise(resolve => { finishWrite = resolve; });
    };
    frm.doc.start_date = "2026-04-01";
    await handlers.start_date(frm);
    const beforeRace = requests.length;
    const applying = requests.at(-1).callback({message: {preserved: false, expiry_date: "2027-04-01", sections: ["NDT"], rule: policy}});
    frm.doc.start_date = "2026-05-01";
    await handlers.start_date(frm);
    finishWrite();
    await applying;
    assert.equal(requests.length, beforeRace + 1, "editing while normalized fields are applied must queue a fresh preview");
    assert.equal(JSON.parse(requests.at(-1).args.values).start_date, "2026-05-01");
    frm.set_value = originalSet;
    process.stdout.write("Desk history, server preview and stale-response tests passed\n");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
