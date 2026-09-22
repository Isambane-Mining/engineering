const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");


function load_daily_summary_script() {
    const source = fs.readFileSync(
        path.join(__dirname, "daily_downtime_summary.js"),
        "utf8"
    );
    const context = {
        frappe: {
            ui: {
                form: {
                    on() {}
                }
            }
        }
    };

    vm.createContext(context);
    vm.runInContext(source, context);

    return context;
}


test("daily summary periods match all saved report types", () => {
    const context = load_daily_summary_script();

    assert.equal(context.get_daily_shift_period("Day Shift"), "06:00 - 18:00");
    assert.equal(context.get_daily_shift_period("Night Shift"), "18:00 - 06:00");
    assert.equal(context.get_daily_shift_period("Full Daily"), "06:00 - 06:00 next day");
});
