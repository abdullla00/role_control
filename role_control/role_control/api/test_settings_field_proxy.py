# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

from __future__ import annotations

from frappe.tests.utils import FrappeTestCase

from role_control.role_control.api import settings_field_proxy as proxy


class TestSettingsFieldProxy(FrappeTestCase):
	def test_safe_stock_settings_fields_are_allowlisted(self):
		allowed = proxy.SAFE_SINGLE_FIELDS["Stock Settings"]
		self.assertIn("sample_retention_warehouse", allowed)
		self.assertIn("disable_serial_no_and_batch_selector", allowed)
		self.assertNotIn("valuation_method", allowed)
		self.assertNotIn("default_warehouse", allowed)

	def test_should_proxy_requires_operational_access_without_settings_perm(self):
		# Administrator has Stock Settings read — must not use proxy path.
		self.assertFalse(
			proxy._should_proxy("Stock Settings", ["disable_serial_no_and_batch_selector"])
		)

	def test_normalize_fields(self):
		self.assertEqual(proxy._normalize_fields("a"), ["a"])
		self.assertEqual(proxy._normalize_fields(["a", "b"]), ["a", "b"])
		self.assertEqual(proxy._normalize_fields('["a","b"]'), ["a", "b"])
