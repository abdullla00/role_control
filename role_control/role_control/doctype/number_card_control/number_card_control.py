# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from role_control.role_control.api.number_card_control import clear_rules_cache, sync_ignored_cards_from_removal


class NumberCardControl(Document):
	def validate(self):
		if not self.role and not self.user:
			frappe.throw(_("Either Role or User is required."))

		if self.enabled and not self.cards and not (self.is_system_seed and self.ignored_cards):
			frappe.throw(_("At least one card rule is required when Enabled is checked."))

		if self.is_system_seed:
			self.company = None

		self._validate_duplicate_card_rows()
		self._validate_duplicate_ignored_rows()

	def _validate_duplicate_card_rows(self):
		seen = set()
		for row in self.cards or []:
			if not row.number_card:
				continue
			if row.number_card in seen:
				frappe.throw(
					_("Duplicate number card {0} in row {1}.").format(row.number_card, row.idx)
				)
			seen.add(row.number_card)

	def _validate_duplicate_ignored_rows(self):
		seen = set()
		for row in self.ignored_cards or []:
			if not row.number_card:
				continue
			if row.number_card in seen:
				frappe.throw(
					_("Duplicate ignored number card {0} in row {1}.").format(
						row.number_card, row.idx
					)
				)
			seen.add(row.number_card)

	def before_save(self):
		if self.is_system_seed and not self.is_new():
			sync_ignored_cards_from_removal(self)

	def on_update(self):
		clear_rules_cache()

	def on_trash(self):
		clear_rules_cache()
