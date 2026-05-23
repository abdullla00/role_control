# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import UnitTestCase

from role_control.role_control.api.button_control import (
	_get_cached_rules,
	_merge_rules,
	clear_cache_for_doc,
	apply_on_docstatus_matches,
	get_applicable_rules,
)


class TestFormButtonControl(UnitTestCase):
	TEST_USER = "role_control_tester@example.com"

	def setUp(self):
		clear_cache_for_doc()
		frappe.cache.delete_keys("role_control:button_rules")
		self._ensure_test_user()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Form Button Control", {"description": ["like", "role_control_test_%"]})
		clear_cache_for_doc()

	def _ensure_test_user(self):
		if frappe.db.exists("User", self.TEST_USER):
			return

		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": self.TEST_USER,
				"first_name": "Role Control",
				"last_name": "Tester",
				"send_welcome_email": 0,
				"roles": [{"role": "Employee"}],
			}
		)
		user.insert(ignore_permissions=True)

	def _as_test_user(self):
		frappe.set_user(self.TEST_USER)
		clear_cache_for_doc()

	def _make_control(self, **kwargs):
		doc = frappe.get_doc(
			{
				"doctype": "Form Button Control",
				"naming_series": "FBC-.#####",
				"enabled": kwargs.pop("enabled", 1),
				"priority": kwargs.pop("priority", 0),
				"role": kwargs.pop("role", None),
				"user": kwargs.pop("user", None),
				"company": kwargs.pop("company", None),
				"description": kwargs.pop("description", "role_control_test_default"),
				"buttons": kwargs.pop(
					"buttons",
					[
						{
							"reference_doctype": "User",
							"view": "Form",
							"button_category": "Custom",
							"button_label": "Test Button",
							"apply_on_docstatus": "All",
							"hide": 1,
						}
					],
				),
			}
		)
		doc.update(kwargs)
		doc.insert(ignore_permissions=True)
		return doc

	def test_validate_requires_role_or_user(self):
		doc = frappe.get_doc(
			{
				"doctype": "Form Button Control",
				"naming_series": "FBC-.#####",
				"buttons": [
					{
						"reference_doctype": "User",
						"view": "Form",
						"button_category": "Custom",
						"button_label": "X",
					}
				],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_validate_requires_buttons_when_enabled(self):
		doc = frappe.get_doc(
			{
				"doctype": "Form Button Control",
				"naming_series": "FBC-.#####",
				"enabled": 1,
				"role": "Employee",
				"buttons": [],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_validate_duplicate_child_rows(self):
		buttons = [
			{
				"reference_doctype": "User",
				"view": "Form",
				"button_category": "Custom",
				"button_label": "Duplicate",
				"apply_on_docstatus": "All",
			},
			{
				"reference_doctype": "User",
				"view": "Form",
				"button_category": "Custom",
				"button_label": "Duplicate",
				"apply_on_docstatus": "All",
			},
		]
		doc = frappe.get_doc(
			{
				"doctype": "Form Button Control",
				"naming_series": "FBC-.#####",
				"role": "Employee",
				"description": "role_control_test_duplicate",
				"buttons": buttons,
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_user_rule_overrides_role_rule(self):
		if not frappe.db.exists("Role", "Employee"):
			return

		self._as_test_user()

		self._make_control(
			role="Employee",
			priority=0,
			description="role_control_test_role",
			buttons=[
				{
					"reference_doctype": "User",
					"view": "Form",
					"button_category": "Custom",
					"button_label": "Shared Button",
					"apply_on_docstatus": "All",
					"hide": 1,
				}
			],
		)
		self._make_control(
			user=self.TEST_USER,
			priority=10,
			description="role_control_test_user",
			buttons=[
				{
					"reference_doctype": "User",
					"view": "Form",
					"button_category": "Custom",
					"button_label": "Shared Button",
					"apply_on_docstatus": "All",
					"hide": 1,
				}
			],
		)

		rules = get_applicable_rules("User", view="Form")
		self.assertEqual(len(rules), 1)
		self.assertEqual(rules[0]["parent_user"], self.TEST_USER)

	def test_view_both_matches_form_and_list(self):
		self._as_test_user()

		self._make_control(
			role="All",
			description="role_control_test_both",
			buttons=[
				{
					"reference_doctype": "User",
					"view": "Both",
					"button_category": "Menu Action",
					"button_label": "Email",
					"apply_on_docstatus": "All",
					"hide": 1,
				}
			],
		)

		form_rules = get_applicable_rules("User", view="Form")
		list_rules = get_applicable_rules("User", view="List")
		self.assertEqual(len(form_rules), 1)
		self.assertEqual(len(list_rules), 1)

	def test_disabled_parent_excluded(self):
		doc = self._make_control(
			role="All",
			description="role_control_test_disabled",
			enabled=0,
		)
		rules = get_applicable_rules("User", view="Form")
		self.assertEqual(rules, [])

	def test_company_filter(self):
		self._as_test_user()
		company = frappe.defaults.get_user_default("Company", user=self.TEST_USER)
		if not company:
			return

		self._make_control(
			role="All",
			company=company,
			description="role_control_test_company_match",
			buttons=[
				{
					"reference_doctype": "User",
					"view": "Form",
					"button_category": "Custom",
					"button_label": "Company Scoped",
					"hide": 1,
				}
			],
		)

		rules = get_applicable_rules("User", view="Form", company=company)
		labels = {r.get("button_label") for r in rules}
		self.assertIn("Company Scoped", labels)

		rules_other = get_applicable_rules("User", view="Form", company="__nonexistent_company__")
		other_labels = {r.get("button_label") for r in rules_other}
		self.assertNotIn("Company Scoped", other_labels)

	def test_cache_invalidated_on_save(self):
		self._as_test_user()
		doc = self._make_control(role="All", description="role_control_test_cache")
		company = frappe.defaults.get_user_default("Company", user=self.TEST_USER) or ""
		_get_cached_rules(self.TEST_USER, company)
		key = f"role_control:button_rules:{self.TEST_USER}:{company}"
		self.assertIsNotNone(frappe.cache.get_value(key))

		doc.save(ignore_permissions=True)
		self.assertIsNone(frappe.cache.get_value(key))

	def test_apply_on_docstatus_matches_helper(self):
		self.assertTrue(apply_on_docstatus_matches("All", 0))
		self.assertTrue(apply_on_docstatus_matches("Draft", 0))
		self.assertFalse(apply_on_docstatus_matches("Submitted", 0))

	def test_merge_keeps_distinct_custom_labels_with_shared_standard_button(self):
		rules = [
			{
				"button_category": "Custom",
				"standard_button": "Save",
				"button_label": "View Invoice",
				"button_group": "Navigate",
				"apply_on_docstatus": "All",
				"view": "Form",
			},
			{
				"button_category": "Custom",
				"standard_button": "Save",
				"button_label": "View Delivery Ticket",
				"button_group": "Navigate",
				"apply_on_docstatus": "All",
				"view": "Form",
			},
			{
				"button_category": "Custom",
				"standard_button": "Save",
				"button_label": "View Return Ticket",
				"button_group": "Navigate",
				"apply_on_docstatus": "All",
				"view": "Form",
			},
		]
		merged = _merge_rules(rules)
		labels = {r["button_label"] for r in merged}
		self.assertEqual(
			labels,
			{"View Invoice", "View Delivery Ticket", "View Return Ticket"},
		)
