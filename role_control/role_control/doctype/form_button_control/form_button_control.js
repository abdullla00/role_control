// Copyright (c) 2026, Abdulla & Brusk and contributors
// For license information, please see license.txt

frappe.provide("role_control.form_button_control_config");

const BUTTON_LABEL_CATEGORIES = ["Custom", "Menu Action"];

role_control.form_button_control_config = {
	setup_queries(frm) {
		frm.set_query("reference_doctype", "buttons", function () {
			return {
				filters: { istable: 0 },
			};
		});

		frm.set_query("button_label", "buttons", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (!row?.reference_doctype || !BUTTON_LABEL_CATEGORIES.includes(row.button_category)) {
				return;
			}

			return {
				query: "role_control.role_control.api.button_discovery.search_button_labels",
				params: {
					reference_doctype: row.reference_doctype,
					button_category: row.button_category,
					view: row.view || "Form",
				},
			};
		});

		frm.set_query("button_group", "buttons", function (doc, cdt, cdn) {
			const row = locals[cdt][cdn];
			if (row?.button_category !== "Custom" || !row?.reference_doctype) {
				return;
			}

			return {
				query: "role_control.role_control.api.button_discovery.search_button_groups",
				params: {
					reference_doctype: row.reference_doctype,
					view: row.view || "Form",
					button_label: row.button_label || "",
				},
			};
		});
	},

	trigger_autocomplete_load(frm, cdn, fieldname) {
		const grid = frm.fields_dict.buttons?.grid;
		if (!grid) {
			return;
		}

		const grid_row = grid.grid_rows_by_docname?.[cdn];
		const field = grid_row?.grid_form?.fields_dict?.[fieldname];
		if (field?.$input) {
			field.$input.trigger("focus");
			field.$input.trigger("input");
		}
	},

	refresh_open_row_autocomplete(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row?.reference_doctype) {
			return;
		}

		if (BUTTON_LABEL_CATEGORIES.includes(row.button_category)) {
			setTimeout(() => this.trigger_autocomplete_load(frm, cdn, "button_label"), 200);
		}
		if (row.button_category === "Custom") {
			setTimeout(() => this.trigger_autocomplete_load(frm, cdn, "button_group"), 250);
		}
	},
};

frappe.ui.form.on("Form Button Control", {
	setup(frm) {
		role_control.form_button_control_config.setup_queries(frm);
	},

	refresh(frm) {
		role_control.form_button_control_config.setup_queries(frm);
	},
});

frappe.ui.form.on("Form Button Control Detail", {
	form_render(frm, cdt, cdn) {
		role_control.form_button_control_config.refresh_open_row_autocomplete(frm, cdt, cdn);
	},

	reference_doctype(frm, cdt, cdn) {
		role_control.form_button_control_config.refresh_open_row_autocomplete(frm, cdt, cdn);
	},

	button_category(frm, cdt, cdn) {
		role_control.form_button_control_config.refresh_open_row_autocomplete(frm, cdt, cdn);
	},

	view(frm, cdt, cdn) {
		role_control.form_button_control_config.refresh_open_row_autocomplete(frm, cdt, cdn);
	},

	button_label(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (row.button_category === "Custom" && row.reference_doctype) {
			setTimeout(
				() => role_control.form_button_control_config.trigger_autocomplete_load(frm, cdn, "button_group"),
				100
			);
		}
	},
});
