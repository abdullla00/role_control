# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

from __future__ import annotations

import frappe

# Only the Administrator user bypasses rules (so admins can always configure/test).
# Rules targeting the "System Manager" role still apply to System Manager users.
BYPASS_USERS = frozenset({"Administrator"})
CACHE_KEY_PREFIX = "role_control:button_rules"
CACHE_TTL = 300

DOCSTATUS_MAP = {
	"Draft": 0,
	"Submitted": 1,
	"Cancelled": 2,
}


def _cache_key(user: str, company: str | None) -> str:
	return f"{CACHE_KEY_PREFIX}:{user}:{company or ''}"


def _is_bypass_user(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user in BYPASS_USERS


def _get_effective_company(company: str | None = None) -> str | None:
	if company:
		return company
	return frappe.defaults.get_user_default("Company")


def _view_matches(row_view: str, requested_view: str) -> bool:
	if row_view == "Both":
		return True
	return row_view == requested_view


def _rule_key(rule: dict) -> str:
	button_id = rule.get("standard_button") or rule.get("button_label") or ""
	return ":".join(
		[
			rule.get("button_category") or "",
			button_id,
			rule.get("button_group") or "",
			rule.get("apply_on_docstatus") or "All",
			rule.get("view") or "",
		]
	)


def _merge_rules(rules: list[dict]) -> list[dict]:
	"""Lower priority first; user-specific rules overwrite later."""
	sorted_rules = sorted(
		rules,
		key=lambda r: (
			r.get("priority") or 0,
			0 if r.get("parent_user") else 1,
		),
	)
	merged: dict[str, dict] = {}
	for rule in sorted_rules:
		merged[_rule_key(rule)] = rule
	return list(merged.values())


def _load_rules_for_user(user: str, company: str | None) -> list[dict]:
	roles = frappe.get_roles(user)
	company_filter = company or ""

	if roles:
		rules = frappe.db.sql(
			"""
			SELECT
				fbc.name AS parent,
				fbc.priority,
				fbc.user AS parent_user,
				fbc.role AS parent_role,
				fbc.company AS parent_company,
				fbcd.reference_doctype,
				fbcd.view,
				fbcd.button_category,
				fbcd.standard_button,
				fbcd.button_label,
				fbcd.button_group,
				fbcd.apply_on_docstatus,
				fbcd.hide
			FROM `tabForm Button Control` fbc
			INNER JOIN `tabForm Button Control Detail` fbcd ON fbcd.parent = fbc.name
			WHERE fbc.enabled = 1
				AND (fbc.user = %s OR fbc.role IN %s)
				AND (IFNULL(fbc.company, '') = '' OR fbc.company = %s)
			""",
			(user, tuple(roles), company_filter),
			as_dict=True,
		)
	else:
		rules = frappe.db.sql(
			"""
			SELECT
				fbc.name AS parent,
				fbc.priority,
				fbc.user AS parent_user,
				fbc.role AS parent_role,
				fbc.company AS parent_company,
				fbcd.reference_doctype,
				fbcd.view,
				fbcd.button_category,
				fbcd.standard_button,
				fbcd.button_label,
				fbcd.button_group,
				fbcd.apply_on_docstatus,
				fbcd.hide
			FROM `tabForm Button Control` fbc
			INNER JOIN `tabForm Button Control Detail` fbcd ON fbcd.parent = fbc.name
			WHERE fbc.enabled = 1
				AND fbc.user = %s
				AND (IFNULL(fbc.company, '') = '' OR fbc.company = %s)
			""",
			(user, company_filter),
			as_dict=True,
		)

	return rules


def _get_cached_rules(user: str, company: str | None) -> list[dict]:
	key = _cache_key(user, company)
	rules = frappe.cache.get_value(key)
	if rules is None:
		rules = _load_rules_for_user(user, company)
		frappe.cache.set_value(key, rules, expires_in_sec=CACHE_TTL)
	return rules


def clear_cache_for_doc(doc=None):
	frappe.cache.delete_keys(CACHE_KEY_PREFIX)
	from role_control.role_control.api.button_discovery import clear_options_cache

	clear_options_cache()


def clear_cache_on_doc_event(doc, method=None):
	clear_cache_for_doc(doc)


@frappe.whitelist()
def get_applicable_rules(doctype: str, view: str = "Form", company: str | None = None):
	if _is_bypass_user():
		return []

	effective_company = _get_effective_company(company)
	user = frappe.session.user
	all_rules = _get_cached_rules(user, effective_company)

	filtered = [
		rule
		for rule in all_rules
		if rule.reference_doctype == doctype
		and _view_matches(rule.view, view)
		and rule.hide
	]

	return _merge_rules(filtered)


def apply_on_docstatus_matches(rule_docstatus: str, doc_docstatus: int | None) -> bool:
	if not rule_docstatus or rule_docstatus == "All":
		return True
	expected = DOCSTATUS_MAP.get(rule_docstatus)
	return expected is not None and doc_docstatus == expected
