# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

from __future__ import annotations

import os
import re
from typing import TypedDict

import frappe
from frappe import _
from frappe.desk.form.meta import get_code_files_via_hooks
from frappe.modules import get_module_path, scrub

OPTIONS_CACHE_PREFIX = "role_control:button_options"
OPTIONS_CACHE_TTL = 3600

FIXED_MENU_CATALOG = [
	"Customize",
	"Delete",
	"Discard",
	"Duplicate",
	"Email",
	"Jump to field",
	"Print",
	"Redo",
	"Remind",
	"Rename",
	"Show Links",
	"Toggle Sidebar",
	"Undo",
]

CUSTOM_BUTTON_PATTERNS = [
	re.compile(r"""add_custom_button\s*\(\s*__\s*\(\s*["']([^"']+)["']""", re.MULTILINE),
	re.compile(r"""add_custom_button\s*\(\s*["']([^"']+)["']""", re.MULTILINE),
]

CUSTOM_BUTTON_WITH_GROUP_PATTERN = re.compile(
	r"""add_custom_button\s*\(\s*__\s*\(\s*["']([^"']+)["']\s*\)\s*,\s*function\s*\([^)]*\)\s*\{[^}]*\}\s*,\s*__\s*\(\s*["']([^"']+)["']""",
	re.MULTILINE | re.DOTALL,
)

MENU_PATTERNS = [
	re.compile(r"""add_menu_item\s*\(\s*__\s*\(\s*["']([^"']+)["']""", re.MULTILINE),
	re.compile(r"""add_menu_item\s*\(\s*["']([^"']+)["']""", re.MULTILINE),
	re.compile(r"""add_actions_menu_item\s*\(\s*__\s*\(\s*["']([^"']+)["']""", re.MULTILINE),
	re.compile(r"""add_actions_menu_item\s*\(\s*["']([^"']+)["']""", re.MULTILINE),
]


class ButtonOption(TypedDict):
	value: str
	label: str
	group: str | None
	description: str
	source: str


def _options_cache_key(doctype: str, button_category: str, view: str) -> str:
	return f"{OPTIONS_CACHE_PREFIX}:{doctype}:{button_category}:{view}"


def clear_options_cache():
	frappe.cache.delete_keys(OPTIONS_CACHE_PREFIX)


def _can_configure_buttons() -> bool:
	if frappe.session.user == "Guest":
		return False
	if "System Manager" in frappe.get_roles():
		return True
	return frappe.has_permission("Form Button Control", "write")


def _get_doctype_js_paths(doctype: str, view: str) -> list[str]:
	paths: list[str] = []
	include_form = view in ("Form", "Both")
	include_list = view in ("List", "Both")

	try:
		meta = frappe.get_meta(doctype)
	except frappe.DoesNotExistError:
		return paths

	if meta.custom:
		return paths

	module_path = os.path.join(get_module_path(meta.module), "doctype", scrub(doctype))
	scrubbed = scrub(doctype)

	if include_form:
		form_js = os.path.join(module_path, f"{scrubbed}.js")
		if os.path.isfile(form_js):
			paths.append(form_js)

	if include_list:
		list_js = os.path.join(module_path, f"{scrubbed}_list.js")
		if os.path.isfile(list_js):
			paths.append(list_js)

	if include_form:
		paths.extend(get_code_files_via_hooks("doctype_js", doctype))
	if include_list:
		paths.extend(get_code_files_via_hooks("doctype_list_js", doctype))

	seen = set()
	unique_paths = []
	for path in paths:
		if path not in seen and os.path.isfile(path):
			seen.add(path)
			unique_paths.append(path)
	return unique_paths


def _get_client_script_contents(doctype: str, view: str) -> list[str]:
	views = []
	if view in ("Form", "Both"):
		views.append("Form")
	if view in ("List", "Both"):
		views.append("List")

	if not views:
		return []

	scripts = frappe.get_all(
		"Client Script",
		filters={"dt": doctype, "enabled": 1, "view": ["in", views]},
		fields=["script"],
	)
	return [s.script for s in scripts if s.script]


def _read_file_content(path: str) -> str:
	try:
		return frappe.read_file(path) or ""
	except OSError:
		return ""


def _scan_custom_buttons(content: str, source: str) -> dict[tuple[str, str | None], ButtonOption]:
	found: dict[tuple[str, str | None], ButtonOption] = {}

	for pattern in CUSTOM_BUTTON_PATTERNS:
		for match in pattern.finditer(content):
			label = match.group(1).strip()
			if label:
				key = (label, None)
				found[key] = _make_option(label, None, source)

	for match in CUSTOM_BUTTON_WITH_GROUP_PATTERN.finditer(content):
		label = match.group(1).strip()
		group = match.group(2).strip() if match.lastindex and match.lastindex >= 2 else None
		if label:
			key = (label, group)
			found[key] = _make_option(label, group, source)

	return found


def _scan_menu_buttons(content: str, source: str) -> dict[tuple[str, str | None], ButtonOption]:
	found: dict[tuple[str, str | None], ButtonOption] = {}

	for pattern in MENU_PATTERNS:
		for match in pattern.finditer(content):
			label = match.group(1).strip()
			if label:
				key = (label, None)
				found[key] = _make_option(label, None, source)

	return found


def _make_option(label: str, group: str | None, source: str) -> ButtonOption:
	description_parts = [f"source: {source}"]
	if group:
		description_parts.insert(0, f"group: {group}")
	return {
		"value": label,
		"label": label,
		"group": group,
		"description": " | ".join(description_parts),
		"source": source,
	}


def _collect_scanned_options(
	doctype: str, button_category: str, view: str
) -> dict[tuple[str, str | None], ButtonOption]:
	options: dict[tuple[str, str | None], ButtonOption] = {}
	scan_fn = _scan_custom_buttons if button_category == "Custom" else _scan_menu_buttons

	for path in _get_doctype_js_paths(doctype, view):
		content = _read_file_content(path)
		if content:
			options.update(scan_fn(content, f"scan:{os.path.basename(path)}"))

	for idx, content in enumerate(_get_client_script_contents(doctype, view)):
		if content:
			options.update(scan_fn(content, f"client_script:{idx}"))

	return options


def _get_registry_options(doctype: str, button_category: str) -> dict[tuple[str, str | None], ButtonOption]:
	options: dict[tuple[str, str | None], ButtonOption] = {}
	registry = frappe.get_hooks("button_control_registry") or {}

	if isinstance(registry, dict):
		entries = registry.get(doctype, [])
	else:
		entries = []

	for entry in entries:
		if isinstance(entry, str):
			continue
		category = entry.get("category") or "Custom"
		if category != button_category:
			continue
		label = (entry.get("label") or "").strip()
		if not label:
			continue
		group = entry.get("group")
		key = (label, group)
		options[key] = _make_option(label, group, "registry")

	return options


def _get_menu_catalog_options() -> dict[tuple[str, str | None], ButtonOption]:
	return {
		(label, None): _make_option(label, None, "catalog")
		for label in FIXED_MENU_CATALOG
	}


def _build_button_options(doctype: str, button_category: str, view: str) -> list[ButtonOption]:
	if button_category not in ("Custom", "Menu Action"):
		return []

	options: dict[tuple[str, str | None], ButtonOption] = {}

	if button_category == "Menu Action":
		options.update(_get_menu_catalog_options())

	options.update(_collect_scanned_options(doctype, button_category, view))
	options.update(_get_registry_options(doctype, button_category))

	return sorted(options.values(), key=lambda o: o["label"].lower())


def _get_cached_button_options(doctype: str, button_category: str, view: str) -> list[ButtonOption]:
	key = _options_cache_key(doctype, button_category, view)
	cached = frappe.cache.get_value(key)
	if cached is not None:
		return cached

	options = _build_button_options(doctype, button_category, view)
	frappe.cache.set_value(key, options, expires_in_sec=OPTIONS_CACHE_TTL)
	return options


def _filter_options_by_txt(options: list[ButtonOption], txt: str) -> list[ButtonOption]:
	if not txt:
		return options
	txt_lower = txt.lower()
	return [o for o in options if txt_lower in (o.get("label") or "").lower()]


def _as_autocomplete_results(options: list[ButtonOption]) -> list[dict]:
	return [
		{
			"value": o["value"],
			"label": o["label"],
			"description": o.get("description") or "",
		}
		for o in options
	]


def _get_unique_groups(doctype: str, view: str, button_label: str | None = None) -> list[str]:
	options = _get_cached_button_options(doctype, "Custom", view or "Form")
	groups: set[str] = set()

	for option in options:
		if button_label and option.get("value") != button_label:
			continue
		group = (option.get("group") or "").strip()
		if group:
			groups.add(group)

	return sorted(groups)


@frappe.whitelist()
def get_button_options(doctype: str, button_category: str, view: str = "Form"):
	if not _can_configure_buttons():
		frappe.throw(_("Not permitted to load button options."), frappe.PermissionError)

	if not doctype or not button_category:
		return []

	return _get_cached_button_options(doctype, button_category, view or "Form")


@frappe.whitelist()
def search_button_labels(
	txt: str = "",
	reference_doctype: str | None = None,
	button_category: str | None = None,
	view: str = "Form",
):
	if not _can_configure_buttons():
		return []

	if not reference_doctype or button_category not in ("Custom", "Menu Action"):
		return []

	options = _get_cached_button_options(reference_doctype, button_category, view or "Form")
	return _as_autocomplete_results(_filter_options_by_txt(options, txt))


@frappe.whitelist()
def search_button_groups(
	txt: str = "",
	reference_doctype: str | None = None,
	view: str = "Form",
	button_label: str | None = None,
):
	if not _can_configure_buttons():
		return []

	if not reference_doctype:
		return []

	groups = _get_unique_groups(reference_doctype, view or "Form", button_label)
	if txt:
		txt_lower = txt.lower()
		groups = [g for g in groups if txt_lower in g.lower()]

	return [{"value": group, "label": group, "description": ""} for group in groups]
