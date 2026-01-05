# Serbian to English Translation Mapping

**Purpose:** Comprehensive mapping for refactoring FiberQ codebase from Serbian to English.
**Date:** 2026-01-05
**Status:** Ready for implementation

---

## CLASS NAMES

| Serbian Name | English Name | Location | Notes |
|-------------|--------------|----------|-------|
| `TrasiranjeUI` | `RoutingUI` | main_plugin.py:508 | Routing/Tracing UI |
| `CrteziUI` | `DrawingsUI` | main_plugin.py:765 | Drawings management UI |
| `PolaganjeKablovaUI` | `CableLayingUI` | main_plugin.py:792 | Cable laying UI |
| `PolaganjeElemenataUI` | `ElementPlacementUI` | main_plugin.py:830 | Element placement UI |
| `KanalizacijaUI` | `DuctingUI` | main_plugin.py:863 | Infrastructure/ducting UI |
| `SelekcijaUI` | `SelectionUI` | main_plugin.py:897 | Selection tools UI |
| `RezerveUI` | `SlackUI` | main_plugin.py:10088 | Optical slack/reserves UI |
| `ObjektiUI` | `ObjectsUI` | main_plugin.py:12114 | Objects/buildings UI |
| `LomnaTackaTool` | `BreakpointTool` | main_plugin.py:6984 | Route breaking point tool |
| `RucnaTrasaTool` | `ManualRouteTool` | main_plugin.py:7461 | Manual route drawing tool |
| `KorekcijaDialog` | `CorrectionDialog` | main_plugin.py:7787 | Route correction dialog |
| `PECevDialog` | `PEDuctDialog` | main_plugin.py:9413 | PE pipe/duct dialog |
| `PrelaznaCevDialog` | `TransitionDuctDialog` | main_plugin.py:9447 | Transition pipe dialog |
| `RezervaDialog` | `SlackDialog` | main_plugin.py:10122 | Optical slack dialog |

---

## METHOD/FUNCTION NAMES

| Serbian Name | English Name | Location | Notes |
|-------------|--------------|----------|-------|
| `stilizuj_trasa_layer` | `stylize_route_layer` | main_plugin.py:1767 | Apply route layer style |
| `_stilizuj_kablovi_layer` | `_stylize_cable_layer` | main_plugin.py:3577 | Apply cable layer style |
| `kreiraj_trasu` | `create_route` | main_plugin.py:3403 | Create new route |
| `spoji_sve_trase` | `merge_all_routes` | main_plugin.py:3965 | Merge selected routes |
| `uvezi_trasu_iz_fajla` | `import_route_from_file` | main_plugin.py:4406 | Import route from file |
| `izmeni_tip_trase` | `change_route_type` | main_plugin.py:4530 | Change route type |
| `polozi_kabl` | `lay_cable` | main_plugin.py:4105 | Lay cable on route |
| `polozi_kabl_tip` | `lay_cable_type` | main_plugin.py:4099 | Lay specific cable type |
| `proveri_konzistentnost` | `check_consistency` | main_plugin.py:4959 | Consistency check |
| `popravi_trasa_na_stub` | `fix_route_to_pole` | main_plugin.py:5013 | Fix route to pole |
| `activate_lomna_tool` | `activate_breakpoint_tool` | main_plugin.py:2485 | Activate breakpoint tool |
| `activate_rucna_trasu_tool` | `activate_manual_route_tool` | main_plugin.py:2491 | Activate manual route |
| `_start_rezerva_interaktivno` | `_start_slack_interactive` | main_plugin.py:1701 | Start slack placement |
| `generisi_zavrsne_rezerve_za_selektovane` | `generate_terminal_slack_for_selected` | main_plugin.py:1710 | Generate terminal slack |
| `_ensure_rezerve_layer` | `_ensure_slack_layer` | main_plugin.py:1546 | Ensure slack layer exists |
| `open_prelazna_cev_workflow` | `open_transition_duct_workflow` | main_plugin.py:5790 | Open transition duct workflow |
| `_ensure_prelazna_cev_layer` | `_ensure_transition_duct_layer` | main_plugin.py:5750 | Ensure transition duct layer |

---

## INSTANCE VARIABLES

| Serbian Name | English Name | Location | Notes |
|-------------|--------------|----------|-------|
| `self.lomna_tool` | `self.breakpoint_tool` | main_plugin.py:1384 | Breakpoint tool instance |
| `self.rucna_trasa_tool` | `self.manual_route_tool` | main_plugin.py:2491 | Manual route tool instance |
| `self.ui_trasiranje` | `self.ui_routing` | main_plugin.py:2086 | Routing UI reference |
| `self.ui_polaganje` | `self.ui_cable_laying` | main_plugin.py:2087 | Cable laying UI reference |
| `self.ui_kanalizacija` | `self.ui_ducting` | main_plugin.py:2088 | Ducting UI reference |
| `self.ui_selekcija` | `self.ui_selection` | main_plugin.py:2089 | Selection UI reference |
| `self.ui_rezerve` | `self.ui_slack` | main_plugin.py:2090 | Slack UI reference |
| `self.ui_crtezi` | `self.ui_drawings` | main_plugin.py:2103 | Drawings UI reference |
| `self.ui_objekti` | `self.ui_objects` | main_plugin.py:2104 | Objects UI reference |

---

## ACTION VARIABLES

| Serbian Name | English Name | Location | Notes |
|-------------|--------------|----------|-------|
| `action_trasa` | `action_route` | main_plugin.py:528 | Create route action |
| `action_spoji` | `action_merge` | main_plugin.py:535 | Merge routes action |
| `action_lomna` | `action_breakpoint` | main_plugin.py:549 | Add breakpoint action |
| `action_rucna` | `action_manual` | main_plugin.py:556 | Manual route action |
| `action_korekcija` | `action_correction` | main_plugin.py:570 | Route correction action |

---

## CONSTANTS

| Serbian Name | English Name | Location | Notes |
|-------------|--------------|----------|-------|
| `COLOR_GLAVNI` | `COLOR_BACKBONE` | main_plugin.py:3620 | Backbone cable color |
| `COLOR_DISTR` | `COLOR_DISTRIBUTION` | main_plugin.py:3621 | Distribution cable color |
| `COLOR_RAZV` | `COLOR_DROP` | main_plugin.py:3622 | Drop cable color |

---

## DATABASE FIELD NAMES

**Note:** These fields already have English aliases in the UI, but internal names are Serbian.
Keep Serbian names for backward compatibility with existing databases, but add constants.

| Serbian Name | English Name | English Alias | Notes |
|-------------|--------------|---------------|-------|
| `naziv` | `name` | "Name" | Generic name field |
| `duzina` | `length` | "Length" | Generic length field |
| `duzina_m` | `length_m` | "Length (m)" | Length in meters |
| `duzina_km` | `length_km` | "Length (km)" | Length in kilometers |
| `tip_trase` | `route_type` | "Route type" | Route type field |
| `podtip` | `subtype` | "Subtype" | Cable subtype |
| `materijal` | `material` | "Material" | Material field |
| `visina` | `height` | "Height (m)" | Height field |
| `kapacitet` | `capacity` | "Capacity" | Capacity field |
| `lokacija` | `location` | "Location" | Location field |
| `vreme` | `time` | "Time" | Time field |
| `naziv_objekta` | `object_name` | "Object Name" | Object name field |
| `zahtev_kapaciteta` | `capacity_required` | "Required capacity" | Capacity requirement |
| `zahtev_rezerve` | `reserve_capacity` | "Reserve capacity" | Reserve requirement |
| `kabl_layer_id` | `cable_layer_id` | "Cable layer ID" | Cable layer ID |
| `kabl_fid` | `cable_fid` | "Cable feature ID" | Cable feature ID |

---

## CONFIG.INI KEYS

### Layer Names & Table Names

| Serbian Key | English Key | Current Value | Suggested Value |
|------------|-------------|---------------|-----------------|
| `okna_layer_name` | `manholes_layer_name` | "OKNA" | "Manholes" |
| `okna_table` | `manholes_table` | "ftth_okna" | "ftth_manholes" |
| `stubovi_layer_name` | `poles_layer_name` | "Stubovi" | "Poles" |
| `stubovi_table` | `poles_table` | "ftth_stubovi" | "ftth_poles" |
| `kablovi_podzemni_layer_name` | `underground_cables_layer_name` | "Kablovi_podzemni" | "Underground_cables" |
| `kablovi_podzemni_table` | `underground_cables_table` | "ftth_kablovi_podzemni" | "ftth_underground_cables" |
| `kablovi_nadzemni_layer_name` | `aerial_cables_layer_name` | "Kablovi_vazdusni" | "Aerial_cables" |
| `kablovi_nadzemni_table` | `aerial_cables_table` | "ftth_kablovi_nadzemni" | "ftth_aerial_cables" |
| `trase_layer_name` | `routes_layer_name` | "Trasa" | "Routes" |
| `trase_table` | `routes_table` | "ftth_trase" | "ftth_routes" |
| `cevi_layer_name` | `ducts_layer_name` | "PE cevi, Prelazne cevi" | "PE_ducts, Transition_ducts" |
| `cevi_table` | `ducts_table` | "ftth_cevi" | "ftth_ducts" |
| `mufovi_layer_name` | `joint_closures_layer_name` | "Nastavci" | "Joint_closures" |
| `mufovi_table` | `joint_closures_table` | "ftth_mufovi" | "ftth_joint_closures" |
| `prekid_vlakna_layer_name` | `fiber_breaks_layer_name` | "Prekid vlakna" | "Fiber_breaks" |
| `prekid_vlakna_table` | `fiber_breaks_table` | "ftth_spojevi" | "ftth_breaks" |
| `rezerve_layer_name` | `slack_layer_name` | "Opticke_rezerve" | "Optical_slack" |
| `rezerve_table` | `slack_table` | "ftth_spojevi" | "ftth_slack" |

---

## INTERNAL VALUE ENUMS

**Note:** These are database values that should remain for backward compatibility.
Map to English in code using constants/enums.

### Route Types
- `"vazdusna"` → `ROUTE_TYPE_AERIAL` → Display: "Aerial"
- `"podzemna"` → `ROUTE_TYPE_UNDERGROUND` → Display: "Underground"
- `"kroz objekat"` → `ROUTE_TYPE_THROUGH_OBJECT` → Display: "Through Object"

### Cable Subtypes
- `"glavni"` → `CABLE_SUBTYPE_BACKBONE` → Display: "Backbone"
- `"distributivni"` → `CABLE_SUBTYPE_DISTRIBUTION` → Display: "Distribution"
- `"razvodni"` → `CABLE_SUBTYPE_DROP` → Display: "Drop"

### Location Types
- `"OKNO"` → `LOCATION_MANHOLE` → Display: "Manhole"
- `"Stub"` → `LOCATION_POLE` → Display: "Pole"
- `"Objekat"` → `LOCATION_OBJECT` → Display: "Object"

### Slack Types
- `"zavrsna"` → `SLACK_TYPE_TERMINAL` → Display: "Terminal"
- `"prolazna"` → `SLACK_TYPE_MIDSPAN` → Display: "Mid-span"

---

## REFACTORING STRATEGY

### Phase 1: Code Identifiers (Classes, Methods, Variables)
1. Create English constant enums for all internal values
2. Rename all classes to English
3. Rename all methods/functions to English
4. Rename all instance variables to English
5. Update all references throughout codebase

### Phase 2: Configuration
1. Add English config keys alongside Serbian keys
2. Update code to read English keys (with fallback to Serbian)
3. Document migration path for existing users

### Phase 3: Database Fields
1. Keep Serbian field names for backward compatibility
2. Add field name constants in English
3. Ensure aliases are properly set for all fields

### Phase 4: Comments & Documentation
1. Translate all Serbian comments to English
2. Update README files
3. Update inline documentation

### Phase 5: Testing
1. Test all functionality with new names
2. Verify backward compatibility with existing projects
3. Test with both Serbian and English config values

---

## BACKWARD COMPATIBILITY NOTES

**CRITICAL:** Many users may have existing FiberQ projects with:
- Serbian layer names in their QGIS projects
- Serbian table names in their databases
- Serbian config.ini files

**Compatibility Strategy:**
1. Support BOTH Serbian and English identifiers in code
2. Check for English names first, fall back to Serbian
3. Provide migration utility/documentation
4. Deprecation warnings for Serbian identifiers (future version)

---

## COMMON SERBIAN-ENGLISH TERMS

| Serbian | English | Context |
|---------|---------|---------|
| trasa/trasiranje | route/routing | Network path |
| kabl/kablovi | cable/cables | Fiber optic cables |
| stub/stubovi | pole/poles | Utility poles |
| okno/okna | manhole/manholes | Underground access |
| cev/cevi | duct/ducts | Conduit/pipe |
| muf/mufovi | joint closure/closures | Splice enclosure |
| rezerva/rezerve | slack/reserve | Optical slack/loop |
| lomna tacka | breakpoint | Route vertex/break |
| rucna | manual | Manual operation |
| polaganje | laying/placement | Installing cables |
| kanalizacija | ducting/infrastructure | Underground infrastructure |
| selekcija | selection | Selection tools |
| crtez/crtezi | drawing/drawings | CAD drawings |
| objekat/objekti | object/objects | Buildings/structures |
| korekcija | correction | Route correction |
| prelazna | transition | Transition element |
| zavrsna | terminal | Terminal/end |
| prolazna | mid-span | Through/passing |
| glavni | backbone | Main cable |
| distributivni | distribution | Distribution cable |
| razvodni | drop | Drop cable |
| vazdusna | aerial | Above ground |
| podzemna | underground | Below ground |

---

*This document serves as the authoritative reference for the FiberQ internationalization refactoring.*
