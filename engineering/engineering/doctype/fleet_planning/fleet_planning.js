// Copyright (c) 2026, BuFf0k and contributors
// For license information, please see license.txt

// Same red/orange/green semantics as fleet_compliance.py's own
// _STATUS_COLOURS and the Fleet Compliance Dashboard's FCD_STATUS_META —
// a status means the same colour everywhere in Fleet.
const COMPLIANCE_COLOURS = {
	"Non-Compliant": "#c62828",
	"Attention Required": "#e65100",
	Compliant: "#2e7d32",
};

frappe.ui.form.on("Fleet Planning", {
	onload(frm) {
		// frm is reused across every Fleet Planning document opened in this
		// session (same "frm is reused" lesson already established for
		// Vehicle Allocation) — reset this per-document so a second "+ New"
		// later in the same session also gets its own auto-save attempt,
		// not one silently skipped because the flag was left true by an
		// earlier document.
		frm.__fleet_plan_auto_saving = false;
	},

	refresh(frm) {
		if (frm.is_new()) {
			// The whole point of this doctype is the current fleet
			// snapshot — there is no meaningful "blank" state worth
			// showing, so save immediately rather than making the user
			// click Save first just to see a populated board. after_insert
			// (server-side) does the actual import; saving is what makes
			// that fire. Guarded so a save that's already in flight (or
			// that failed) doesn't get retried on every refresh.
			if (!frm.__fleet_plan_auto_saving) {
				frm.__fleet_plan_auto_saving = true;
				frm.save();
			}

			return;
		}

		render_board(frm);
		setup_board(frm);
		refresh_board_compliance(frm);
	},
});

function refresh_board_compliance(frm) {
	// Colours reflect the board's CURRENT client-side state, including
	// edits not yet saved — get_board_compliance takes that state as an
	// explicit argument rather than reading the saved document, exactly
	// like the rest of this board never waits for a save to reflect an
	// edit. Cheap enough to just call again after every structural change
	// (add/remove Asset or Driver) rather than trying to diff — compliance
	// for the whole board computes in well under a second server-side even
	// at a few hundred cards (see the session's own profiling of
	// import_current_allocations, which does the same amount of work).
	const rows = (frm.doc.plan_assets || []).map((row) => ({
		asset: row.asset,
		required_licence_type: row.required_licence_type,
		drivers: (frm.doc.plan_drivers || []).filter((d) => d.asset === row.asset).map((d) => d.driver),
	}));

	if (!rows.length) {
		frm.__fleet_plan_compliance = { asset_status: {}, driver_status: {} };
		render_board(frm);
		return;
	}

	frappe.call({
		method: "engineering.engineering.doctype.fleet_planning.fleet_planning.get_board_compliance",
		args: { rows },
		callback(r) {
			frm.__fleet_plan_compliance = (r && r.message) || { asset_status: {}, driver_status: {} };
			render_board(frm);
		},
	});
}

function setup_board(frm) {
	// The Planning Board field's $wrapper is the same DOM node Frappe
	// reuses across every Fleet Planning document opened in this session
	// (same reasoning already established for Vehicle Allocation's driver
	// picker — see setup_driver_picker) — event delegation is bound once,
	// guarded so it's never bound twice, and never needs rebinding per
	// document since delegation reads frm.doc fresh on every event anyway.
	if (frm.__fleet_plan_board_bound) {
		return;
	}

	const field = frm.fields_dict.planning_board_html;

	if (!field) {
		return;
	}

	frm.__fleet_plan_board_bound = true;

	const $wrapper = field.$wrapper;
	let asset_search_timer = null;
	let driver_search_timer = null;

	// --- Add an Asset to the board ---
	$wrapper.on("input", "[data-fleet-plan-asset-search]", function () {
		const $input = $(this);
		const $results = $wrapper.find("[data-fleet-plan-asset-results]");
		const txt = $input.val();

		clearTimeout(asset_search_timer);

		if (!txt) {
			$results.hide().empty();
			return;
		}

		asset_search_timer = setTimeout(() => {
			frappe.call({
				method: "engineering.engineering.doctype.fleet_planning.fleet_planning.search_planning_assets",
				args: { doctype: "Asset", txt, searchfield: "name", start: 0, page_len: 20, filters: null },
				callback(r) {
					render_asset_search_results(frm, $wrapper, r.message || []);
				},
			});
		}, 250);
	});

	$wrapper.on("click", "[data-fleet-plan-card-remove]", function (e) {
		e.stopPropagation();
		remove_plan_asset(frm, $(this).attr("data-fleet-plan-card-remove"));
	});

	// --- Add/remove a Driver on a card ---
	$wrapper.on("input", "[data-fleet-plan-driver-search]", function () {
		const $input = $(this);
		const asset = $input.attr("data-fleet-plan-driver-search");
		const $results = $wrapper.find(`[data-fleet-plan-driver-results="${css_escape(asset)}"]`);
		const txt = $input.val();

		clearTimeout(driver_search_timer);

		if (!txt) {
			$results.hide().empty();
			return;
		}

		driver_search_timer = setTimeout(() => {
			frappe.call({
				method: "frappe.desk.search.search_link",
				args: { doctype: "Employee", txt, reference_doctype: "Fleet Planning Driver" },
				callback(r) {
					render_driver_search_results(frm, $wrapper, asset, r.message || []);
				},
			});
		}, 250);
	});

	$wrapper.on("click", "[data-fleet-plan-driver-remove]", function (e) {
		e.stopPropagation();
		const [asset, driver] = $(this).attr("data-fleet-plan-driver-remove").split("|");
		remove_plan_driver(frm, asset, driver);
	});

	$wrapper.on("change", "[data-fleet-plan-card-temp]", function () {
		const asset = $(this).attr("data-fleet-plan-card-temp");
		const row = (frm.doc.plan_assets || []).find((r) => r.asset === asset);

		if (!row) {
			return;
		}

		row.is_temp = $(this).is(":checked") ? 1 : 0;
		frm.dirty();
	});

	// --- Drag and drop between Location rows ---
	$wrapper.on("dragstart", "[data-fleet-plan-card]", function (e) {
		e.originalEvent.dataTransfer.setData("text/plain", $(this).attr("data-fleet-plan-card"));
		e.originalEvent.dataTransfer.effectAllowed = "move";
	});

	$wrapper.on("dragover", "[data-fleet-plan-row-cards]", function (e) {
		e.preventDefault();
		$(this).css("background", "var(--fg-hover-color)");
	});

	$wrapper.on("dragleave", "[data-fleet-plan-row-cards]", function () {
		$(this).css("background", "");
	});

	$wrapper.on("drop", "[data-fleet-plan-row-cards]", function (e) {
		e.preventDefault();
		$(this).css("background", "");

		const asset = e.originalEvent.dataTransfer.getData("text/plain");
		const location = $(this).attr("data-fleet-plan-row-cards");

		move_plan_asset(frm, asset, location);
	});

	$(document).on("click.fleet_plan_board", (e) => {
		if (!$(e.target).closest($wrapper).length) {
			$wrapper.find("[data-fleet-plan-asset-results]").hide();
			$wrapper.find("[data-fleet-plan-driver-results]").hide();
		}
	});
}

function css_escape(value) {
	return (value || "").replace(/["\\]/g, "\\$&");
}

function render_asset_search_results(frm, $wrapper, matches) {
	const $results = $wrapper.find("[data-fleet-plan-asset-results]");
	const existing = (frm.doc.plan_assets || []).map((row) => row.asset);
	const filtered = matches.filter((m) => !existing.includes(m.value));
	const esc = frappe.utils.escape_html;

	if (!filtered.length) {
		$results.html(`<div class="fleet-plan-search-empty">${__("No matches")}</div>`).show();
		return;
	}

	$results
		.html(
			filtered
				.map(
					(m) =>
						`<div class="fleet-plan-search-result" data-value="${esc(m.value)}" data-label="${esc(m.description || "")}" data-item-name="${esc(m.item_name || "")}">${esc(m.value)} - ${esc(m.description || m.label || "")}</div>`
				)
				.join("")
		)
		.show();

	$results.find(".fleet-plan-search-result").on("click", function () {
		add_plan_asset(frm, $(this).attr("data-value"), $(this).attr("data-label"), $(this).attr("data-item-name"));
		$wrapper.find("[data-fleet-plan-asset-search]").val("");
		$results.hide().empty();
	});
}

function render_driver_search_results(frm, $wrapper, asset, matches) {
	const $results = $wrapper.find(`[data-fleet-plan-driver-results="${css_escape(asset)}"]`);
	const existing = (frm.doc.plan_drivers || []).filter((r) => r.asset === asset).map((r) => r.driver);
	const filtered = matches.filter((m) => !existing.includes(m.value));
	const esc = frappe.utils.escape_html;

	if (!filtered.length) {
		$results.html(`<div class="fleet-plan-search-empty">${__("No matches")}</div>`).show();
		return;
	}

	$results
		.html(
			filtered
				.map(
					(m) =>
						`<div class="fleet-plan-search-result" data-value="${esc(m.value)}" data-label="${esc(m.description || "")}">${esc(m.value)} - ${esc(m.description || m.label || "")}</div>`
				)
				.join("")
		)
		.show();

	$results.find(".fleet-plan-search-result").on("click", function () {
		add_plan_driver(frm, asset, $(this).attr("data-value"), $(this).attr("data-label"));
		$wrapper.find(`[data-fleet-plan-driver-search="${css_escape(asset)}"]`).val("");
		$results.hide().empty();
	});
}

function add_plan_asset(frm, asset, asset_name, item_name) {
	if (!asset || (frm.doc.plan_assets || []).some((row) => row.asset === asset)) {
		return;
	}

	const row = frappe.model.add_child(frm.doc, "Fleet Planning Asset", "plan_assets");
	row.asset = asset;
	row.asset_name = asset_name || asset;
	row.item_name = item_name || "";
	frm.dirty();
	render_board(frm);
	refresh_board_compliance(frm);
}

function remove_plan_asset(frm, asset) {
	const row = (frm.doc.plan_assets || []).find((r) => r.asset === asset);

	if (!row) {
		return;
	}

	frappe.model.clear_doc("Fleet Planning Asset", row.name);
	frm.doc.plan_assets = (frm.doc.plan_assets || []).filter((r) => r.asset !== asset);

	(frm.doc.plan_drivers || [])
		.filter((r) => r.asset === asset)
		.forEach((r) => frappe.model.clear_doc("Fleet Planning Driver", r.name));
	frm.doc.plan_drivers = (frm.doc.plan_drivers || []).filter((r) => r.asset !== asset);

	frm.dirty();
	render_board(frm);
	refresh_board_compliance(frm);
}

function add_plan_driver(frm, asset, employee, employee_label) {
	if (!employee || (frm.doc.plan_drivers || []).some((r) => r.asset === asset && r.driver === employee)) {
		return;
	}

	const row = frappe.model.add_child(frm.doc, "Fleet Planning Driver", "plan_drivers");
	row.asset = asset;
	row.driver = employee;
	row.driver_name = employee_label || employee;
	frm.dirty();
	render_board(frm);
	refresh_board_compliance(frm);
}

function remove_plan_driver(frm, asset, driver) {
	const row = (frm.doc.plan_drivers || []).find((r) => r.asset === asset && r.driver === driver);

	if (!row) {
		return;
	}

	frappe.model.clear_doc("Fleet Planning Driver", row.name);
	frm.doc.plan_drivers = (frm.doc.plan_drivers || []).filter((r) => r !== row);
	frm.dirty();
	render_board(frm);
	refresh_board_compliance(frm);
}

function move_plan_asset(frm, asset, location) {
	const row = (frm.doc.plan_assets || []).find((r) => r.asset === asset);

	if (!row) {
		return;
	}

	const new_location = location || null;

	if ((row.location || "") === (new_location || "")) {
		return;
	}

	row.location = new_location;
	frm.dirty();
	render_board(frm);
}

const BOARD_STYLE = `
<style>
  .fleet-plan-toolbar { position: relative; margin-bottom: 14px; max-width: 420px; }
  .fleet-plan-toolbar input {
    width: 100%; padding: 6px 10px; border: 1px solid var(--border-color); border-radius: 6px; font-size: 13px;
  }
  .fleet-plan-search-result, .fleet-plan-search-empty {
    padding: 6px 10px; font-size: 12px; cursor: pointer;
  }
  .fleet-plan-search-empty { color: var(--text-muted); cursor: default; }
  .fleet-plan-search-result:hover { background: var(--fg-hover-color); }
  [data-fleet-plan-asset-results], [data-fleet-plan-driver-results] {
    display: none; position: absolute; z-index: 50; left: 0; right: 0; top: 100%;
    background: var(--fg-color); border: 1px solid var(--border-color); border-radius: 6px;
    max-height: 220px; overflow-y: auto; box-shadow: var(--shadow-md);
  }
  .fleet-plan-row { border: 1px solid var(--border-color); border-radius: 8px; margin-bottom: 12px; overflow: hidden; }
  .fleet-plan-row-header {
    padding: 6px 12px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.3px;
    color: var(--text-muted); background: var(--control-bg); border-bottom: 1px solid var(--border-color);
  }
  .fleet-plan-row-cards {
    display: flex; flex-wrap: wrap; gap: 10px; padding: 10px; min-height: 56px; background: var(--card-bg, transparent);
  }
  .fleet-plan-card {
    border: 1px solid var(--border-color); border-radius: 8px; padding: 8px 10px; width: 220px;
    background: var(--fg-color); cursor: grab; position: relative;
  }
  .fleet-plan-card-header { display: flex; justify-content: space-between; align-items: baseline; font-size: 13px; font-weight: 600; }
  .fleet-plan-card-remove { cursor: pointer; color: var(--text-muted); font-size: 14px; line-height: 1; }
  .fleet-plan-card-remove:hover { color: var(--text-color); }
  .fleet-plan-card-model { font-size: 11px; color: var(--text-muted); margin: 2px 0 6px; }
  .fleet-plan-card-temp { font-size: 11px; display: flex; align-items: center; gap: 4px; margin-bottom: 6px; }
  .fleet-plan-driver-chip {
    display: inline-flex; align-items: center; gap: 4px; font-size: 11px; padding: 2px 6px; border-radius: 10px;
    background: var(--control-bg); margin: 0 4px 4px 0;
  }
  .fleet-plan-driver-chip span { cursor: pointer; color: var(--text-muted); }
  .fleet-plan-driver-chip span:hover { color: var(--text-color); }
  .fleet-plan-driver-add { position: relative; margin-top: 4px; }
  .fleet-plan-driver-add input { width: 100%; font-size: 11px; padding: 3px 6px; border: 1px solid var(--border-color); border-radius: 4px; }
  .fleet-plan-legend { display: flex; gap: 16px; margin-bottom: 14px; font-size: 11px; color: var(--text-muted); }
  .fleet-plan-legend-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }
</style>
`;

function render_board(frm) {
	const field = frm.fields_dict.planning_board_html;

	if (!field) {
		return;
	}

	const esc = frappe.utils.escape_html;
	const compliance = frm.__fleet_plan_compliance || { asset_status: {}, driver_status: {} };
	const rows_by_location = {};

	(frm.doc.plan_assets || []).forEach((row) => {
		const key = row.location || "";
		rows_by_location[key] = rows_by_location[key] || [];
		rows_by_location[key].push(row);
	});

	const drivers_by_asset = {};

	(frm.doc.plan_drivers || []).forEach((row) => {
		drivers_by_asset[row.asset] = drivers_by_asset[row.asset] || [];
		drivers_by_asset[row.asset].push(row);
	});

	const locations = Object.keys(rows_by_location).sort((a, b) => {
		if (a === "" || b === "") {
			return a === "" ? -1 : 1;
		}

		return a.localeCompare(b);
	});

	if (!locations.includes("")) {
		locations.unshift("");
	}

	const rows_html = locations
		.map((location) => {
			const cards = rows_by_location[location] || [];
			const label = location || __("Unallocated");
			const editable = frm.doc.docstatus === 0;

			const cards_html = cards
				.map((card) => {
					const drivers = drivers_by_asset[card.asset] || [];
					const drivers_html = drivers
						.map((d) => {
							const driver_key = `${d.driver}|${card.required_licence_type || ""}`;
							const driver_colour = COMPLIANCE_COLOURS[compliance.driver_status[driver_key]];
							const chip_style = driver_colour ? ` style="background:${driver_colour}; color:#fff;"` : "";

							return `
							<span class="fleet-plan-driver-chip" data-fleet-plan-driver-chip="${esc(card.asset)}|${esc(d.driver)}"${chip_style}>
								${esc(d.driver_name || d.driver)}
								${editable ? `<span data-fleet-plan-driver-remove="${esc(card.asset)}|${esc(d.driver)}">&times;</span>` : ""}
							</span>`;
						})
						.join("");

					const card_colour = COMPLIANCE_COLOURS[compliance.asset_status[card.asset]] || "var(--border-color)";

					return `
						<div class="fleet-plan-card" ${editable ? 'draggable="true"' : ""} data-fleet-plan-card="${esc(card.asset)}" style="border-left: 4px solid ${card_colour};">
							<div class="fleet-plan-card-header">
								<span>${esc(card.asset)}${card.asset_name ? " - " + esc(card.asset_name) : ""}</span>
								${editable ? `<span class="fleet-plan-card-remove" data-fleet-plan-card-remove="${esc(card.asset)}">&times;</span>` : ""}
							</div>
							<div class="fleet-plan-card-model">${esc(card.item_name || "")}</div>
							<label class="fleet-plan-card-temp">
								<input type="checkbox" data-fleet-plan-card-temp="${esc(card.asset)}" ${card.is_temp ? "checked" : ""} ${editable ? "" : "disabled"}>
								${__("Temporary Loan")}
							</label>
							<div>
								${drivers_html}
							</div>
							${
								editable
									? `<div class="fleet-plan-driver-add">
										<input type="text" placeholder="${__("+ driver")}" data-fleet-plan-driver-search="${esc(card.asset)}">
										<div data-fleet-plan-driver-results="${esc(card.asset)}"></div>
									</div>`
									: ""
							}
						</div>`;
				})
				.join("");

			return `
				<div class="fleet-plan-row">
					<div class="fleet-plan-row-header">${esc(label)} (${cards.length})</div>
					<div class="fleet-plan-row-cards" data-fleet-plan-row-cards="${esc(location)}">${cards_html}</div>
				</div>`;
		})
		.join("");

	const toolbar_html =
		frm.doc.docstatus === 0
			? `<div class="fleet-plan-toolbar">
				<input type="text" placeholder="${__("Add an Asset to the board…")}" data-fleet-plan-asset-search>
				<div data-fleet-plan-asset-results></div>
			</div>`
			: "";

	const legend_html = `
		<div class="fleet-plan-legend">
			<span><span class="fleet-plan-legend-dot" style="background:${COMPLIANCE_COLOURS["Non-Compliant"]};"></span>${__("Non-Compliant")}</span>
			<span><span class="fleet-plan-legend-dot" style="background:${COMPLIANCE_COLOURS["Attention Required"]};"></span>${__("Attention Required")}</span>
			<span><span class="fleet-plan-legend-dot" style="background:${COMPLIANCE_COLOURS["Compliant"]};"></span>${__("Compliant")}</span>
		</div>`;

	field.$wrapper.html(BOARD_STYLE + toolbar_html + legend_html + rows_html);
}
