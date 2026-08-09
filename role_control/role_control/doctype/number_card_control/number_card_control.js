// Copyright (c) 2026, Abdulla & Brusk and contributors
// For license information, please see license.txt

frappe.ui.form.on("Number Card Control", {
	refresh(frm) {
		frm.set_df_property("ignored_cards", "hidden", !frm.doc.is_system_seed);
		frm.set_df_property("section_break_ignored", "hidden", !frm.doc.is_system_seed);
	},
});
