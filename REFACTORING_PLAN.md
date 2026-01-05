# FiberQ Main Plugin Refactoring Plan

**Created:** 2026-01-05
**Target File:** `fiberq/main_plugin.py` (12,757 lines)
**Goal:** Improve maintainability, testability, and code organization

---

## 🎯 Refactoring Objectives

1. **Reduce file size** from 12,757 lines to < 1,000 lines
2. **Improve modularity** by separating concerns into logical modules
3. **Enhance testability** by isolating business logic
4. **Simplify maintenance** by reducing complexity per file
5. **Improve code reusability** through better abstractions

---

## 📊 Current State Analysis

### File Statistics:
- **Total Lines:** 12,757
- **Classes:** 47 (UI classes, dialogs, map tools)
- **Functions:** 414 methods in StuboviPlugin class
- **Dependencies:** High coupling between components

### Major Components:
1. **Main Plugin Class** (`StuboviPlugin`) - ~10,000+ lines
2. **UI Group Classes** (8 classes) - ~1,500 lines
3. **Dialog Classes** (15+ classes) - ~2,000 lines
4. **Map Tool Classes** (10+ classes) - ~3,000 lines
5. **Helper Functions** - scattered throughout

---

## 🏗️ Proposed Architecture

```
fiberq/
├── main_plugin.py           # Plugin entry point (~500 lines)
├── core/
│   ├── __init__.py
│   ├── plugin.py            # Main StuboviPlugin class (~800 lines)
│   ├── layer_manager.py     # Layer creation and management
│   ├── style_manager.py     # Styling and symbology
│   └── config_manager.py    # Configuration handling
├── ui/
│   ├── __init__.py
│   ├── routing_ui.py        # RoutingUI class
│   ├── cable_laying_ui.py   # CableLayingUI class
│   ├── element_placement_ui.py
│   ├── ducting_ui.py
│   ├── selection_ui.py
│   ├── slack_ui.py
│   ├── drawings_ui.py
│   └── objects_ui.py
├── dialogs/
│   ├── __init__.py
│   ├── bom_dialog.py        # Bill of Materials
│   ├── correction_dialog.py # Route correction
│   ├── slack_dialog.py      # Optical slack
│   ├── duct_dialogs.py      # PE and Transition ducts
│   ├── locator_dialog.py    # Element locator
│   ├── schematic_dialog.py  # Optical schematic
│   └── settings_dialog.py   # Plugin settings
├── tools/
│   ├── __init__.py
│   ├── breakpoint_tool.py   # BreakpointTool
│   ├── manual_route_tool.py # ManualRouteTool
│   ├── place_element_tool.py
│   ├── extension_tool.py
│   ├── reserve_place_tool.py
│   ├── pipe_place_tool.py
│   ├── smart_select_tool.py
│   └── move_feature_tool.py
├── utils/
│   ├── __init__.py
│   ├── geometry.py          # Geometry utilities
│   ├── routing.py           # Path finding algorithms
│   ├── field_aliases.py     # Field alias management
│   ├── constants.py         # Constants and enums
│   └── validators.py        # Input validation
├── models/
│   ├── __init__.py
│   ├── element_defs.py      # Element definitions
│   └── color_catalogs.py    # Fiber color catalogs
└── addons/                  # Already exists
    └── ... (existing addons)
```

---

## 📝 Refactoring Steps (Phase-by-Phase)

### **Phase 1: Extract Constants and Configuration** ✓ Low Risk
**Goal:** Move all constants, element definitions, and configuration to separate files

**Files to Create:**
- `utils/constants.py`
- `models/element_defs.py`
- `models/color_catalogs.py`

**What to Extract:**
- `ELEMENT_DEFS` (lines 475-505)
- `NASTAVAK_DEF` (line 506)
- `TRASA_TYPE_OPTIONS`, `TRASA_TYPE_LABELS` (lines 941-951)
- Color constants (`COLOR_GLAVNI`, `COLOR_DISTR`, `COLOR_RAZV`)
- Fiber color catalogs (lines 2424+)
- Element icons mapping

**Estimated Reduction:** ~500 lines

---

### **Phase 2: Extract Utility Functions** ✓ Low Risk
**Goal:** Move standalone helper functions to utility modules

**Files to Create:**
- `utils/geometry.py`
- `utils/routing.py`
- `utils/field_aliases.py`

**What to Extract:**
- Geometry utilities (snapping, distance calculations)
- Path finding algorithms:
  - `_build_path_across_network()` (line 1801)
  - `_build_path_across_joined_trasa()` (line 1905)
- Field alias application functions
- Format conversion utilities

**Estimated Reduction:** ~800 lines

---

### **Phase 3: Extract Map Tools** ⚠️ Medium Risk
**Goal:** Move all map tool classes to separate files

**Files to Create:**
- `tools/breakpoint_tool.py`
- `tools/manual_route_tool.py`
- `tools/place_element_tool.py`
- `tools/extension_tool.py`
- `tools/reserve_place_tool.py`
- `tools/pipe_place_tool.py`
- `tools/smart_select_tool.py`
- `tools/move_feature_tool.py`

**Classes to Extract:**
1. **BreakpointTool** (line 6984) - ~500 lines
2. **ManualRouteTool** (line 7461) - ~320 lines
3. **PlaceElementTool** - ~200 lines
4. **ExtensionTool** - ~150 lines
5. **OknoPlaceTool** - ~200 lines
6. **ReservePlaceTool** - ~450 lines
7. **PipePlaceTool** - ~300 lines
8. **SmartMultiSelectTool** - ~200 lines
9. **MoveFeatureTool** - ~150 lines
10. **DrawRegionPolygonTool** - ~100 lines

**Estimated Reduction:** ~2,500 lines

---

### **Phase 4: Extract Dialog Classes** ⚠️ Medium Risk
**Goal:** Move all dialog classes to separate files

**Files to Create:**
- `dialogs/bom_dialog.py`
- `dialogs/correction_dialog.py`
- `dialogs/slack_dialog.py`
- `dialogs/duct_dialogs.py`
- `dialogs/locator_dialog.py`
- `dialogs/schematic_dialog.py`
- `dialogs/settings_dialog.py`

**Classes to Extract:**
1. **_BOMDialog** - ~400 lines
2. **CorrectionDialog** (line 7787) - ~50 lines
3. **SlackDialog** (line 10122) - ~60 lines
4. **PEDuctDialog** (line 9413) - ~35 lines
5. **TransitionDuctDialog** (line 9447) - ~30 lines
6. **LocatorDialog** - ~300 lines
7. **OpticalSchematicDialog** - ~500 lines
8. **FiberQSettingsDialog** - ~100 lines
9. **ColorCatalogManagerDialog** - ~200 lines
10. **RelationsDialog** - ~150 lines
11. **CreateRegionDialog** - ~100 lines
12. **LatentElementsDialog** - ~100 lines
13. **OknoTypeDialog** - ~50 lines
14. **OknoDataDialog** - ~100 lines

**Estimated Reduction:** ~2,200 lines

---

### **Phase 5: Extract UI Group Classes** ✓ Low Risk
**Goal:** Move UI group classes to separate files

**Files to Create:**
- `ui/routing_ui.py`
- `ui/cable_laying_ui.py`
- `ui/element_placement_ui.py`
- `ui/ducting_ui.py`
- `ui/selection_ui.py`
- `ui/slack_ui.py`
- `ui/drawings_ui.py`
- `ui/objects_ui.py`

**Classes to Extract:**
1. **RoutingUI** (line 508) - ~150 lines
2. **DrawingsUI** (line 765) - ~30 lines
3. **CableLayingUI** (line 792) - ~40 lines
4. **ElementPlacementUI** (line 830) - ~35 lines
5. **DuctingUI** (line 863) - ~35 lines
6. **SelectionUI** (line 897) - ~45 lines
7. **SlackUI** (line 10088) - ~35 lines
8. **ObjectsUI** (line 12114) - ~60 lines

**Estimated Reduction:** ~430 lines

---

### **Phase 6: Extract Layer Management** 🔴 High Risk
**Goal:** Separate layer creation and management logic

**Files to Create:**
- `core/layer_manager.py`

**What to Extract:**
- `init_layer()` - Poles layer initialization
- `_ensure_manholes_layer()` (line 5307)
- `_ensure_slack_layer()` (line 1545)
- `_ensure_pe_duct_layer()` (line 5746)
- `_ensure_transition_duct_layer()` (line 5750)
- `_ensure_ducts_group()` (line 5594)
- `_ensure_pipe_layer()` (line 5662)
- Layer type detection methods
- Layer lookup methods

**Estimated Reduction:** ~1,200 lines

---

### **Phase 7: Extract Style Management** ⚠️ Medium Risk
**Goal:** Centralize all styling and symbology logic

**Files to Create:**
- `core/style_manager.py`

**What to Extract:**
- `stylize_route_layer()` (line 1767)
- `_stylize_cable_layer()` (line 3577)
- `_stylize_slack_layer()` (line 1589)
- `_apply_manholes_style()` (line 5402)
- `_apply_pipe_style()` (line 5755)
- Field alias methods:
  - `_apply_slack_field_aliases()`
  - `_apply_manholes_field_aliases()`
  - Various other field alias methods
- Symbol creation utilities

**Estimated Reduction:** ~1,000 lines

---

### **Phase 8: Refactor Core Plugin Class** 🔴 High Risk
**Goal:** Slim down StuboviPlugin to orchestrator role

**Files to Create:**
- `core/plugin.py`
- `core/config_manager.py`

**Strategy:**
1. Keep only orchestration logic in StuboviPlugin
2. Delegate to specialized managers:
   - `LayerManager` for layer operations
   - `StyleManager` for styling
   - `ConfigManager` for configuration
   - UI classes for toolbar/menu
3. Remove direct implementation of business logic
4. Use dependency injection for better testability

**Core Plugin Responsibilities (After Refactoring):**
- Plugin initialization/cleanup
- Toolbar creation
- Menu creation
- Coordinating between components
- Event handling delegation
- Settings management

**Target Size:** < 800 lines

---

### **Phase 9: Extract Route and Cable Logic** 🔴 High Risk
**Goal:** Separate complex business logic for routes and cables

**Files to Create:**
- `core/route_manager.py`
- `core/cable_manager.py`

**Route Manager:**
- `create_route()` (line 3403)
- `merge_all_routes()` (line 3965)
- `import_route_from_file()` (line 4406)
- `change_route_type()` (line 4530)
- `check_consistency()` (line 4959)
- `fix_route_to_pole()` (line 5013)

**Cable Manager:**
- `lay_cable()` (line 4105)
- `lay_cable_type()` (line 4099)
- `branch_cables_offset()` (line 3890)
- Slack calculation logic

**Estimated Reduction:** ~2,000 lines

---

### **Phase 10: Documentation and Testing** ✅ Critical
**Goal:** Document new structure and add tests

**Tasks:**
1. Add module docstrings to all new files
2. Document public APIs
3. Create architecture diagram
4. Write unit tests for utility functions
5. Write integration tests for core workflows
6. Update README with new structure
7. Create migration guide for developers

---

## 🔧 Implementation Guidelines

### **General Principles:**
1. **One Change at a Time:** Complete each phase before moving to next
2. **Test After Each Phase:** Ensure functionality works after extraction
3. **Maintain Backward Compatibility:** Don't break existing installations
4. **Use Type Hints:** Add type annotations to new modules
5. **Document Public APIs:** Clear docstrings for all public methods
6. **Keep Imports Clean:** Use relative imports within package

### **Testing Strategy:**
1. **Manual Testing:** Test all major workflows after each phase
2. **Smoke Tests:** Quick functionality checks
3. **Regression Testing:** Ensure old features still work
4. **Integration Testing:** Test component interactions

### **Risk Mitigation:**
- ✓ **Low Risk:** Can be done safely with minimal testing
- ⚠️ **Medium Risk:** Requires careful testing
- 🔴 **High Risk:** Needs extensive testing and backup

---

## 📦 Expected Results

### **Before Refactoring:**
```
fiberq/
├── main_plugin.py          12,757 lines (monolithic)
├── addons/                 8 modules
└── config.ini
```

### **After Refactoring:**
```
fiberq/
├── main_plugin.py          ~500 lines (entry point)
├── core/                   5 modules (~3,000 lines)
├── ui/                     8 modules (~430 lines)
├── dialogs/                7 modules (~2,200 lines)
├── tools/                  10 modules (~2,500 lines)
├── utils/                  5 modules (~1,300 lines)
├── models/                 2 modules (~500 lines)
├── addons/                 8 modules (existing)
└── config.ini
```

**Total Lines:** Still ~12,757 but organized into 37+ focused modules averaging ~350 lines each

---

## ⏱️ Estimated Timeline

### **Conservative Estimate (Full Refactoring):**
- **Phase 1-2:** 2 days (constants, utilities)
- **Phase 3:** 3 days (map tools)
- **Phase 4:** 3 days (dialogs)
- **Phase 5:** 1 day (UI classes)
- **Phase 6:** 4 days (layer management)
- **Phase 7:** 3 days (style management)
- **Phase 8:** 5 days (core plugin refactor)
- **Phase 9:** 4 days (route/cable logic)
- **Phase 10:** 3 days (documentation/testing)

**Total:** ~28 days (5-6 weeks)

### **Quick Wins (Phases 1-5 Only):**
- **Timeline:** ~10 days
- **Reduction:** ~5,630 lines extracted
- **Remaining:** ~7,127 lines in main_plugin.py
- **Benefit:** Significantly improved organization with lower risk

---

## 🎯 Success Criteria

### **Quantitative:**
- [ ] main_plugin.py reduced to < 1,000 lines
- [ ] Average module size < 500 lines
- [ ] No module > 1,000 lines
- [ ] At least 30 separate modules created
- [ ] 100% of existing functionality preserved

### **Qualitative:**
- [ ] Code is easier to understand
- [ ] New developers can navigate codebase easily
- [ ] Components are testable in isolation
- [ ] Dependencies are clear and explicit
- [ ] Changes can be made with less risk

---

## 📋 Next Steps

1. **Review Plan:** Get approval from team/maintainer
2. **Create Branch:** `refactor/modularize-main-plugin`
3. **Start with Phase 1:** Extract constants (safest, quick win)
4. **Iterate:** Complete phases sequentially
5. **Test Continuously:** After each phase
6. **Document:** Update docs as you go
7. **Review:** Code review after each major phase

---

## 🚨 Risks and Mitigation

### **High-Risk Areas:**
1. **Plugin Initialization:** Breaking QGIS plugin loading
   - *Mitigation:* Keep `__init__.py` and entry points unchanged

2. **Circular Dependencies:** Import cycles between new modules
   - *Mitigation:* Careful dependency planning, use dependency injection

3. **State Management:** Shared state between components
   - *Mitigation:* Explicit state passing, avoid global state

4. **QGIS API Changes:** Compatibility with different QGIS versions
   - *Mitigation:* Test on multiple QGIS versions

5. **User Projects:** Breaking existing user projects
   - *Mitigation:* Maintain all layer names, field names, behaviors

---

## 💡 Additional Recommendations

### **Beyond Refactoring:**
1. **Add Type Hints:** Use Python type annotations throughout
2. **Add Logging:** Replace print statements with proper logging
3. **Error Handling:** Consistent error handling strategy
4. **Configuration:** Move hardcoded values to config
5. **Internationalization:** Prepare for multi-language support
6. **Plugin Settings:** Centralized settings management
7. **Performance:** Profile and optimize hot paths
8. **Code Quality:** Set up linters (flake8, pylint, mypy)

### **Future Enhancements:**
1. **Plugin API:** Expose public API for extensions
2. **Event System:** Implement plugin event hooks
3. **Unit Tests:** Add comprehensive test suite
4. **CI/CD:** Automated testing and deployment
5. **Documentation:** API documentation (Sphinx)

---

*This plan provides a roadmap for transforming main_plugin.py from a monolithic 12,757-line file into a well-organized, maintainable codebase with clear separation of concerns.*
