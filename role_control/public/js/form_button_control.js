// Copyright (c) 2026, Abdulla & Brusk and contributors
// For license information, please see license.txt

frappe.provide("role_control.form_button_control");

const BYPASS_USERS = ["Administrator"];
const DOCSTATUS_MAP = { Draft: 0, Submitted: 1, Cancelled: 2 };
// Job Order refresh adds many custom buttons synchronously; extra passes catch late additions.
const FORM_APPLY_DELAYS = [0, 300, 800, 1500, 2500, 4000];
const LIST_APPLY_DELAYS = [0, 300];

role_control.form_button_control = {
	_memo: {},
	_form_timeouts: new WeakMap(),

	is_bypass_user() {
		return BYPASS_USERS.includes(frappe.session.user);
	},

	get_company_from_frm(frm) {
		if (frm?.doc?.company) {
			return frm.doc.company;
		}
		return frappe.defaults.get_user_default("Company");
	},

	clear_memo() {
		this._memo = {};
	},

	fetch_rules(doctype, view, company) {
		const key = `${doctype}|${view}|${company || ""}`;
		if (this._memo[key]) {
			return Promise.resolve(this._memo[key]);
		}

		return frappe
			.call({
				method: "role_control.role_control.api.button_control.get_applicable_rules",
				args: { doctype, view, company },
			})
			.then((r) => {
				this._memo[key] = r.message || [];
				return this._memo[key];
			});
	},

	apply_on_docstatus_matches(rule, docstatus) {
		const apply_on = rule.apply_on_docstatus;
		if (!apply_on || apply_on === "All") {
			return true;
		}
		const expected = DOCSTATUS_MAP[apply_on];
		return expected !== undefined && docstatus === expected;
	},

	encoded_label(label) {
		return encodeURIComponent(__(label));
	},

	hide_dropdown_by_label($parent, label) {
		if (!$parent || !$parent.length) {
			return;
		}

		const translated = __(label);
		const encoded = this.encoded_label(label);

		$parent.find("li").each(function () {
			const $li = $(this);
			const menu_text = $li.find(".menu-item-label").text().trim();
			const data_label = $li.find("[data-label]").attr("data-label");

			if (menu_text === translated || data_label === encoded) {
				$li.hide();
			}
		});
	},

	hide_inner_toolbar_button(page, label, group) {
		if (!page) {
			return;
		}

		const translated = __(label);
		const encoded = this.encoded_label(label);

		if (group) {
			const $group = page.get_inner_group_button?.(__(group));
			if ($group?.length) {
				$group.find(`.dropdown-item[data-label="${encoded}"]`).closest("li").hide();
			}
		} else if (page.inner_toolbar) {
			page.inner_toolbar.find(`button[data-label="${encoded}"]`).hide();
		}
	},

	hide_standard_form_button(frm, standard_button) {
		const label = __(standard_button);
		const primary_text = frm.page.btn_primary?.text?.().trim();
		const secondary_text = frm.page.btn_secondary?.text?.().trim();

		if (primary_text === label) {
			frm.page.btn_primary.addClass("hide");
		}
		if (secondary_text === label) {
			frm.page.btn_secondary.addClass("hide");
		}
	},

	hide_standard_list_button(listview, standard_button) {
		const page = listview.page;
		if (!page) {
			return;
		}

		if (standard_button === "Add" && page.btn_primary) {
			page.btn_primary.addClass("hide");
			return;
		}

		if (standard_button === "Refresh") {
			if (listview.refresh_button) {
				listview.refresh_button.hide();
			}
			page.wrapper.find('[title="' + __("Reload List") + '"]').hide();
			return;
		}

		if (page.actions) {
			this.hide_dropdown_by_label(page.actions, standard_button);
		}
		if (page.menu) {
			this.hide_dropdown_by_label(page.menu, standard_button);
		}
	},

	apply_rule_form(frm, rule) {
		if (!this.apply_on_docstatus_matches(rule, frm.doc.docstatus)) {
			return;
		}

		const category = rule.button_category;

		if (category === "Standard" && rule.standard_button) {
			this.hide_standard_form_button(frm, rule.standard_button);
			return;
		}

		if (category === "Custom" && rule.button_label) {
			frm.remove_custom_button?.(__(rule.button_label), rule.button_group || null);
			this.hide_inner_toolbar_button(frm.page, rule.button_label, rule.button_group);
			return;
		}

		if (category === "Workflow" && rule.button_label) {
			this.hide_dropdown_by_label(frm.page.actions, rule.button_label);
			return;
		}

		if (category === "Menu Action" && rule.button_label) {
			this.hide_dropdown_by_label(frm.page.menu, rule.button_label);
		}
	},

	apply_rule_list(listview, rule) {
		const category = rule.button_category;

		if (category === "Standard" && rule.standard_button) {
			this.hide_standard_list_button(listview, rule.standard_button);
			return;
		}

		if (category === "Custom" && rule.button_label && listview.page?.actions) {
			this.hide_dropdown_by_label(listview.page.actions, rule.button_label);
			return;
		}

		if (category === "Workflow" && rule.button_label) {
			this.hide_dropdown_by_label(listview.page.actions, rule.button_label);
			return;
		}

		if (category === "Menu Action" && rule.button_label) {
			this.hide_dropdown_by_label(listview.page.menu, rule.button_label);
		}
	},

	apply_form(frm) {
		if (!frm || !frm.doctype || this.is_bypass_user()) {
			return;
		}

		const company = this.get_company_from_frm(frm);

		this.fetch_rules(frm.doctype, "Form", company).then((rules) => {
			rules.forEach((rule) => this.apply_rule_form(frm, rule));
		});
	},

	apply_list(listview) {
		if (!listview?.doctype || this.is_bypass_user()) {
			return;
		}

		const company = frappe.defaults.get_user_default("Company");

		this.fetch_rules(listview.doctype, "List", company).then((rules) => {
			rules.forEach((rule) => this.apply_rule_list(listview, rule));
		});
	},

	schedule_form_apply(frm) {
		let timeouts = this._form_timeouts.get(frm);
		if (!timeouts) {
			timeouts = {};
			this._form_timeouts.set(frm, timeouts);
		}

		FORM_APPLY_DELAYS.forEach((delay) => {
			if (timeouts[delay]) {
				clearTimeout(timeouts[delay]);
			}
			timeouts[delay] = setTimeout(() => this.apply_form(frm), delay);
		});
	},

	schedule_list_apply(listview) {
		LIST_APPLY_DELAYS.forEach((delay) => {
			setTimeout(() => this.apply_list(listview), delay);
		});
	},
};

$(document).on("form-refresh", function (e, frm) {
	role_control.form_button_control.schedule_form_apply(frm);
});

if (frappe.views?.ListView?.prototype?.setup_page_head) {
	const original_setup_page_head = frappe.views.ListView.prototype.setup_page_head;

	frappe.views.ListView.prototype.setup_page_head = function () {
		original_setup_page_head.apply(this, arguments);
		role_control.form_button_control.schedule_list_apply(this);
	};
}
