# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

from __future__ import annotations

import json
from typing import Any

import frappe
from frappe import _
from frappe.utils import cint

# Only the Administrator user bypasses rules (so admins can always configure/test).
# Rules targeting the "System Manager" role still apply to System Manager users.
BYPASS_USERS = frozenset({"Administrator"})
RULES_CACHE_PREFIX = "role_control:number_card_rules"
INACCESSIBLE_CACHE_PREFIX = "role_control:number_card_inaccessible"
CACHE_TTL = 300

SEED_DOC_NAME = "NCC-CHIEF-MANAGER-SENSITIVE"
SEED_ROLE = "Chief Manager"
SENSITIVE_FUNCTIONS = frozenset({"Sum", "Average", "Minimum", "Maximum"})
FALLBACK_SENSITIVE_CARDS = ("Manufactured Items Value", "Total Stock Value")
PREFERRED_FIELDTYPES = frozenset({"Currency", "Float", "Percent", "Int"})


def _cache_key(prefix: str, *parts: str) -> str:
	return ":".join((prefix, *(str(p) for p in parts)))


def _is_bypass_user(user: str | None = None) -> bool:
	user = user or frappe.session.user
	return user in BYPASS_USERS


def _conf_flag(key: str, default: int = 1) -> bool:
	return cint(frappe.conf.get(key, default)) == 1


def field_aware_enabled() -> bool:
	return _conf_flag("role_control_field_aware_number_cards", 1)


def auto_seed_enabled() -> bool:
	return _conf_flag("role_control_auto_seed_sensitive_number_cards", 1)


def _get_effective_company(company: str | None = None) -> str | None:
	if company:
		return company
	return frappe.defaults.get_user_default("Company")


def clear_rules_cache(doc=None, method=None):
	frappe.cache.delete_keys(RULES_CACHE_PREFIX)


def clear_inaccessible_cache(doc=None, method=None):
	frappe.cache.delete_keys(INACCESSIBLE_CACHE_PREFIX)


def clear_all_number_card_caches(doc=None, method=None):
	clear_rules_cache()
	clear_inaccessible_cache()


def clear_caches_on_user_update(doc, method=None):
	"""Invalidate per-user inaccessible/rules caches when roles may have changed."""
	clear_all_number_card_caches()


def _load_rules_for_user(user: str, company: str | None) -> list[dict]:
	roles = frappe.get_roles(user)
	company_filter = company or ""

	if roles:
		rules = frappe.db.sql(
			"""
			SELECT
				ncc.name AS parent,
				ncc.priority,
				ncc.user AS parent_user,
				ncc.role AS parent_role,
				ncc.company AS parent_company,
				nccd.number_card,
				nccd.hide
			FROM `tabNumber Card Control` ncc
			INNER JOIN `tabNumber Card Control Detail` nccd ON nccd.parent = ncc.name
			WHERE ncc.enabled = 1
				AND (ncc.user = %s OR ncc.role IN %s)
				AND (IFNULL(ncc.company, '') = '' OR ncc.company = %s)
				AND nccd.hide = 1
			""",
			(user, tuple(roles), company_filter),
			as_dict=True,
		)
	else:
		rules = frappe.db.sql(
			"""
			SELECT
				ncc.name AS parent,
				ncc.priority,
				ncc.user AS parent_user,
				ncc.role AS parent_role,
				ncc.company AS parent_company,
				nccd.number_card,
				nccd.hide
			FROM `tabNumber Card Control` ncc
			INNER JOIN `tabNumber Card Control Detail` nccd ON nccd.parent = ncc.name
			WHERE ncc.enabled = 1
				AND ncc.user = %s
				AND (IFNULL(ncc.company, '') = '' OR ncc.company = %s)
				AND nccd.hide = 1
			""",
			(user, company_filter),
			as_dict=True,
		)

	return rules


def _merge_hidden_cards(rules: list[dict]) -> set[str]:
	"""Higher priority wins; user-specific overwrites role for the same card."""
	sorted_rules = sorted(
		rules,
		key=lambda r: (
			r.get("priority") or 0,
			0 if r.get("parent_user") else 1,
		),
	)
	merged: dict[str, dict] = {}
	for rule in sorted_rules:
		card = rule.get("number_card")
		if card:
			merged[card] = rule
	return {name for name, rule in merged.items() if rule.get("hide")}


def _get_cached_hidden_cards(user: str, company: str | None) -> set[str]:
	key = _cache_key(RULES_CACHE_PREFIX, user, company or "")
	cached = frappe.cache.get_value(key)
	if cached is not None:
		return set(cached)

	hidden = _merge_hidden_cards(_load_rules_for_user(user, company))
	frappe.cache.set_value(key, list(hidden), expires_in_sec=CACHE_TTL)
	return hidden


def is_number_card_hidden(
	card_name: str, user: str | None = None, company: str | None = None
) -> bool:
	if not card_name:
		return False
	user = user or frappe.session.user
	if _is_bypass_user(user):
		return False
	effective_company = _get_effective_company(company)
	return card_name in _get_cached_hidden_cards(user, effective_company)


def get_hidden_number_cards(user: str | None = None, company: str | None = None) -> set[str]:
	user = user or frappe.session.user
	if _is_bypass_user(user):
		return set()
	return _get_cached_hidden_cards(user, _get_effective_company(company))


def _resolve_card(card_doc_or_name: Any):
	if card_doc_or_name is None:
		return None
	if isinstance(card_doc_or_name, str):
		if not frappe.db.exists("Number Card", card_doc_or_name):
			return None
		return frappe.get_cached_doc("Number Card", card_doc_or_name)
	# Document / _dict / mapping with Number Card fields
	if hasattr(card_doc_or_name, "doctype") and getattr(card_doc_or_name, "doctype", None) == "Number Card":
		return card_doc_or_name
	if isinstance(card_doc_or_name, dict):
		name = card_doc_or_name.get("name")
		if card_doc_or_name.get("type") or card_doc_or_name.get("document_type"):
			return frappe._dict(card_doc_or_name)
		if name and frappe.db.exists("Number Card", name):
			return frappe.get_cached_doc("Number Card", name)
		return frappe._dict(card_doc_or_name)
	if hasattr(card_doc_or_name, "get"):
		name = card_doc_or_name.get("name")
		if card_doc_or_name.get("type") or card_doc_or_name.get("document_type"):
			return card_doc_or_name
		if name and frappe.db.exists("Number Card", name):
			return frappe.get_cached_doc("Number Card", name)
	return card_doc_or_name


def _card_aggregate_inaccessible(card, user: str) -> bool:
	card_type = card.get("type") or "Document Type"
	if card_type != "Document Type":
		return False

	function = card.get("function")
	if function == "Count" or function not in SENSITIVE_FUNCTIONS:
		return False

	document_type = card.get("document_type")
	aggregate_field = card.get("aggregate_function_based_on")
	if not document_type:
		return True
	if not aggregate_field:
		return True

	try:
		meta = frappe.get_meta(document_type)
	except Exception:
		return True

	df = meta.get_field(aggregate_field)
	if not df:
		return True

	parenttype = card.get("parent_document_type") if meta.istable else None
	read_levels = set(
		meta.get_permlevel_access(permission_type="read", parenttype=parenttype, user=user)
	)
	if cint(df.permlevel) not in read_levels:
		return True

	if df.get("mask"):
		mask_levels = set(
			meta.get_permlevel_access(permission_type="mask", parenttype=parenttype, user=user)
		)
		if cint(df.permlevel) not in mask_levels:
			return True

	return False


def is_number_card_inaccessible(card_doc_or_name: Any, user: str | None = None) -> bool:
	if not field_aware_enabled():
		return False
	user = user or frappe.session.user
	if _is_bypass_user(user):
		return False

	card = _resolve_card(card_doc_or_name)
	if not card:
		return False

	card_name = card.get("name")
	if card_name:
		key = _cache_key(INACCESSIBLE_CACHE_PREFIX, user)
		cached = frappe.cache.get_value(key)
		if cached is not None:
			return card_name in set(cached)

	return _card_aggregate_inaccessible(card, user)


def _get_inaccessible_card_names(user: str) -> set[str]:
	if not field_aware_enabled() or _is_bypass_user(user):
		return set()

	key = _cache_key(INACCESSIBLE_CACHE_PREFIX, user)
	cached = frappe.cache.get_value(key)
	if cached is not None:
		return set(cached)

	inaccessible: set[str] = set()
	cards = frappe.get_all(
		"Number Card",
		filters={"type": "Document Type", "function": ["in", list(SENSITIVE_FUNCTIONS)]},
		fields=[
			"name",
			"type",
			"function",
			"document_type",
			"aggregate_function_based_on",
			"parent_document_type",
		],
	)
	for card in cards:
		if _card_aggregate_inaccessible(card, user):
			inaccessible.add(card.name)

	frappe.cache.set_value(key, list(inaccessible), expires_in_sec=CACHE_TTL)
	return inaccessible


def should_block_number_card(
	card_doc_or_name: Any, user: str | None = None, company: str | None = None
) -> bool:
	user = user or frappe.session.user
	if _is_bypass_user(user):
		return False

	card = _resolve_card(card_doc_or_name)
	name = None
	if card:
		name = card.get("name")
	elif isinstance(card_doc_or_name, str):
		name = card_doc_or_name

	if name and is_number_card_hidden(name, user=user, company=company):
		return True
	if card and is_number_card_inaccessible(card, user=user):
		return True
	return False


def has_number_card_permission(doc, ptype=None, user=None, debug=False):
	"""has_permission hook: return False to deny, True to abstain."""
	user = user or frappe.session.user
	if _is_bypass_user(user):
		return True
	if should_block_number_card(doc, user=user):
		return False
	return True


def get_permission_query_conditions(user=None, doctype=None):
	"""AND-composed with core Number Card query conditions."""
	user = user or frappe.session.user
	if _is_bypass_user(user):
		return ""

	blocked = get_hidden_number_cards(user=user) | _get_inaccessible_card_names(user)
	if not blocked:
		return ""

	# Escape names for SQL IN list
	escaped = ", ".join(frappe.db.escape(name) for name in sorted(blocked))
	return f"`tabNumber Card`.name not in ({escaped})"


def _card_name_from_doc_payload(doc) -> str | None:
	if doc is None:
		return None
	if isinstance(doc, str):
		try:
			doc = json.loads(doc)
		except (TypeError, ValueError):
			return doc
	if isinstance(doc, dict):
		return doc.get("name")
	return getattr(doc, "name", None)


def _throw_not_permitted():
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def _guard_card_access(doc):
	user = frappe.session.user
	if _is_bypass_user(user):
		return
	card = _resolve_card(doc if not isinstance(doc, str) else frappe.parse_json(doc))
	if should_block_number_card(card or _card_name_from_doc_payload(doc), user=user):
		_throw_not_permitted()


@frappe.whitelist()
def get_result(doc, filters, to_date=None):
	_guard_card_access(doc)
	from frappe.desk.doctype.number_card.number_card import get_result as original_get_result

	return original_get_result(doc, filters, to_date=to_date)


@frappe.whitelist()
def get_percentage_difference(doc, filters, result):
	_guard_card_access(doc)
	from frappe.desk.doctype.number_card.number_card import (
		get_percentage_difference as original_get_percentage_difference,
	)

	return original_get_percentage_difference(doc, filters, result)


def _field_is_sensitive(df) -> bool:
	if not df:
		return False
	if cint(df.permlevel) > 0 or df.get("mask"):
		# Prefer monetary-ish types, but still flag other types with elev/mask
		if df.fieldtype in PREFERRED_FIELDTYPES or cint(df.permlevel) > 0 or df.get("mask"):
			return True
	return False


def get_sensitive_number_cards() -> list[str]:
	"""Discover Document Type cards that aggregate masked/high-permlevel fields."""
	sensitive: set[str] = set()

	cards = frappe.get_all(
		"Number Card",
		filters={"type": "Document Type", "function": ["in", list(SENSITIVE_FUNCTIONS)]},
		fields=[
			"name",
			"document_type",
			"aggregate_function_based_on",
			"parent_document_type",
		],
	)

	for card in cards:
		document_type = card.document_type
		aggregate_field = card.aggregate_function_based_on
		if not document_type or not aggregate_field:
			continue
		try:
			meta = frappe.get_meta(document_type)
		except Exception:
			continue
		df = meta.get_field(aggregate_field)
		if _field_is_sensitive(df):
			sensitive.add(card.name)

	for name in FALLBACK_SENSITIVE_CARDS:
		if frappe.db.exists("Number Card", name):
			sensitive.add(name)

	return sorted(sensitive)


def sync_ignored_cards_from_removal(doc):
	"""Move removed card names into ignored_cards (append-once). Called from before_save."""
	if not doc.is_system_seed or doc.is_new():
		return

	before = doc.get_doc_before_save()
	if not before:
		return

	before_cards = {row.number_card for row in (before.cards or []) if row.number_card}
	after_cards = {row.number_card for row in (doc.cards or []) if row.number_card}
	ignored = {row.number_card for row in (doc.ignored_cards or []) if row.number_card}

	for removed in before_cards - after_cards:
		if removed and removed not in ignored:
			doc.append("ignored_cards", {"number_card": removed})
			ignored.add(removed)


def _get_or_create_seed_doc():
	"""Return existing system seed doc (canonical name or is_system_seed), or None."""
	if frappe.db.exists("Number Card Control", SEED_DOC_NAME):
		return frappe.get_doc("Number Card Control", SEED_DOC_NAME)

	existing = frappe.db.get_value(
		"Number Card Control",
		{"is_system_seed": 1, "role": SEED_ROLE},
		"name",
	)
	if existing:
		return frappe.get_doc("Number Card Control", existing)
	return None


def ensure_chief_manager_sensitive_seed(card_names: list[str] | None = None) -> str | None:
	"""Create/update the Chief Manager auto-seed document (append-once)."""
	if not auto_seed_enabled():
		return None
	if not frappe.db.exists("Role", SEED_ROLE):
		return None

	names = set(card_names if card_names is not None else get_sensitive_number_cards())
	names = {n for n in names if frappe.db.exists("Number Card", n)}

	doc = _get_or_create_seed_doc()
	if doc:
		doc.db_set("is_system_seed", 1, update_modified=False)
		if not doc.role:
			doc.db_set("role", SEED_ROLE, update_modified=False)
		if not cint(doc.enabled):
			doc.db_set("enabled", 1, update_modified=False)
		if doc.company:
			doc.db_set("company", None, update_modified=False)

		doc.reload()
		existing = {row.number_card for row in (doc.cards or []) if row.number_card}
		ignored = {row.number_card for row in (doc.ignored_cards or []) if row.number_card}
		to_add = sorted(names - existing - ignored)
		if not to_add:
			clear_rules_cache()
			return doc.name

		for card_name in to_add:
			doc.append("cards", {"number_card": card_name, "hide": 1})

		doc.save(ignore_permissions=True)
		clear_rules_cache()
		return doc.name

	if not names:
		return None

	doc = frappe.get_doc(
		{
			"doctype": "Number Card Control",
			"naming_series": "NCC-.#####",
			"enabled": 1,
			"priority": 10,
			"is_system_seed": 1,
			"role": SEED_ROLE,
			"company": "",
			"description": (
				"Auto-seeded: hide cards aggregating masked/high-permlevel fields "
				"for Chief Manager (append-once)."
			),
			"cards": [{"number_card": name, "hide": 1} for name in sorted(names)],
			"ignored_cards": [],
		}
	)
	doc.insert(ignore_permissions=True, set_name=SEED_DOC_NAME)
	clear_rules_cache()
	return doc.name


def _card_doc_is_sensitive(doc) -> bool:
	if doc.get("type") != "Document Type":
		return False
	if doc.get("function") not in SENSITIVE_FUNCTIONS:
		return False
	document_type = doc.get("document_type")
	aggregate_field = doc.get("aggregate_function_based_on")
	if not document_type or not aggregate_field:
		return False
	try:
		meta = frappe.get_meta(document_type)
	except Exception:
		return False
	return _field_is_sensitive(meta.get_field(aggregate_field)) or doc.name in FALLBACK_SENSITIVE_CARDS


def maybe_append_card_to_seed(doc, method=None):
	"""Number Card after_insert/on_update catch-up for sensitive cards."""
	if not auto_seed_enabled():
		return
	if getattr(frappe.flags, "in_install", False):
		return

	try:
		if doc.name in FALLBACK_SENSITIVE_CARDS or _card_doc_is_sensitive(doc):
			ensure_chief_manager_sensitive_seed([doc.name])
	except Exception:
		frappe.log_error(title="Number Card Control seed catch-up failed")


def after_migrate():
	try:
		ensure_chief_manager_sensitive_seed()
	except Exception:
		frappe.log_error(title="Number Card Control after_migrate seed failed")
