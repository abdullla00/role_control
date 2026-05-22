# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from role_control.role_control.api.button_control import clear_cache_for_doc


class FormButtonControl(Document):
	def validate(self):
		if not self.role and not self.user:
			frappe.throw(_("Either Role or User is required."))

		if self.enabled and not self.buttons:
			frappe.throw(_("At least one button rule is required when Enabled is checked."))

		self._validate_duplicate_button_rows()

	def _validate_duplicate_button_rows(self):
		seen = set()
		for row in self.buttons:
			key = self._row_key(row)
			if key in seen:
				frappe.throw(
					_("Duplicate button rule for {0} in row {1}.").format(
						row.reference_doctype, row.idx
					)
				)
			seen.add(key)

	@staticmethod
	def _row_key(row):
		button_id = row.standard_button if row.button_category == "Standard" else row.button_label
		return (
			row.reference_doctype,
			row.view,
			row.button_category,
			button_id or "",
			row.button_group or "",
			row.apply_on_docstatus,
		)

	def on_update(self):
		clear_cache_for_doc(self)

	def on_trash(self):
		clear_cache_for_doc(self)
