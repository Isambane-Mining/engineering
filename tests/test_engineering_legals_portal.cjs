const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

async function main() {
    const requests = [], elements = new Map();
    function element(id) {
        if (!elements.has(id)) elements.set(id, {
            value: "", textContent: id.endsWith("_json") ? "[]" : "", style: {}, files: [], listeners: {},
            addEventListener(event, fn) { this.listeners[event] = fn; },
            querySelector() { return {value: ""}; }, closest() { return {style: {}, contains() { return true; }}; }
        });
        return elements.get(id);
    }
    Object.assign(element("sections"), {value: "PDS"});
    Object.assign(element("site"), {value: "Gwab"});
    Object.assign(element("fleet_number"), {value: "EX001"});
    Object.assign(element("vehicle_type"), {value: "TMM"});
    Object.assign(element("start_date"), {value: "2026-01-31"});
    const html = fs.readFileSync(path.join(__dirname, "../engineering/templates/pages/engineering_legals_sup.html"), "utf8");
    const start = html.lastIndexOf("<script>") + "<script>".length;
    const script = html.slice(start, html.indexOf("</script>", start));
    vm.runInNewContext(script, {
        document: {getElementById: element, addEventListener() {}, createElement() { return {
            set innerHTML(text) { this.textContent = text; }, textContent: ""
        }; }},
        frappe: {csrf_token: "test-only"}, URLSearchParams, alert() {},
        fetch: (_url, options) => new Promise(resolve => requests.push({options, resolve}))
    });
    assert.equal(requests.length, 1, "portal must request server rules");
    const policy = {vehicle_options: ["LDV", "TMM"], vehicle_type: "TMM", lifting_options: [],
                    fleet_required: 1, start_date_policy: "Required", no_expiry: 0};
    requests[0].resolve({ok: true, json: async () => ({message: {sections: ["PDS"], rule: policy, expiry_date: "2026-04-30"}})});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(element("expiry_date").value, "2026-04-30");
    assert.equal(element("vehicle_type").required, true);
    element("start_date").value = "2026-02-01";
    element("start_date").listeners.change();
    element("start_date").value = "2026-03-01";
    element("start_date").listeners.change();
    requests[2].resolve({ok: true, json: async () => ({message: {sections: ["PDS"], rule: policy, expiry_date: "2026-06-01"}})});
    await new Promise(resolve => setImmediate(resolve));
    requests[1].resolve({ok: true, json: async () => ({message: {sections: ["PDS"], rule: policy, expiry_date: "2026-05-01"}})});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(element("expiry_date").value, "2026-06-01");
    element("start_date").listeners.change();
    requests[3].resolve({ok: false, json: async () => ({exc: "validation", _server_messages: JSON.stringify([JSON.stringify({message: "Section is inactive"})])})});
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(element("rule_error").textContent, "Section is inactive", "server validation errors must remain readable");
    process.stdout.write("Portal server expiry, requirements and stale-response tests passed\n");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
