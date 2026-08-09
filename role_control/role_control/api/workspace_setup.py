# Copyright (c) 2026, Abdulla & Brusk and contributors
# For license information, please see license.txt

"""Ensure Role Control desk workspace, sidebar, desktop icon, and KPI cards exist."""

from __future__ import annotations

import json

import frappe
from frappe.modules.export_file import export_to_files

WORKSPACE_NAME = "Role Control"
SIDEBAR_NAME = "Role Control"

NUMBER_CARDS = (
	{
		"name": "RC Button Rules",
		"label": "Button Rules",
		"document_type": "Form Button Control",
		"function": "Count",
		"filters_json": json.dumps([["Form Button Control", "enabled", "=", 1]]),
	},
	{
		"name": "RC Number Card Rules",
		"label": "Number Card Rules",
		"document_type": "Number Card Control",
		"function": "Count",
		"filters_json": json.dumps([["Number Card Control", "enabled", "=", 1]]),
	},
	{
		"name": "RC Hidden Cards",
		"label": "Hidden Cards",
		"document_type": "Number Card Control Detail",
		"function": "Count",
		"filters_json": json.dumps([["Number Card Control Detail", "hide", "=", 1]]),
		"parent_document_type": "Number Card Control",
	},
)


def _ensure_number_card(spec: dict) -> str:
	name = spec["name"]
	if frappe.db.exists("Number Card", name):
		doc = frappe.get_doc("Number Card", name)
	else:
		doc = frappe.new_doc("Number Card")
		doc.name = name
		doc.flags.name_set = True

	doc.label = spec["label"]
	doc.type = "Document Type"
	doc.document_type = spec["document_type"]
	doc.function = spec["function"]
	doc.filters_json = spec.get("filters_json") or "[]"
	doc.is_public = 1
	doc.is_standard = 1
	doc.module = "Role Control"
	doc.show_percentage_stats = 0
	if spec.get("parent_document_type"):
		doc.parent_document_type = spec["parent_document_type"]

	if doc.is_new():
		doc.insert(ignore_permissions=True, set_name=name)
	else:
		doc.save(ignore_permissions=True)
	return doc.name


def _workspace_content() -> str:
	blocks = [
		{
			"id": "rc_hero",
			"type": "header",
			"data": {
				"text": '<span class="h3"><b>Role Control</b></span>',
				"col": 12,
			},
		},
		{
			"id": "rc_mission",
			"type": "paragraph",
			"data": {
				"text": (
					"Server-aware access controls for Desk UI — hide form buttons and sensitive "
					"number cards per role or user, without breaking workspaces."
				),
				"col": 12,
			},
		},
		{"id": "rc_spacer_1", "type": "spacer", "data": {"col": 12}},
		{
			"id": "rc_nc_buttons",
			"type": "number_card",
			"data": {"number_card_name": "RC Button Rules", "col": 4},
		},
		{
			"id": "rc_nc_cards",
			"type": "number_card",
			"data": {"number_card_name": "RC Number Card Rules", "col": 4},
		},
		{
			"id": "rc_nc_hidden",
			"type": "number_card",
			"data": {"number_card_name": "RC Hidden Cards", "col": 4},
		},
		{"id": "rc_spacer_2", "type": "spacer", "data": {"col": 12}},
		{
			"id": "rc_sec_quick",
			"type": "header",
			"data": {
				"text": '<span class="h5"><b>Quick open</b></span>',
				"col": 12,
			},
		},
		{
			"id": "rc_sc_fbc",
			"type": "shortcut",
			"data": {"shortcut_name": "Form Button Control", "col": 4},
		},
		{
			"id": "rc_sc_ncc",
			"type": "shortcut",
			"data": {"shortcut_name": "Number Card Control", "col": 4},
		},
		{
			"id": "rc_sc_seed",
			"type": "shortcut",
			"data": {"shortcut_name": "Chief Manager Seed", "col": 4},
		},
		{"id": "rc_spacer_3", "type": "spacer", "data": {"col": 12}},
		{
			"id": "rc_card_ui",
			"type": "card",
			"data": {"card_name": "UI Controls", "col": 6},
		},
		{
			"id": "rc_card_nc",
			"type": "card",
			"data": {"card_name": "Number Cards", "col": 6},
		},
	]
	return json.dumps(blocks)


def ensure_role_control_workspace(export: bool = True) -> str:
	"""Create/update Role Control workspace, sidebar, and KPIs. Returns workspace name."""
	for spec in NUMBER_CARDS:
		_ensure_number_card(spec)

	theme_exists = frappe.db.exists("DocType", "SaaS Theme Settings")

	shortcuts = [
		{
			"label": "Form Button Control",
			"link_to": "Form Button Control",
			"type": "DocType",
			"doc_view": "List",
			"color": "Blue",
		},
		{
			"label": "Number Card Control",
			"link_to": "Number Card Control",
			"type": "DocType",
			"doc_view": "List",
			"color": "Orange",
		},
		{
			"label": "Chief Manager Seed",
			"link_to": "Number Card Control",
			"type": "DocType",
			"doc_view": "List",
			"color": "Red",
			"stats_filter": json.dumps({"is_system_seed": 1}),
		},
	]
	if theme_exists:
		shortcuts.append(
			{
				"label": "SaaS Theme Settings",
				"link_to": "SaaS Theme Settings",
				"type": "DocType",
				"doc_view": "Form",
				"color": "Purple",
			}
		)

	links = [
		{"type": "Card Break", "label": "UI Controls", "hidden": 0, "link_count": 1},
		{
			"type": "Link",
			"label": "Form Button Control",
			"link_type": "DocType",
			"link_to": "Form Button Control",
			"hidden": 0,
			"onboard": 1,
			"is_query_report": 0,
			"link_count": 0,
		},
		{"type": "Card Break", "label": "Number Cards", "hidden": 0, "link_count": 1},
		{
			"type": "Link",
			"label": "Number Card Control",
			"link_type": "DocType",
			"link_to": "Number Card Control",
			"hidden": 0,
			"onboard": 1,
			"is_query_report": 0,
			"link_count": 0,
		},
	]
	if theme_exists:
		links.extend(
			[
				{"type": "Card Break", "label": "Appearance", "hidden": 0, "link_count": 1},
				{
					"type": "Link",
					"label": "SaaS Theme Settings",
					"link_type": "DocType",
					"link_to": "SaaS Theme Settings",
					"hidden": 0,
					"onboard": 0,
					"is_query_report": 0,
					"link_count": 0,
				},
			]
		)

	if frappe.db.exists("Workspace", WORKSPACE_NAME):
		ws = frappe.get_doc("Workspace", WORKSPACE_NAME)
		ws.shortcuts = []
		ws.links = []
		ws.number_cards = []
		ws.roles = []
	else:
		ws = frappe.new_doc("Workspace")
		ws.name = WORKSPACE_NAME
		ws.flags.name_set = True

	ws.label = WORKSPACE_NAME
	ws.title = WORKSPACE_NAME
	ws.module = "Role Control"
	ws.icon = "shield"
	ws.indicator_color = "orange"
	ws.public = 1
	ws.is_hidden = 0
	ws.hide_custom = 0
	ws.for_user = ""
	ws.content = _workspace_content()
	ws.app = "role_control"
	ws.sequence_id = ws.sequence_id or 20

	for s in shortcuts:
		ws.append("shortcuts", s)
	for link in links:
		ws.append("links", link)
	for card in NUMBER_CARDS:
		ws.append("number_cards", {"number_card_name": card["name"], "label": card["label"]})
	ws.append("roles", {"role": "System Manager"})

	if ws.is_new():
		ws.insert(ignore_permissions=True, set_name=WORKSPACE_NAME)
	else:
		ws.save(ignore_permissions=True)

	_ensure_sidebar()
	_ensure_desktop_icon()

	if export and frappe.conf.developer_mode:
		export_to_files(
			record_list=[
				["Workspace", WORKSPACE_NAME],
				*[["Number Card", c["name"]] for c in NUMBER_CARDS],
			],
			record_module="Role Control",
		)

	frappe.clear_cache()
	return WORKSPACE_NAME


def after_migrate():
	try:
		ensure_role_control_workspace(export=False)
	except Exception:
		frappe.log_error(title="Role Control workspace setup failed")


def _ensure_sidebar():
	if frappe.db.exists("Workspace Sidebar", SIDEBAR_NAME):
		sb = frappe.get_doc("Workspace Sidebar", SIDEBAR_NAME)
		sb.items = []
	else:
		sb = frappe.new_doc("Workspace Sidebar")
		sb.name = SIDEBAR_NAME
		sb.flags.name_set = True

	sb.title = SIDEBAR_NAME
	sb.header_icon = "shield"
	sb.module = "Role Control"
	sb.standard = 0
	sb.append(
		"items",
		{
			"label": "Home",
			"link_type": "Workspace",
			"link_to": WORKSPACE_NAME,
			"type": "Link",
		},
	)
	sb.append(
		"items",
		{
			"label": "Form Button Control",
			"link_type": "DocType",
			"link_to": "Form Button Control",
			"type": "Link",
		},
	)
	sb.append(
		"items",
		{
			"label": "Number Card Control",
			"link_type": "DocType",
			"link_to": "Number Card Control",
			"type": "Link",
		},
	)
	if frappe.db.exists("DocType", "SaaS Theme Settings"):
		sb.append(
			"items",
			{
				"label": "SaaS Theme Settings",
				"link_type": "DocType",
				"link_to": "SaaS Theme Settings",
				"type": "Link",
			},
		)

	if sb.is_new():
		sb.insert(ignore_permissions=True, set_name=SIDEBAR_NAME)
	else:
		sb.save(ignore_permissions=True)


def _ensure_desktop_icon():
	existing = frappe.db.get_value("Desktop Icon", {"label": WORKSPACE_NAME}, "name")
	if existing:
		icon = frappe.get_doc("Desktop Icon", existing)
	else:
		icon = frappe.new_doc("Desktop Icon")

	icon.label = WORKSPACE_NAME
	icon.icon = "shield"
	icon.icon_type = "Link"
	icon.link_type = "Workspace Sidebar"
	icon.link_to = SIDEBAR_NAME
	icon.sidebar = SIDEBAR_NAME
	icon.app = "role_control"
	icon.hidden = 0
	icon.standard = 0
	icon.parent_icon = ""
	icon.bg_color = "blue"
	icon.roles = []
	icon.append("roles", {"role": "System Manager"})
	if icon.is_new():
		icon.insert(ignore_permissions=True)
	else:
		icon.save(ignore_permissions=True)
