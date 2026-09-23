// Covers both the Overall Status vocabulary (Non-Compliant/Attention
// Required/Not Registered/Compliant) AND the per-item vocabulary used by
// the Vehicle Licence/Driver Licence/Addendum columns (Valid/On File/
// Expiring/Incomplete/Expired/Outstanding/Not Applicable) — these three
// columns were previously falling through to status_chip()'s plain-gray
// fallback on every row, since only the Overall Status keys were mapped
// here. Same red/orange/green semantics as fleet_compliance.py's own
// _STATUS_COLOURS, so a status means the same colour everywhere in Fleet.
const FCD_STATUS_META = {
	"Non-Compliant": { bg: "var(--bg-red)", fg: "var(--text-on-red)" },
	"Attention Required": { bg: "var(--bg-orange)", fg: "var(--text-on-orange)" },
	"Not Registered": { bg: "var(--bg-gray)", fg: "var(--text-on-gray)" },
	Compliant: { bg: "var(--bg-green)", fg: "var(--text-on-green)" },
	Valid: { bg: "var(--bg-green)", fg: "var(--text-on-green)" },
	"On File": { bg: "var(--bg-green)", fg: "var(--text-on-green)" },
	Expiring: { bg: "var(--bg-orange)", fg: "var(--text-on-orange)" },
	Incomplete: { bg: "var(--bg-orange)", fg: "var(--text-on-orange)" },
	Expired: { bg: "var(--bg-red)", fg: "var(--text-on-red)" },
	Outstanding: { bg: "var(--bg-red)", fg: "var(--text-on-red)" },
	"Not Applicable": { bg: "var(--bg-gray)", fg: "var(--text-on-gray)" },
};

// Per-Asset Allocation/Licence history — lazy-loaded once per Asset and
// kept for the life of the page so re-expanding doesn't refetch.
const FCD_HISTORY_CACHE = {};

frappe.pages["fleet-compliance-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: __("Fleet Compliance Dashboard"),
		single_column: true,
	});

	const filters = {
		location: page.add_field({
			fieldname: "location",
			label: __("Location"),
			fieldtype: "Link",
			options: "Location",
			change: () => refresh(),
		}),
		asset_category: page.add_field({
			fieldname: "asset_category",
			label: __("Asset Category"),
			fieldtype: "Link",
			options: "Asset Category",
			get_query: () => ({
				query: "engineering.engineering.doctype.fleet_management_settings.fleet_management_settings.public_road_asset_category_query",
			}),
			change: () => refresh(),
		}),
		driver: page.add_field({
			fieldname: "driver",
			label: __("Driver"),
			fieldtype: "Link",
			options: "Employee",
			change: () => refresh(),
		}),
	};

	page.set_primary_action(__("Refresh"), () => refresh(), "refresh");
	page.add_inner_button(__("Open as Report"), () => frappe.set_route("query-report", "Fleet Compliance Overview"));
	page.add_inner_button(__("Export to Excel"), () => {
		frappe.call({
			method: "engineering.engineering.doctype.vehicle_allocation.vehicle_allocation.export_road_asset_register_xlsx",
			freeze: true,
			freeze_message: __("Building Excel file…"),
			callback(r) {
				if (!r || !r.message || !r.message.content) return;

				const filename = r.message.filename || "road_asset_register.xlsx";
				const mime = r.message.type || "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

				download_base64_file_fleet_compliance_dashboard(r.message.content, filename, mime);
			},
		});
	});

	const $container = $("<div class='fcd-page'></div>").appendTo(page.main);

	$container.html(`
		<style>
			.fcd-page { padding: 18px 4px 40px; color: var(--text-color); }
			.fcd-page .fcd-note { color: var(--text-muted); margin-bottom: 16px; font-size: 12px; }
			.fcd-panel {
				background: var(--card-bg);
				border: 1px solid var(--border-color);
				border-radius: 10px;
				padding: 16px;
				margin-bottom: 18px;
			}
			.fcd-panel h4 {
				margin: 0 0 12px;
				font-size: 14px;
				font-weight: 700;
				text-transform: uppercase;
				letter-spacing: 0.3px;
				color: var(--text-color);
			}
			.fcd-panel-empty { color: var(--text-muted); padding: 10px 2px; font-size: 13px; }

			.fcd-bubble-row { display: flex; gap: 12px; flex-wrap: wrap; }
			.fcd-bubble {
				flex: 1 1 160px;
				min-width: 140px;
				border-radius: 10px;
				padding: 14px 16px;
				cursor: pointer;
				border: 1px solid var(--border-color);
				transition: transform 0.08s ease;
			}
			.fcd-bubble:hover { transform: translateY(-2px); }
			.fcd-bubble.fcd-active { outline: 2px solid var(--primary); outline-offset: 1px; }
			.fcd-bubble-value { font-size: 28px; font-weight: 800; line-height: 1.1; }
			.fcd-bubble-label { font-size: 11px; font-weight: 700; text-transform: uppercase; margin-top: 4px; opacity: 0.85; }

			.fcd-search { margin-bottom: 12px; }
			.fcd-search input { max-width: 320px; }

			.fcd-table { width: 100%; border-collapse: collapse; font-size: 12px; }
			.fcd-table th, .fcd-table td {
				border-bottom: 1px solid var(--border-color);
				padding: 7px 10px;
				text-align: left;
				color: var(--text-color);
				white-space: nowrap;
			}
			.fcd-table th { color: var(--text-muted); font-weight: 700; text-transform: uppercase; font-size: 10.5px; }
			.fcd-table tr:hover td { background: var(--fg-hover-color); }
			.fcd-status-chip {
				display: inline-block;
				padding: 2px 8px;
				border-radius: 999px;
				font-size: 10.5px;
				font-weight: 700;
				white-space: nowrap;
			}

			.fcd-tree details { border: 1px solid var(--border-color); border-radius: 8px; padding: 8px 10px; margin: 6px 0; background: var(--fg-color); }
			.fcd-tree summary { cursor: pointer; font-weight: 700; color: var(--text-color); display: flex; align-items: center; gap: 8px; }
			.fcd-tree .fcd-tree-count { color: var(--text-muted); font-weight: 400; }
			.fcd-tree .fcd-tree-body { margin-top: 10px; overflow: auto; }
			.fcd-tree .fcd-tree-dots { display: inline-flex; gap: 4px; margin-left: auto; }
			.fcd-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }

			.fcd-asset-row { cursor: default; }
			.fcd-expand-cell { cursor: pointer; width: 18px; text-align: center; }
			.fcd-expand-icon { display: inline-block; font-size: 9px; color: var(--text-muted); transition: transform 0.1s ease; }
			.fcd-expand-icon.fcd-expanded { transform: rotate(90deg); }
			.fcd-history-row td { background: var(--fg-color); white-space: normal; padding: 12px; }
			.fcd-history-section { margin-bottom: 14px; }
			.fcd-history-section:last-child { margin-bottom: 0; }
			.fcd-history-title { font-size: 11px; font-weight: 700; text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px; }
		</style>

		<div class="fcd-note">
			${__("Every submitted public-road Asset — registered or not — with its live compliance status. Click a bubble to filter by status; each category is expanded by default; click the arrow on an Asset row to see its underlying Vehicle Allocation and Vehicle Licence history.")}
		</div>

		<div class="fcd-panel">
			<h4>${__("Overall Status")}</h4>
			<div class="fcd-bubble-row" id="fcd-bubbles"><div class="fcd-panel-empty">${__("Loading…")}</div></div>
		</div>

		<div class="fcd-panel">
			<h4>${__("By Asset Category")}</h4>
			<div class="fcd-search"><input type="text" class="input-with-feedback form-control" id="fcd-search-input" placeholder="${__("Search Asset, Driver…")}"></div>
			<div class="fcd-tree" id="fcd-tree"><div class="fcd-panel-empty">${__("Loading…")}</div></div>
		</div>
	`);

	let active_status = null;
	let all_rows = [];
	let search_text = "";

	function get_filter_values() {
		return {
			location: filters.location.get_value() || "",
			asset_category: filters.asset_category.get_value() || "",
			driver: filters.driver.get_value() || "",
		};
	}

	function refresh() {
		active_status = null;
		render_bubbles();
		render_tree();
	}

	function render_bubbles() {
		frappe.call({
			method: "engineering.engineering.page.fleet_compliance_dashboard.fleet_compliance_dashboard.get_summary",
			args: get_filter_values(),
			callback: (r) => {
				render_bubble_row((r && r.message) || { total: 0, by_status: [] });
			},
		});
	}

	function render_bubble_row(summary) {
		const $bubbles = $container.find("#fcd-bubbles");
		const rows = summary.by_status || [];

		if (!rows.length) {
			$bubbles.html(`<div class="fcd-panel-empty">${__("No public-road Assets found.")}</div>`);
			return;
		}

		const total_active = active_status === null ? "fcd-active" : "";
		const total_bubble = `
			<div class="fcd-bubble ${total_active}" data-status="" style="background:var(--control-bg); color:var(--text-color);">
				<div class="fcd-bubble-value">${frappe.utils.escape_html(String(summary.total || 0))}</div>
				<div class="fcd-bubble-label">${__("Total")}</div>
			</div>
		`;

		const status_bubbles = rows
			.map((r) => {
				const meta = FCD_STATUS_META[r.status] || { bg: "var(--control-bg)", fg: "var(--text-color)" };
				const active_cls = active_status === r.status ? "fcd-active" : "";
				return `
					<div class="fcd-bubble ${active_cls}" data-status="${frappe.utils.escape_html(r.status)}" style="background:${meta.bg}; color:${meta.fg};">
						<div class="fcd-bubble-value">${frappe.utils.escape_html(String(r.count || 0))}</div>
						<div class="fcd-bubble-label">${frappe.utils.escape_html(__(r.status))}</div>
					</div>
				`;
			})
			.join("");

		$bubbles.html(total_bubble + status_bubbles);

		$bubbles.find(".fcd-bubble").on("click", function () {
			const status = $(this).attr("data-status");
			// Clicking the already-active bubble (or Total) clears the filter.
			active_status = !status || active_status === status ? null : status;
			render_bubble_row(summary);
			render_tree();
		});
	}

	function render_tree() {
		const $tree = $container.find("#fcd-tree");
		$tree.html(`<div class="fcd-panel-empty">${__("Loading…")}</div>`);

		const args = { ...get_filter_values(), overall_status: active_status || "" };

		frappe.call({
			method: "engineering.engineering.page.fleet_compliance_dashboard.fleet_compliance_dashboard.get_rows",
			args,
			callback: (r) => {
				all_rows = (r && r.message) || [];
				render_tree_html();
			},
		});
	}

	function filtered_rows() {
		if (!search_text) {
			return all_rows;
		}

		const needle = search_text.toLowerCase();

		return all_rows.filter((row) => {
			const haystack = [row.asset, row.item_name, row.drivers, row.location, row.comments]
				.filter(Boolean)
				.join(" ")
				.toLowerCase();

			return haystack.includes(needle);
		});
	}

	function render_tree_html() {
		const $tree = $container.find("#fcd-tree");
		const rows = filtered_rows();

		if (!rows.length) {
			$tree.html(`<div class="fcd-panel-empty">${__("No records match the current filters.")}</div>`);
			return;
		}

		const by_category = {};
		rows.forEach((row) => {
			const category = row.asset_category || __("Uncategorised");
			(by_category[category] = by_category[category] || []).push(row);
		});

		const esc = frappe.utils.escape_html;

		const html = Object.keys(by_category)
			.sort()
			.map((category) => {
				const cat_rows = by_category[category];
				const dots = Object.keys(FCD_STATUS_META)
					.map((status) => {
						const count = cat_rows.filter((r) => r.overall_status === status).length;
						if (!count) return "";
						const meta = FCD_STATUS_META[status];
						return `<span class="fcd-dot" style="background:${meta.bg};" title="${esc(status)}: ${count}"></span>`;
					})
					.join("");

				return `
					<details class="fcd-category-node" open>
						<summary>
							${esc(category)} <span class="fcd-tree-count">(${cat_rows.length})</span>
							<span class="fcd-tree-dots">${dots}</span>
						</summary>
						<div class="fcd-tree-body">${render_rows_table(cat_rows)}</div>
					</details>
				`;
			})
			.join("");

		$tree.html(html);
	}

	function render_rows_table(rows) {
		const esc = frappe.utils.escape_html;

		const status_chip = (status) => {
			const meta = FCD_STATUS_META[status] || { bg: "var(--control-bg)", fg: "var(--text-color)" };
			return `<span class="fcd-status-chip" style="background:${meta.bg}; color:${meta.fg};">${esc(status || "")}</span>`;
		};

		const trs = rows
			.map((r) => {
				const href = r.allocation
					? `/app/vehicle-allocation/${encodeURIComponent(r.allocation)}`
					: `/app/asset/${encodeURIComponent(r.asset)}`;
				const asset_key = esc(r.asset || "");

				return `
					<tr class="fcd-asset-row" data-asset="${asset_key}">
						<td class="fcd-expand-cell"><span class="fcd-expand-icon">▶</span></td>
						<td><a href="${href}" target="_blank" rel="noopener noreferrer">${esc(r.asset || "")}</a></td>
						<td>${esc(r.item_name || "")}</td>
						<td>${esc(r.registered || "")}</td>
						<td>${esc(r.location || "")}</td>
						<td>${esc(r.drivers || "")}</td>
						<td>${status_chip(r.vehicle_licence_status)}</td>
						<td>${status_chip(r.driver_licence_status)}</td>
						<td>${status_chip(r.addendum_status)}</td>
						<td>${status_chip(r.overall_status)}</td>
						<td>${esc(r.comments || "")}</td>
					</tr>
					<tr class="fcd-history-row" data-asset="${asset_key}" hidden>
						<td colspan="11">
							<div class="fcd-history-body fcd-panel-empty">${__("Expand to load…")}</div>
						</td>
					</tr>
				`;
			})
			.join("");

		return `
			<table class="fcd-table">
				<thead>
					<tr>
						<th></th>
						<th>${__("Asset")}</th>
						<th>${__("Item Name")}</th>
						<th>${__("Registered")}</th>
						<th>${__("Location")}</th>
						<th>${__("Drivers")}</th>
						<th>${__("Vehicle Licence")}</th>
						<th>${__("Driver Licence")}</th>
						<th>${__("Undertaking")}</th>
						<th>${__("Overall Status")}</th>
						<th>${__("Comments")}</th>
					</tr>
				</thead>
				<tbody>${trs}</tbody>
			</table>
		`;
	}

	function render_history_html(data) {
		const esc = frappe.utils.escape_html;
		const allocations = data.allocations || [];
		const licences = data.licences || [];

		const alloc_rows =
			allocations
				.map(
					(a) => `
					<tr>
						<td><a href="/app/vehicle-allocation/${encodeURIComponent(a.name)}" target="_blank" rel="noopener noreferrer">${esc(a.name)}</a></td>
						<td>${esc(a.location || "")}</td>
						<td>${esc(a.drivers || "")}</td>
						<td>${esc(a.valid_from ? String(a.valid_from) : "")}</td>
						<td>${esc(a.valid_to ? String(a.valid_to) : "")}</td>
						<td>${esc(a.status || "")}</td>
						<td>${esc(a.docstatus_label || "")}</td>
					</tr>
				`
				)
				.join("") ||
			`<tr><td colspan="7" style="text-align:center;">${__("No Vehicle Allocation records")}</td></tr>`;

		const lic_rows =
			licences
				.map((l) => {
					const attach = (l.attach || "").trim();
					const open_link = attach
						? `<a href="${encodeURI(attach)}" target="_blank" rel="noopener noreferrer">${__("Open")}</a>`
						: `<span style="color:var(--text-muted);">${__("No File")}</span>`;

					return `
						<tr>
							<td><a href="/app/vehicle-licence/${encodeURIComponent(l.name)}" target="_blank" rel="noopener noreferrer">${esc(l.name)}</a></td>
							<td>${esc(l.site || "")}</td>
							<td>${esc(l.registration_number || "")}</td>
							<td>${esc(l.issue_date ? String(l.issue_date) : "")}</td>
							<td>${esc(l.expiry_date ? String(l.expiry_date) : "")}</td>
							<td>${esc(l.docstatus_label || "")}</td>
							<td>${open_link}</td>
						</tr>
					`;
				})
				.join("") ||
			`<tr><td colspan="7" style="text-align:center;">${__("No Vehicle Licence records")}</td></tr>`;

		return `
			<div class="fcd-history-section">
				<div class="fcd-history-title">${__("Vehicle Allocations")}</div>
				<table class="fcd-table">
					<thead>
						<tr>
							<th>${__("Name")}</th>
							<th>${__("Location")}</th>
							<th>${__("Drivers")}</th>
							<th>${__("Valid From")}</th>
							<th>${__("Valid To")}</th>
							<th>${__("Status")}</th>
							<th>${__("Docstatus")}</th>
						</tr>
					</thead>
					<tbody>${alloc_rows}</tbody>
				</table>
			</div>
			<div class="fcd-history-section">
				<div class="fcd-history-title">${__("Vehicle Licences")}</div>
				<table class="fcd-table">
					<thead>
						<tr>
							<th>${__("Name")}</th>
							<th>${__("Site")}</th>
							<th>${__("Registration")}</th>
							<th>${__("Issue Date")}</th>
							<th>${__("Expiry Date")}</th>
							<th>${__("Docstatus")}</th>
							<th>${__("Attachment")}</th>
						</tr>
					</thead>
					<tbody>${lic_rows}</tbody>
				</table>
			</div>
		`;
	}

	function load_asset_history(asset, $body) {
		if (FCD_HISTORY_CACHE[asset]) {
			$body.html(render_history_html(FCD_HISTORY_CACHE[asset]));
			return;
		}

		$body.html(`<div class="fcd-panel-empty">${__("Loading…")}</div>`);

		frappe.call({
			method: "engineering.engineering.page.fleet_compliance_dashboard.fleet_compliance_dashboard.get_asset_history",
			args: { asset },
			callback: (r) => {
				const data = (r && r.message) || { allocations: [], licences: [] };
				FCD_HISTORY_CACHE[asset] = data;
				$body.html(render_history_html(data));
			},
		});
	}

	$container.on("input", "#fcd-search-input", function () {
		search_text = $(this).val().trim();
		render_tree_html();
	});

	// Delegated: the tree/table is rebuilt on every refresh/search, so bind
	// once on the container rather than per-row.
	$container.on("click", ".fcd-expand-cell", function () {
		const $row = $(this).closest("tr.fcd-asset-row");
		const asset = $row.attr("data-asset");
		const $history_row = $row.next("tr.fcd-history-row");
		const $icon = $(this).find(".fcd-expand-icon");
		const is_collapsed = $history_row.attr("hidden") !== undefined;

		if (is_collapsed) {
			$history_row.removeAttr("hidden");
			$icon.addClass("fcd-expanded");
			load_asset_history(asset, $history_row.find(".fcd-history-body"));
		} else {
			$history_row.attr("hidden", true);
			$icon.removeClass("fcd-expanded");
		}
	});

	refresh();
};

function download_base64_file_fleet_compliance_dashboard(base64_content, filename, mime_type) {
	const byte_chars = atob(base64_content);
	const byte_numbers = new Array(byte_chars.length);

	for (let i = 0; i < byte_chars.length; i++) {
		byte_numbers[i] = byte_chars.charCodeAt(i);
	}

	const byte_array = new Uint8Array(byte_numbers);
	const blob = new Blob([byte_array], { type: mime_type });
	const url = window.URL.createObjectURL(blob);

	const link = document.createElement("a");
	link.href = url;
	link.download = filename;

	document.body.appendChild(link);
	link.click();
	document.body.removeChild(link);

	window.URL.revokeObjectURL(url);
}
