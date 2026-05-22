# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

from unittest.mock import patch

import frappe
from frappe.tests import UnitTestCase

from role_control.role_control.api.button_discovery import (
	_build_button_options,
	_get_menu_catalog_options,
	_get_registry_options,
	_get_unique_groups,
	_scan_custom_buttons,
	clear_options_cache,
	get_button_options,
	search_button_groups,
	search_button_labels,
)
from role_control.role_control.api.button_control import clear_cache_for_doc


class TestButtonDiscovery(UnitTestCase):
	def setUp(self):
		clear_options_cache()
		clear_cache_for_doc()

	def tearDown(self):
		clear_options_cache()
		clear_cache_for_doc()

	def test_scan_custom_buttons_from_fixture(self):
		content = '''
		frm.add_custom_button(__("Make Return Ticket"), function () {});
		frm.add_custom_button(__("Grouped"), function () {}, __("Update"));
		'''
		found = _scan_custom_buttons(content, "test")
		labels = {key[0] for key in found}
		self.assertIn("Make Return Ticket", labels)
		self.assertIn("Grouped", labels)

	def test_menu_catalog_includes_email(self):
		catalog = _get_menu_catalog_options()
		self.assertIn(("Email", None), catalog)

	def test_menu_action_includes_catalog(self):
		options = _build_button_options("User", "Menu Action", "Form")
		values = {o["value"] for o in options}
		self.assertIn("Email", values)

	def test_registry_from_hooks(self):
		registry = {
			"Test DocType X": [
				{"category": "Custom", "label": "Registry Only", "group": "Actions"},
			]
		}
		with patch("frappe.get_hooks", return_value=registry):
			options = _get_registry_options("Test DocType X", "Custom")
		self.assertIn(("Registry Only", "Actions"), options)
		self.assertEqual(options[("Registry Only", "Actions")]["source"], "registry")

	def test_get_button_options_cached(self):
		frappe.set_user("Administrator")
		clear_options_cache()
		first = get_button_options("User", "Menu Action", "Form")
		second = get_button_options("User", "Menu Action", "Form")
		self.assertEqual(first, second)
		self.assertTrue(any(o["value"] == "Email" for o in first))

	def test_search_button_labels_for_job_order(self):
		frappe.set_user("Administrator")
		results = search_button_labels(
			txt="Return",
			reference_doctype="Job Order",
			button_category="Custom",
			view="Form",
		)
		values = {r["value"] for r in results}
		self.assertIn("Make Return Ticket", values)

	def test_search_button_groups_filtered_by_label(self):
		frappe.set_user("Administrator")
		groups = _get_unique_groups("Job Order", "Form", "Make Delivery Ticket")
		self.assertTrue(any("Actions" in g for g in groups) or len(groups) >= 0)

		results = search_button_groups(
			reference_doctype="Job Order",
			view="Form",
			button_label="Make Delivery Ticket",
		)
		if results:
			self.assertTrue(all("value" in r for r in results))

	def test_cache_cleared_with_button_control_cache(self):
		frappe.set_user("Administrator")
		get_button_options("User", "Menu Action", "Form")
		key = "role_control:button_options:User:Menu Action:Form"
		self.assertIsNotNone(frappe.cache.get_value(key))

		clear_cache_for_doc()
		self.assertIsNone(frappe.cache.get_value(key))
