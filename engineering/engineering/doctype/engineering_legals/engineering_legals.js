frappe.ui.form.on('Engineering Legals', {
  refresh(frm) {
    apply_asset_filter(frm);
    apply_section_rules(frm);
    apply_hsec_rules(frm);
    set_expiry_date(frm);
    add_eng_legals_report_button(frm);
    update_fleet_number_requirement(frm);
  },

  site(frm) {
    frm.set_value('fleet_number', null);
    apply_asset_filter(frm);
  },

  sections(frm) {
    frm.set_value('vehicle_type', null);
    frm.set_value('lifting_type', null);
    frm.set_value('brake_wear_type', null);

    const section = (frm.doc.sections || '').trim();

    // populate HSEC external code from selected section
    frm.set_value('hsec_qualification_id_external', section || null);

    // Auto-send only for HSEC sections
    const HSEC_SEND_SECTIONS = ['Brake Test', 'FRCS'];
    frm.set_value('hsec_send', HSEC_SEND_SECTIONS.includes(section) ? 1 : 0);

    apply_section_rules(frm);
    apply_hsec_rules(frm);
    set_expiry_date(frm);
    update_fleet_number_requirement(frm);
  },

  vehicle_type(frm) {
    set_expiry_date(frm);
  },

  lifting_type(frm) {
    set_expiry_date(frm);
  },

  brake_wear_type(frm) {
    set_expiry_date(frm);
  },

  start_date(frm) {
    set_expiry_date(frm);
  },

  hsec_send(frm) {
    apply_hsec_rules(frm);
  }
});


function apply_section_rules(frm) {
  const section = (frm.doc.sections || '').trim();

  frm.toggle_display('vehicle_type', false);
  frm.toggle_display('lifting_type', false);
  frm.toggle_display('brake_wear_type', false);
  frm.toggle_display('start_date', true);
  frm.toggle_display('expiry_date', true);

  frm.toggle_reqd('vehicle_type', false);
  frm.toggle_reqd('lifting_type', false);
  frm.toggle_reqd('brake_wear_type', false);
  frm.toggle_reqd('start_date', true);

  if (['Brake Test', 'PDS'].includes(section)) {
    frm.toggle_display('vehicle_type', true);
    frm.toggle_reqd('vehicle_type', true);
  }

  if (section === 'Lifting Equipment') {
    frm.toggle_display('lifting_type', true);
    frm.toggle_reqd('lifting_type', true);
  }

  if (section === 'Brake Wear Measurements') {
    frm.toggle_display('brake_wear_type', true);
    frm.toggle_reqd('brake_wear_type', true);
    frm.toggle_display('start_date', false);
    frm.toggle_display('expiry_date', false);
    frm.set_value('start_date', null);
    frm.set_value('expiry_date', null);
  }
}


function apply_hsec_rules(frm) {
  const send = !!frm.doc.hsec_send;

  // Only required if we are sending to HSEC
  frm.toggle_reqd('hsec_qualification_id_external', send);

  // Optional: hide the fields unless enabled
  frm.toggle_display('hsec_qual_category_id', send);
  frm.toggle_display('hsec_qualification_id_external', send);
  frm.toggle_display('hsec_inserted_at', send);
}


function set_expiry_date(frm) {
  const section = (frm.doc.sections || '').trim();
  const start = frm.doc.start_date;

  const NO_EXPIRY = new Set([
    'Machine Service Records',
    'Service Schedule',
    'Wearcheck',
    'Brake Wear Measurements'
  ]);

  if (NO_EXPIRY.has(section)) {
    frm.set_value('expiry_date', null);
    return;
  }

  if (!start) {
    frm.set_value('expiry_date', null);
    return;
  }

  const addMonths = (m) => frappe.datetime.add_months(start, m);

  let expiry = null;

  if (section === 'Brake Test') {
    if (frm.doc.vehicle_type === 'TMM') expiry = addMonths(1);
    else if (frm.doc.vehicle_type === 'LDV') expiry = addMonths(3);
  } else if (section === 'PDS') {
    if (frm.doc.vehicle_type === 'TMM') expiry = addMonths(3);
    else if (frm.doc.vehicle_type === 'LDV') expiry = addMonths(4);
  } else if (section === 'FRCS') {
    expiry = addMonths(3);
  } else if (section === 'Lifting Equipment') {
    if (frm.doc.lifting_type === 'Inspection') expiry = addMonths(3);
    else if (frm.doc.lifting_type === 'Certificate') expiry = addMonths(12);
  } else if (section === 'NDT' || section === 'Machine NDT') {
    expiry = addMonths(12);
  } else if (section === 'C-Track Inspection') {
    expiry = addMonths(1);
  } else if (section === 'Fire Suppression') {
    expiry = addMonths(3);
  } else if (section === 'Tyre Inspection Report') {
    expiry = addMonths(1);
  } else if (section === 'Illumination Baseline') {
    expiry = addMonths(24);
  } else if (section === 'Noise Level Baseline & Measurement') {
    expiry = addMonths(24);
  } else if (
    [
      'Brake Tester Calibration Certificate',
      'Brake Test Authorisations',
      'Multi-meter Calibration Certificate',
      'Authorised LV Person',
      'Pressure Vessels'
    ].includes(section)
  ) {
    expiry = addMonths(12);
  } else if (section === 'CoC for Containers, Offices, Workshops') {
    expiry = addMonths(1);
  } else if (section === 'Earth Leakage Testing') {
    expiry = addMonths(3);
  } else {
    expiry = null;
  }

  if (frm.doc.expiry_date !== expiry) {
    frm.set_value('expiry_date', expiry);
  }
}

function apply_asset_filter(frm) {
  frm.set_query('fleet_number', () => {
    return {
      filters: {
        docstatus: 1,
        location: frm.doc.site || ''
      }
    };
  });
}

function add_eng_legals_report_button(frm) {
  frm.remove_custom_button("Open Engineering Legals Report");

  frm.add_custom_button("Open Engineering Legals Report", () => {
    const params = new URLSearchParams({
      report_name: "Engineering Legals Report",
      as_at_date: frappe.datetime.get_today(),
      view: "Summary"
    });

    if (frm.doc.site) {
      params.set("site", frm.doc.site);
    }

    const url = `/desk/query-report/Engineering%20Legals%20Report?${params.toString()}`;
    window.open(url, "_blank");
  });
}

function update_fleet_number_requirement(frm) {
    const section = (frm.doc.sections || "").trim();

    const fleetOptionalSections = [
        "Brake Tester Calibration Certificate",
        "Brake Test Authorisations",
        "CoC for Containers, Offices, Workshops",
        "Multi-meter Calibration Certificate",
        "Authorised LV Person",
        "Earth Leakage Testing",
        "Pressure Vessels",
    ];

    const fleetIsOptional =
        fleetOptionalSections.includes(section);

    frm.set_df_property(
        "fleet_number",
        "reqd",
        fleetIsOptional ? 0 : 1
    );

    frm.refresh_field("fleet_number");
}
