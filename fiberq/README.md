# FiberQ v1.2

A QGIS plugin for fiber optic network design and documentation.

## What's New in v1.2 — Productivity Release

### Feature 1: Manhole ID Auto-Increment

Place 20+ manholes without retyping the ID. Enter a starting ID like `MH 1` or `OKNO-001`, check "Auto-increment", and each click places the next number in sequence. Handles zero-padding (`001` → `002` → `003`), custom prefixes, and skips existing IDs in the layer.

### Feature 2: FiberQ Undo System

Independent undo/redo that works reliably across all FiberQ layers — unlike QGIS's built-in Ctrl+Z which can struggle with plugin-created features.

- **Ctrl+Shift+Z** — Undo last FiberQ action
- **Ctrl+Shift+Y** — Redo
- Toolbar buttons with icons in the main FiberQ toolbar
- Tracks all tools: manholes, poles, elements, routes, cables, slacks, pipes, objects, regions
- Message bar shows what was undone: *"Undone: Added MH 3 (Manholes)"*
- Stack depth: 50 operations

### Feature 3: Repeat Last Command (Double-Space)

Double-tap the Space key to repeat the last FiberQ tool. No need to find the toolbar button again after a tool deactivates.

- Works with all placement tools: poles, manholes, elements, routes, cables, slacks, pipes
- Status bar shows what will repeat: `Space×2 → Place ODF`
- Manhole repeat is smart — skips the dialog and continues auto-incrementing IDs
- Single Space still works for QGIS panning (no conflict)

### Feature 4: Quick Toolbar

A compact second toolbar ("FiberQ Quick") with the 10 most-used design actions:

| Tool | Icon | Shortcut |
|------|------|----------|
| Place Pole | 🔵 | P |
| Place Manhole | 🟦 | M |
| Create Route | 📐 | R |
| Aerial Cable | 📡 | A |
| Underground Cable | 🔌 | U |
| Place ODF | ◆ | O |
| Place OTB | ◆ | T |
| Place TO | ◆ | — |
| Optical Slack | ➰ | S |
| Undo (FiberQ) | ↩ | Ctrl+Shift+Z |

- Available in **View → Toolbars → FiberQ Quick**
- Keyboard shortcuts are **off by default** (enable in FiberQ Settings to avoid conflicts)
- Toggleable in **FiberQ Settings → Quick Toolbar**

## Module Structure

```
fiberq/
├── main_plugin.py           # Main plugin class
├── core/
│   ├── config_manager.py    # Configuration handling
│   ├── layer_manager.py     # Layer creation and management
│   ├── style_manager.py     # Layer styling
│   ├── data_manager.py      # Data persistence
│   ├── export_manager.py    # Export functionality
│   └── undo_manager.py      # FiberQ undo/redo system (v1.2)
├── ui/
│   ├── quick_toolbar.py     # Quick Toolbar (v1.2)
│   └── ...                  # Toolbar UI groups
├── dialogs/                 # Dialog classes
├── tools/
│   ├── command_manager.py   # Repeat last command (v1.2)
│   └── ...                  # Map tools
├── utils/
│   ├── compat.py            # QGIS version compatibility
│   └── ...                  # Other utilities
├── models/                  # Data models
├── addons/                  # Advanced features
├── icons/                   # Toolbar icons
├── styles/                  # QML style files
└── resources/               # Map icons
```

## Features

### Core Features (Free)

- Create routes and place poles
- Lay aerial and underground cables (backbone, distribution, drop)
- Place network elements (ODF, OTB, TB, TO, Patch Panel, Joint Closures)
- Add optical slack/reserves
- Place manholes and ducting infrastructure
- Draw service areas
- Export to GeoPackage, GPX, KML/KMZ
- BOM (Bill of Materials) report generation

### Productivity Features (v1.2)

- Manhole ID auto-increment
- Independent undo/redo system
- Repeat last command (double-space)
- Quick Toolbar with optional keyboard shortcuts

### Advanced Features (Pro License)

- Preview Map integration
- Publish to PostGIS
- Relations management
- Fiber break tracking
- Infrastructure cut tools

## Installation

### From QGIS Plugin Repository

1. Open QGIS → Plugins → Manage and Install Plugins
2. Search for: **FiberQ**
3. Click Install

### Manual Installation

1. Download the plugin ZIP
2. Extract to your QGIS plugins directory:
   - Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`
   - Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
   - macOS: `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins/`
3. Restart QGIS
4. Enable the plugin in Plugins → Manage and Install Plugins

## Requirements

- **QGIS**: 3.22 LTR through 3.40+ (all versions supported)
- **Operating System**: Windows / macOS / Linux

## Backward Compatibility

v1.2 maintains full backward compatibility with v1.0 and v1.1 projects:

- All layer names work in both Serbian and English
- Database field names unchanged
- Existing QML styles work without modification
- Pro license status preserved

## Support

- Website: https://www.fiberq.net/
- Repository: https://github.com/vukovicvl/fiberq
- Issues: https://github.com/vukovicvl/fiberq/issues

## License

GPL-3.0-or-later
