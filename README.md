# OPDS Client — Calibre Plugin

A Calibre plugin for browsing and downloading books from [OPDS](https://opds.io/) catalog servers directly into your Calibre library.

## Features

- **Multiple servers** — add, edit, delete, and reorder any number of OPDS servers
- **Navigation feed browsing** — explore categories, authors, shelves, and series as a tree
- **Book list view** — title, author, format, and file size at a glance
- **One-click download** — books are added straight into the Calibre library with correct metadata (title, author, publisher)
- **Multiple formats** — when a book has several formats (EPUB, PDF, …) a selection dialog lets you choose
- **Search** — keyword search against the OPDS server
- **Pagination** — next/previous page navigation for large catalogs
- **Basic Auth** — supports password-protected servers (HTTP Basic Authentication)
- **Robust XML parsing** — falls back to lxml recover mode for malformed OPDS feeds
- **Internationalization** — UI language follows Calibre's locale setting; Korean (`ko`) is included out of the box

## Requirements

| Requirement | Version |
|---|---|
| Calibre | 5.0 or later |
| Python | 3.8 or later (bundled with Calibre) |
| Qt | PyQt5 (bundled with Calibre) |

No external pip packages are required — the plugin uses only libraries that ship with Calibre.

## Installation

### From source

```bash
git clone <repo-url>
cd calibre_plugin
calibre-customize -b opds_client
```

### From a zip file

1. Build the zip: `calibre-customize -b opds_client` (the zip is created automatically)
2. In Calibre: **Preferences → Plugins → Load plugin from file** → select the zip

## Quick Start

1. Click the **OPDS Client** button in the Calibre toolbar.
2. Click **Manage Servers** → **Add** to register your first OPDS server.
3. Select the server from the drop-down. The root feed loads automatically.
4. **Double-click** a category (📁) to navigate into it.
5. When a book list appears, **click a row** to select it, then click **Download Selected**.
6. The book is downloaded and added to your Calibre library immediately.

## UI Overview

```
┌─────────────────────────────────────────────────┐
│ Server: [My Calibre-Web          ▼] [Manage Servers] │
│ [◄ Back]  Path: Home > Authors > Jane Austen     │
├─────────────────────────────────────────────────┤
│                                                 │
│  (Navigation feed)          (Acquisition feed)  │
│  📁 Authors                 Title | Author | Fmt │
│  📁 Categories              Pride… | Austen | epub│
│  📁 Series                  Emma   | Austen | pdf │
│  …                          …                   │
│                                                 │
├─────────────────────────────────────────────────┤
│ Search: [___________________] [Search]          │
│                        [Download Selected]      │
│         Page:  ◄  1  ►                          │
└─────────────────────────────────────────────────┘
```

## Server Configuration

Each server entry stores the following fields:

| Field | Description |
|---|---|
| `name` | Display name shown in the drop-down |
| `url` | Root OPDS URL (must start with `http://` or `https://`) |
| `auth` | `"basic"` or `"none"` |
| `username` | Used only when `auth` is `"basic"` |
| `password` | Stored in plain text in Calibre's local config file |

Settings are persisted via Calibre's `JSONConfig` at `~/.config/calibre/plugins/opds_client.json`.

## File Structure

```
opds-client/
├── Makefile                          # macOS build script (make build / make clean)
├── README.md
└── calibre_plugin/
    ├── __init__.py                   # Plugin entry point (InterfaceActionBase)
    ├── plugin-import-name-opds_client.txt
    ├── config.py                     # Server list persistence (JSONConfig)
    ├── opds_parser.py                # OPDS XML parser (navigation / acquisition)
    ├── model.py                      # Qt table model for the book list
    ├── main.py                       # Main dialog + OPDSClientAction
    ├── server_dialog.py              # Add / edit server dialog
    ├── image/
    │   └── opds_client_icon.png      # Toolbar icon
    └── translations/
        ├── ko.po                     # Korean translation source
        └── ko.mo                     # Compiled binary (loaded at runtime)
```

## Internationalization

The plugin uses **English as the base language**. All translatable strings are wrapped with `_()`. Calibre automatically injects `load_translations()` into every module loaded from the plugin zip, which sets up `_()` from the matching `translations/{lang}.mo` file.

### How it works at runtime

```
Calibre locale = "ko"
  → zipplugin reads translations/ko.mo from the plugin zip
  → _() returns Korean strings

Calibre locale = "en" (or any language without a .mo file)
  → _() returns the English source strings unchanged
```

### Adding a new language

**1. Copy the Korean `.po` file as a starting point:**

```bash
cd opds_client/translations
cp ko.po ja.po          # or zh.po, de.po, fr.po, …
```

**2. Edit `ja.po` — translate every `msgstr`:**

```po
msgid "Manage Servers"
msgstr "サーバー管理"          # ← your translation here

msgid "Download Selected"
msgstr "選択してダウンロード"
```

Leave `msgstr ""` blank for any string you have not translated yet; Calibre will fall back to the English `msgid`.

**3. Compile to a binary `.mo` file:**

```bash
msgfmt ja.po -o ja.mo
```

`msgfmt` is part of the standard GNU gettext tools (`gettext` package on most Linux distros, available via Homebrew on macOS, and via the gettext Windows installer).

**4. Reinstall the plugin:**

```bash
cd ../..                  # back to calibre_plugin/
calibre-customize -b opds_client
```

**5. Change Calibre's interface language** to Japanese (Preferences → Look & Feel → User interface language), restart Calibre, and the new strings will appear.

### Updating translations after a code change

When new UI strings are added to the source code:

1. Add the new `msgid`/`msgstr` pairs to each `.po` file.
2. Recompile: `msgfmt <lang>.po -o <lang>.mo`
3. Reinstall: `calibre-customize -b opds_client`

> **Tip:** Tools like [Poedit](https://poedit.net/) provide a graphical editor for `.po` files and can highlight untranslated or fuzzy strings.

## Building on macOS

Requires `make` (included with Xcode Command Line Tools).

```bash
make build   # creates opds_client.zip
make clean   # removes opds_client.zip
```

The zip includes all plugin files and `README.md`.

## Development

### Build & install

```bash
cd calibre_plugin
calibre-customize -b opds_client
```

### Debugging

Use Calibre's built-in logger instead of `print()`:

```python
from calibre.utils.logging import default_log
default_log('debug message')
```

Launch Calibre from a terminal to see log output:

```bash
calibre-debug -g
```

### Coding conventions

- **PyQt5 only** — do not use PyQt6 imports
- **No external dependencies** — use only modules bundled with Calibre
- All user-visible strings must be wrapped with `_()` and have a corresponding entry in every `.po` file
- Call `load_translations()` at module level (before any `_()` call) in every `.py` file that contains translatable strings

## Known Limitations / Roadmap

- [ ] Encrypted password storage
- [ ] Cover image thumbnails in the book list
- [ ] Filter out books already present in the library
- [ ] Import additional metadata (tags, series, rating) from OPDS entries
- [ ] OPDS 1.2 / 2.0 support

## License

BSD License — see `__init__.py` for details.

---

> This plugin was written with the assistance of [Claude.ai](https://claude.ai/).
