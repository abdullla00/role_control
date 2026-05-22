# Role Control

Advanced role utilities and UI control overrides for Frappe and ERPNext.

## Form Button Control

Centrally hide form and list buttons per **Role** and/or **User**, optionally scoped by **Company**.

### Installation

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app apps/role_control
bench --site <site> install-app role_control
bench migrate
bench build --app role_control
```

### Creating a rule

1. Open **Role Control** workspace → **Form Button Control**.
2. Set **Role** or **User** (at least one required).
3. Optionally set **Company** (blank = all companies).
4. Set **Priority** (higher wins when rules conflict).
5. Add child rows:
   - **Reference DocType** — target form (e.g. `Job Order`).
   - **View** — `Form`, `List`, or `Both`.
   - **Button Category** — `Standard`, `Custom`, `Workflow`, or `Menu Action`.
   - **Button Label** — Autocomplete suggestions from JS scan + hook registry (Custom / Menu Action); you can still type a custom label.
   - **Button Group** — optional third argument to `add_custom_button`.
   - **Apply On Docstatus** — when the rule applies on forms (`All` = always).

### Company matching

- On **forms**, the open document’s `company` field is used when present; otherwise the user’s default Company.
- On **list views**, the user’s default Company is used.

### Dynamic button label options

For **Custom** and **Menu Action**, when you set **Reference DocType**, **Button Label** loads suggestions from:

1. **JS scan** — `add_custom_button` / `add_menu_item` in doctype `.js`, hook `doctype_js` / `doctype_list_js`, and enabled **Client Script** records.
2. **Menu catalog** — common Frappe form menu items (`Email`, `Duplicate`, `Rename`, …) for Menu Action.
3. **`button_control_registry` hook** — other apps register extra labels (registry wins over scan for the same label).

Optional: in any app's `hooks.py`:

```python
button_control_registry = {
    "Job Order": [
        {"category": "Custom", "label": "Make Return Ticket", "group": None},
    ],
}
```

**Limitations:** Only literal `__("Label")` strings in `add_custom_button` calls are discovered (including multiline calls with a third-argument group). Dynamic first arguments (variables) and `__("View {0}", [ref])` are not scanned; literal `__("View …")` labels in JS maps are listed under group **Navigate**. Grid `add_custom_button` calls (e.g. row **Swap**) are ignored. Override or type labels manually via the `button_control_registry` hook when needed.

**Using the dropdown:** In the child table row editor, click **Button Label** or **Button Group** (or focus the field) to load suggestions. Options are loaded via `get_query` when the field is focused, not as a static Select list.

### Button label examples (Galiska Job Order)

| Label | Category |
|-------|----------|
| `Make Return Ticket` | Custom |
| `Complete Operation` | Custom |
| `Submit` | Standard |
| `Cancel` | Standard |
| Workflow transition name | Workflow |
| `Email` | Menu Action |

### Security

Button hiding is **UI-only**. Users may still invoke actions via API, shortcuts, or custom scripts unless blocked by DocPerm and server-side checks. Do not rely on this app as the sole authorization layer.

### Bypass

Rules do not apply when logged in as **Administrator** (so setup is never blocked). Rules **do** apply to users with the **System Manager** role, including rules where `role` = System Manager (e.g. FBC-00037).

### Tests

```bash
bench --site <site> run-tests --app role_control
```
