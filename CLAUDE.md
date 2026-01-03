# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FiberQ is a QGIS plugin for fiber optic network design (FTTH/GPON/FTTx). It provides tools for telecom engineers and GIS professionals to design, analyze, and document fiber networks within QGIS.

- **Minimum QGIS version**: 3.22
- **License**: GPL-3.0-or-later
- **Main entry point**: `fiberq/__init__.py` → `classFactory()` loads `FiberQPlugin` from `main_plugin.py`

## Architecture

### Plugin Structure
```
fiberq/
├── __init__.py          # QGIS plugin entry point (classFactory)
├── main_plugin.py       # Core FiberQPlugin class (~500KB, contains all UI/tools)
├── config.ini           # PostGIS connection settings
├── metadata.txt         # QGIS plugin metadata
├── addons/              # Modular feature implementations
│   ├── fiberq_preview.py    # Preview map functionality (Pro feature)
│   ├── publish_pg.py        # PostGIS export dialog
│   ├── fiber_break.py       # Fiber break point placement tool
│   ├── infrastructure_cut.py # Line splitting tool
│   ├── reserve_hook.py      # Optical slack/reserve tracking
│   ├── settings.py          # Plugin settings dialog
│   ├── hotkeys.py           # Keyboard shortcut management
│   └── styles.py            # Layer styling utilities
├── icons/               # SVG toolbar icons (ic_*.svg)
├── resources/map_icons/ # Map marker SVG icons
└── styles/              # QML layer style files
```

### Key Classes

| Class | File | Purpose |
|-------|------|---------|
| `FiberQPlugin` | main_plugin.py | Main plugin class |
| `RoutingUI` | main_plugin.py | Route creation toolbar group |
| `CableLayingUI` | main_plugin.py | Cable laying toolbar group |
| `DuctInfrastructureUI` | main_plugin.py | Duct infrastructure toolbar group |
| `SelectionUI` | main_plugin.py | Selection tools toolbar group |
| `DrawingsUI` | main_plugin.py | Drawings toolbar group |
| `ReservesUI` | main_plugin.py | Optical reserves toolbar group |
| `ManualRouteTool` | main_plugin.py | Manual route drawing map tool |
| `FiberBreakTool` | fiber_break.py | Fiber break placement map tool |
| `InfrastructureCutTool` | infrastructure_cut.py | Line splitting map tool |
| `ReserveHook` | reserve_hook.py | Optical slack tracking |

### Key Methods (FiberQPlugin)

| Method | Purpose |
|--------|---------|
| `create_route()` | Create a new route from selected poles/manholes |
| `merge_all_routes()` | Merge selected routes into one |
| `import_route_from_file()` | Import route from external file |
| `change_route_type()` | Change route type (main/distribution/drop) |
| `lay_cable_by_type()` | Lay cable along selected route |
| `separate_cables_offset()` | Offset overlapping cables |
| `activate_fiber_break_tool()` | Activate fiber break placement |
| `activate_manual_route_tool()` | Activate manual route drawing |
| `_start_reserve_interactive()` | Start interactive reserve placement |
| `generate_terminal_reserves_for_selected()` | Generate reserves at cable ends |
| `check_consistency()` | Run health check on layers |

### Layer Names (English)

| Layer Name | Purpose |
|------------|---------|
| `Poles` | Utility poles |
| `Manholes` | Underground manholes |
| `Route` | Fiber route/trace |
| `Underground_cables` | Underground cables |
| `Aerial_cables` | Aerial cables |
| `PE_ducts` | PE duct infrastructure |
| `Transition_ducts` | Transition ducts |
| `Joint_closures` | Fiber joint closures |
| `Fiber_break` | Fiber break points |
| `Optical_reserves` | Optical slack/reserves |
| `Service_area` | Service area polygons |
| `ODF`, `TB`, `OTB`, `TO` | Optical equipment |

### Design Patterns

1. **Single main_plugin.py**: Most plugin logic is in one large file containing the `FiberQPlugin` class with toolbar setup, map tools, and dialogs.

2. **Addons as Separate Modules**: Complex features (preview, PostGIS export, fiber break, infrastructure cut) are split into `addons/` for maintainability.

3. **Pro Feature Gating**: `_fiberq_check_pro()` gates "Preview Map" and "Publish to PostGIS" features behind a license key stored in QSettings.

4. **QSettings Storage**: Settings stored under org "FiberQ" / app "FiberQ". Project-specific data stored via `QgsProject.instance().writeEntry('FiberQPlugin', ...)`.

## Development Notes

### Testing the Plugin
Install by symlinking `fiberq/` folder to QGIS plugins directory:
- Linux: `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/`
- Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\`

Reload plugin from QGIS: Plugins → Manage and Install Plugins → Installed → FiberQ → Reinstall/Reload

### PostGIS Configuration
Edit `fiberq/config.ini` `[postgis]` section with database credentials before using Publish to PostGIS feature.

### Code Conventions
- Uses PyQt5/QGIS API imports (`qgis.PyQt.QtCore`, `qgis.core`, `qgis.gui`)
- All comments and docstrings in English
- Icon loading via `_load_icon()` helper function
- Layer names use underscores (e.g., `Underground_cables`, `Optical_reserves`)
- Method names use snake_case (e.g., `create_route`, `lay_cable_by_type`)

### Keyboard Shortcuts
| Shortcut | Action |
|----------|--------|
| Ctrl+B | BOM report |
| Ctrl+G | Separate cables (offset) |
| Ctrl+P | Publish to PostGIS |
| Ctrl+F | Fiber break tool |
| R | Terminal reserve |
| Shift+R | Pass-through reserve |
