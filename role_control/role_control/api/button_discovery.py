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

ADD_CUSTOM_BUTTON_NEEDLE = "add_custom_button"
SKIP_ADD_CUSTOM_BUTTON_PREFIXES = ("grid.", "listview.")

# Literal __("View …") used in navigate helpers / label maps.
VIEW_BUTTON_LABEL_PATTERN = re.compile(
	r"""__\s*\(\s*["'](View [^"']+)["']\s*\)""",
	re.MULTILINE,
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


def _extract_i18n_literal(arg: str) -> str | None:
	arg = (arg or "").strip()
	if not arg:
		return None

	match = re.match(r"""^__\s*\(\s*["']([^"']+)["']\s*\)""", arg)
	if match:
		return match.group(1).strip()

	match = re.match(r"""^["']([^"']+)["']\s*$""", arg)
	if match:
		return match.group(1).strip()

	return None


def _split_js_call_args(content: str, args_start: int) -> list[str]:
	"""Split top-level arguments for a call whose '(' opens at args_start - 1."""
	args: list[str] = []
	current: list[str] = []
	depth_paren = 1
	depth_brace = 0
	depth_bracket = 0
	string_char: str | None = None
	escape = False
	i = args_start

	while i < len(content) and depth_paren > 0:
		char = content[i]

		if string_char:
			current.append(char)
			if escape:
				escape = False
			elif char == "\\":
				escape = True
			elif char == string_char:
				string_char = None
			i += 1
			continue

		if char in ("'", '"', "`"):
			string_char = char
			current.append(char)
			i += 1
			continue

		if char == "(":
			depth_paren += 1
			current.append(char)
		elif char == ")":
			depth_paren -= 1
			if depth_paren == 0:
				part = "".join(current).strip()
				if part:
					args.append(part)
				break
			current.append(char)
		elif char == "{":
			depth_brace += 1
			current.append(char)
		elif char == "}":
			depth_brace -= 1
			current.append(char)
		elif char == "[":
			depth_bracket += 1
			current.append(char)
		elif char == "]":
			depth_bracket -= 1
			current.append(char)
		elif char == "," and depth_paren == 1 and depth_brace == 0 and depth_bracket == 0:
			args.append("".join(current).strip())
			current = []
		else:
			current.append(char)

		i += 1

	return args


def _iter_add_custom_button_calls(content: str):
	"""Yield (label, group) for frm/page add_custom_button calls (not grid)."""
	pos = 0
	needle_len = len(ADD_CUSTOM_BUTTON_NEEDLE)

	while True:
		idx = content.find(ADD_CUSTOM_BUTTON_NEEDLE, pos)
		if idx == -1:
			break

		prefix = content[max(0, idx - 12) : idx]
		if any(prefix.endswith(skip) for skip in SKIP_ADD_CUSTOM_BUTTON_PREFIXES):
			pos = idx + needle_len
			continue

		open_paren = content.find("(", idx + needle_len)
		if open_paren == -1:
			pos = idx + 1
			continue

		args = _split_js_call_args(content, open_paren + 1)
		if args:
			label = _extract_i18n_literal(args[0])
			group = _extract_i18n_literal(args[2]) if len(args) >= 3 else None
			if label:
				yield label, group

		pos = open_paren + 1


def _scan_view_button_literals(content: str, source: str) -> dict[tuple[str, str | None], ButtonOption]:
	"""Pick up __("View …") labels (e.g. navigate label maps)."""
	found: dict[tuple[str, str | None], ButtonOption] = {}
	for match in VIEW_BUTTON_LABEL_PATTERN.finditer(content):
		label = match.group(1).strip()
		if label:
			key = (label, "Navigate")
			found[key] = _make_option(label, "Navigate", source)
	return found


def _scan_custom_buttons(content: str, source: str) -> dict[tuple[str, str | None], ButtonOption]:
	found: dict[tuple[str, str | None], ButtonOption] = {}

	for label, group in _iter_add_custom_button_calls(content):
		key = (label, group)
		found[key] = _make_option(label, group, source)

	# Navigate map literals; grouped entries from the parser win on duplicate keys.
	for key, option in _scan_view_button_literals(content, source).items():
		found.setdefault(key, option)

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
	"""One row per label; merge group hints when the same label appears in multiple groups."""
	by_value: dict[str, dict] = {}

	for option in options:
		value = option["value"]
		description = option.get("description") or ""
		if value in by_value:
			existing = by_value[value]["description"]
			if description and description not in existing:
				by_value[value]["description"] = (
					f"{existing}; {description}" if existing else description
				)
			continue
		by_value[value] = {
			"value": value,
			"label": option["label"],
			"description": description,
		}

	return sorted(by_value.values(), key=lambda row: (row.get("label") or "").lower())


def _get_unique_groups(doctype: str, view: str, button_label: str | None = None) -> list[str]:
	options = _get_cached_button_options(doctype, "Custom", view or "Form")
	has_toolbar = False
	named_groups: set[str] = set()

	for option in options:
		if button_label and option.get("value") != button_label:
			continue
		group = (option.get("group") or "").strip()
		if group:
			named_groups.add(group)
		else:
			has_toolbar = True

	result: list[str] = []
	if has_toolbar:
		result.append("")
	result.extend(sorted(named_groups))
	return result


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

	return [
		{
			"value": group,
			"label": "(Main toolbar)" if group == "" else group,
			"description": "",
		}
		for group in groups
	]
