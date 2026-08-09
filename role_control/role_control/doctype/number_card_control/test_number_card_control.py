# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

import frappe
from frappe.tests import UnitTestCase

from role_control.role_control.api import number_card_control as ncc


class TestNumberCardControl(UnitTestCase):
	TEST_USER = "ncc_tester@example.com"
	TEST_ROLE = "NCC Test Role"

	def setUp(self):
		frappe.set_user("Administrator")
		# Avoid seed catch-up mutating NCC-CHIEF-MANAGER-SENSITIVE during tests
		frappe.conf.role_control_auto_seed_sensitive_number_cards = 0
		ncc.clear_all_number_card_caches()
		frappe.db.delete("Number Card Control", {"description": ["like", "ncc_test_%"]})
		self._ensure_test_role()
		self._ensure_test_user()
		self.card_name = self._ensure_count_card()
		frappe.db.commit()
		ncc.clear_all_number_card_caches()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.delete("Number Card Control", {"description": ["like", "ncc_test_%"]})
		ncc.clear_all_number_card_caches()
		frappe.conf.role_control_auto_seed_sensitive_number_cards = 1

	def _ensure_test_role(self):
		if not frappe.db.exists("Role", self.TEST_ROLE):
			frappe.get_doc(
				{"doctype": "Role", "role_name": self.TEST_ROLE, "desk_access": 1}
			).insert(ignore_permissions=True)

	def _ensure_test_user(self):
		if not frappe.db.exists("User", self.TEST_USER):
			user = frappe.get_doc(
				{
					"doctype": "User",
					"email": self.TEST_USER,
					"first_name": "NCC",
					"last_name": "Tester",
					"send_welcome_email": 0,
					"roles": [{"role": self.TEST_ROLE}],
				}
			)
			user.insert(ignore_permissions=True)
		else:
			user = frappe.get_doc("User", self.TEST_USER)
			if self.TEST_ROLE not in {r.role for r in user.roles}:
				user.append("roles", {"role": self.TEST_ROLE})
				user.save(ignore_permissions=True)
		frappe.db.commit()

	def _ensure_count_card(self) -> str:
		# Prefer a known ERPNext card so link validation is stable
		if frappe.db.exists("Number Card", "Manufactured Items Value"):
			return "Manufactured Items Value"

		name = "NCC Test Count Card"
		if not frappe.db.exists("Number Card", name):
			frappe.get_doc(
				{
					"doctype": "Number Card",
					"label": name,
					"type": "Document Type",
					"document_type": "ToDo",
					"function": "Count",
					"is_public": 1,
					"show_percentage_stats": 0,
				}
			).insert(ignore_permissions=True)
		return name

	def _make_control(self, **kwargs):
		cards = kwargs.pop(
			"cards",
			[{"number_card": self.card_name, "hide": 1}],
		)
		doc = frappe.get_doc(
			{
				"doctype": "Number Card Control",
				"naming_series": "NCC-.#####",
				"enabled": kwargs.pop("enabled", 1),
				"priority": kwargs.pop("priority", 0),
				"role": kwargs.pop("role", None),
				"user": kwargs.pop("user", None),
				"company": kwargs.pop("company", ""),
				"description": kwargs.pop("description", "ncc_test_default"),
				"cards": cards,
			}
		)
		doc.update(kwargs)
		if doc.company is None:
			doc.company = ""
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
		ncc.clear_all_number_card_caches()
		return doc

	def test_validate_requires_role_or_user(self):
		doc = frappe.get_doc(
			{
				"doctype": "Number Card Control",
				"naming_series": "NCC-.#####",
				"cards": [{"number_card": self.card_name, "hide": 1}],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	def test_denylist_hides_card_for_role(self):
		self._make_control(role=self.TEST_ROLE, description="ncc_test_role_hide")
		card = frappe.get_doc("Number Card", self.card_name)
		frappe.set_user(self.TEST_USER)
		ncc.clear_all_number_card_caches()
		self.assertTrue(ncc.is_number_card_hidden(self.card_name))
		self.assertFalse(
			ncc.has_number_card_permission(card, ptype="read", user=self.TEST_USER)
		)

	def test_administrator_bypass(self):
		self._make_control(role=self.TEST_ROLE, description="ncc_test_admin_bypass")
		card = frappe.get_doc("Number Card", self.card_name)
		frappe.set_user("Administrator")
		self.assertFalse(ncc.is_number_card_hidden(self.card_name))
		self.assertTrue(
			ncc.has_number_card_permission(card, ptype="read", user="Administrator")
		)

	def test_get_result_throws_clean_permission_error(self):
		self._make_control(role=self.TEST_ROLE, description="ncc_test_get_result")
		card = frappe.get_doc("Number Card", self.card_name)
		frappe.set_user(self.TEST_USER)
		ncc.clear_all_number_card_caches()
		with self.assertRaises(frappe.PermissionError) as ctx:
			ncc.get_result(card.as_dict(), [])
		self.assertNotIn("total_incoming_value", str(ctx.exception))
		self.assertIn("Not permitted", str(ctx.exception))

	def test_get_percentage_difference_blocked(self):
		self._make_control(role=self.TEST_ROLE, description="ncc_test_pct")
		card = frappe.get_doc("Number Card", self.card_name)
		frappe.set_user(self.TEST_USER)
		ncc.clear_all_number_card_caches()
		with self.assertRaises(frappe.PermissionError):
			ncc.get_percentage_difference(card.as_dict(), [], 1)

	def test_user_rule_hides_card(self):
		self._make_control(user=self.TEST_USER, priority=10, description="ncc_test_user")
		frappe.set_user(self.TEST_USER)
		ncc.clear_all_number_card_caches()
		self.assertTrue(ncc.is_number_card_hidden(self.card_name))

	def test_permission_query_excludes_hidden(self):
		self._make_control(role=self.TEST_ROLE, description="ncc_test_query")
		frappe.set_user(self.TEST_USER)
		ncc.clear_all_number_card_caches()
		condition = ncc.get_permission_query_conditions(user=self.TEST_USER)
		self.assertIn(self.card_name, condition)
		self.assertIn("not in", condition)

	def test_field_aware_toggle(self):
		original = frappe.conf.get("role_control_field_aware_number_cards")
		try:
			frappe.conf.role_control_field_aware_number_cards = 0
			self.assertFalse(ncc.field_aware_enabled())
			frappe.conf.role_control_field_aware_number_cards = 1
			self.assertTrue(ncc.field_aware_enabled())
		finally:
			if original is None:
				frappe.conf.pop("role_control_field_aware_number_cards", None)
			else:
				frappe.conf.role_control_field_aware_number_cards = original

	def test_sensitive_discovery_includes_fallback(self):
		sensitive = ncc.get_sensitive_number_cards()
		if frappe.db.exists("Number Card", "Manufactured Items Value"):
			self.assertIn("Manufactured Items Value", sensitive)

	def test_append_once_ignored_cards(self):
		second = None
		for candidate in ("Total Stock Value", "Open Work Orders", "Total Warehouses"):
			if candidate != self.card_name and frappe.db.exists("Number Card", candidate):
				second = candidate
				break
		if not second:
			self.skipTest("Need a second Number Card for append-once test")

		if not frappe.db.exists("Role", ncc.SEED_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": ncc.SEED_ROLE}).insert(
				ignore_permissions=True
			)

		doc = frappe.get_doc(
			{
				"doctype": "Number Card Control",
				"naming_series": "NCC-.#####",
				"enabled": 1,
				"priority": 10,
				"is_system_seed": 1,
				"role": ncc.SEED_ROLE,
				"description": "ncc_test_append_once",
				"cards": [
					{"number_card": self.card_name, "hide": 1},
					{"number_card": second, "hide": 1},
				],
			}
		)
		doc.insert(ignore_permissions=True)
		frappe.db.commit()

		doc = frappe.get_doc("Number Card Control", doc.name)
		doc.cards = [row for row in doc.cards if row.number_card != second]
		doc.save(ignore_permissions=True)
		frappe.db.commit()
		doc.reload()
		ignored = {row.number_card for row in doc.ignored_cards}
		self.assertIn(second, ignored)

		existing = {row.number_card for row in doc.cards}
		to_add = {second} - existing - ignored
		self.assertEqual(to_add, set())

	def test_should_block_combines_layers(self):
		self._make_control(role=self.TEST_ROLE, description="ncc_test_block")
		frappe.set_user(self.TEST_USER)
		ncc.clear_all_number_card_caches()
		self.assertTrue(ncc.should_block_number_card(self.card_name))

	def test_field_aware_blocks_inaccessible_aggregate(self):
		frappe.conf.role_control_field_aware_number_cards = 1
		# Simulate an inaccessible Sum card via helper with a fake card dict
		fake = frappe._dict(
			{
				"name": "Fake Sensitive Card",
				"type": "Document Type",
				"function": "Sum",
				"document_type": "Stock Entry",
				"aggregate_function_based_on": "total_incoming_value",
			}
		)
		# Employee typically lacks elevated permlevels on Stock Entry valuation fields
		# even when meta permlevel is 0, mask check may not apply — force via monkeypatch
		original = ncc._card_aggregate_inaccessible
		try:
			ncc._card_aggregate_inaccessible = lambda card, user: True
			frappe.set_user(self.TEST_USER)
			ncc.clear_inaccessible_cache()
			self.assertTrue(ncc.is_number_card_inaccessible(fake, user=self.TEST_USER))
			self.assertTrue(ncc.should_block_number_card(fake, user=self.TEST_USER))
		finally:
			ncc._card_aggregate_inaccessible = original
			frappe.set_user("Administrator")
