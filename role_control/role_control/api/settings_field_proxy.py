# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

"""Allowlist proxy for Singles fields used by operational forms.

Stock Entry (and related stock controllers) call ``frappe.client.get_value`` /
``get_single_value`` on **Stock Settings** during form setup. Those RPC methods
require DocType read permission, but Chief Manager must not open Stock Settings
or read valuation/config fields.

This override returns only explicitly allowlisted operational fields when the
user lacks Stock Settings permission but can read an operational stock DocType.
All other Stock Settings access still raises PermissionError.
"""

from __future__ import annotations

from typing import Any

import frappe
from frappe.client import get_single_value as _original_get_single_value
from frappe.client import get_value as _original_get_value
from frappe.utils import cint

# Operational UI flags / warehouse links used by Stock Entry + TransactionController.
# Do not add valuation, price-list, freeze, or accounting fields here.
SAFE_SINGLE_FIELDS: dict[str, frozenset[str]] = {
	"Stock Settings": frozenset(
		{
			"sample_retention_warehouse",
			"disable_serial_no_and_batch_selector",
			"use_serial_batch_fields",
			"show_barcode_field",
			"auto_create_serial_and_batch_bundle_for_outward",
			"allow_to_edit_stock_uom_qty_for_stock_entry",
			"allow_to_edit_stock_uom_qty_for_sales",
			"allow_to_edit_stock_uom_qty_for_purchase",
		}
	),
}

# Caller must already be able to use one of these DocTypes.
OPERATIONAL_STOCK_DOCTYPES = (
	"Stock Entry",
	"Work Order",
	"Material Request",
	"Purchase Receipt",
	"Delivery Note",
	"Stock Reconciliation",
)


def proxy_enabled() -> bool:
	return cint(frappe.conf.get("role_control_settings_field_proxy", 1)) == 1


def _normalize_fields(fieldname: Any) -> list[str]:
	try:
		fields = frappe.parse_json(fieldname)
	except (TypeError, ValueError):
		fields = fieldname

	if isinstance(fields, str):
		return [fields]
	if isinstance(fields, (list, tuple)):
		return [str(f) for f in fields]
	return [str(fieldname)]


def _has_operational_stock_access() -> bool:
	return any(frappe.has_permission(dt, "read") for dt in OPERATIONAL_STOCK_DOCTYPES)


def _should_proxy(doctype: str, fields: list[str]) -> bool:
	if not proxy_enabled():
		return False
	allowed = SAFE_SINGLE_FIELDS.get(doctype)
	if not allowed:
		return False
	if not fields or not set(fields).issubset(allowed):
		return False
	# Users who already have DocType access use the normal path.
	if frappe.has_permission(doctype, "read"):
		return False
	return _has_operational_stock_access()


@frappe.whitelist()
def get_single_value(doctype: str, field: str):
	"""Override of ``frappe.client.get_single_value`` with allowlisted Stock Settings fields."""
	fields = _normalize_fields(field)
	if len(fields) == 1 and _should_proxy(doctype, fields):
		return frappe.db.get_single_value(doctype, fields[0])
	return _original_get_single_value(doctype, field)


@frappe.whitelist()
def get_value(
	doctype: str,
	fieldname: Any,
	filters: Any = None,
	as_dict: bool = True,
	debug: bool = False,
	parent: str | None = None,
):
	"""Override of ``frappe.client.get_value`` with allowlisted Stock Settings fields."""
	fields = _normalize_fields(fieldname)
	if frappe.get_meta(doctype).issingle and _should_proxy(doctype, fields):
		value = frappe.db.get_values_from_single(fields, None, doctype, as_dict=as_dict, debug=debug)
		if as_dict:
			return value[0] if value else {}
		if not value:
			return
		return value[0] if len(fields) > 1 else value[0][0]

	return _original_get_value(
		doctype,
		fieldname,
		filters=filters,
		as_dict=as_dict,
		debug=debug,
		parent=parent,
	)
