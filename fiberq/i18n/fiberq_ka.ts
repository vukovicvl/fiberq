<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="ka" sourcelanguage="en">
<context>
    <name>CableLayingUI</name>
    <message>
        <location filename="../ui/cable_ui.py" line="33"/>
        <source>Cable laying</source>
        <extracomment>Title of the top-level cable menu, and the label/tooltip/status tip of the toolbar button that opens it. Gerund: the ACT of laying (installing) optical cable on the map. This same string is reused 4x in this file - one translation must fit both a menu title and a compact toolbar button label.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/cable_ui.py" line="40"/>
        <source>Underground</source>
        <extracomment>Submenu title under &quot;Cable laying&quot;. Adjective: cable laid below ground in ducts or trenches. Pairs with &quot;Aerial&quot;. Groups the Backbone/Distribution/Drop entries into their underground variants.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/cable_ui.py" line="77"/>
        <location filename="../ui/cable_ui.py" line="46"/>
        <source>Backbone</source>
        <extracomment>Cable class (noun). The transport/feeder cable carrying traffic between the main network nodes. Menu entry appearing under BOTH the &quot;Underground&quot; and the &quot;Aerial&quot; submenu, so one translation serves both parents.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/cable_ui.py" line="85"/>
        <location filename="../ui/cable_ui.py" line="54"/>
        <source>Distribution</source>
        <extracomment>Cable class (noun, used attributively: &quot;distribution cable&quot;). The mid-level cable running from a backbone node out to the street distribution points. Menu entry appearing under BOTH &quot;Underground&quot; and &quot;Aerial&quot; - one translation serves both parents.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/cable_ui.py" line="93"/>
        <location filename="../ui/cable_ui.py" line="63"/>
        <source>Drop</source>
        <extracomment>Cable class. &quot;Drop&quot; is a NOUN here (drop cable / subscriber cable) - the final span from the street distribution point to a single subscriber&apos;s premises. NOT the verb &quot;to drop&quot;. Menu entry appearing under BOTH &quot;Underground&quot; and &quot;Aerial&quot; - one translation serves both parents.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/cable_ui.py" line="71"/>
        <source>Aerial</source>
        <extracomment>Submenu title under &quot;Cable laying&quot;. Adjective: cable strung overhead on poles. Pairs with &quot;Underground&quot;. Groups the Backbone/Distribution/Drop entries into their aerial variants.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DrawingsUI</name>
    <message>
        <location filename="../ui/drawings_ui.py" line="92"/>
        <location filename="../ui/drawings_ui.py" line="86"/>
        <location filename="../ui/drawings_ui.py" line="77"/>
        <location filename="../ui/drawings_ui.py" line="35"/>
        <source>Drawings</source>
        <extracomment>Menu title, toolbar button label, tooltip and status tip - the SAME string is reused 4x here, so one translation must serve all four. Plural noun: external CAD files (DWG/DXF) LINKED to map elements, i.e. documents, not something you draw in QGIS. Distinct from the &quot;Drawing object&quot; button, which digitises a building outline. Keep short for a toolbar button.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/drawings_ui.py" line="42"/>
        <source>Add drawing…</source>
        <extracomment>Menu entry, imperative. Attaches an existing CAD file to the selected element(s). The trailing character is a real ellipsis (U+2026), Qt&apos;s convention for &quot;opens a dialog&quot; - please keep it.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/drawings_ui.py" line="46"/>
        <source>Link a DWG/DXF drawing to selected element(s)</source>
        <extracomment>Tooltip for the entry above. DWG and DXF are AutoCAD file formats - keep both as-is. &quot;element(s)&quot; is written with an optional plural in brackets; use whatever plural form reads naturally in your language.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/drawings_ui.py" line="54"/>
        <source>Open drawing (by click)</source>
        <extracomment>Menu entry, imperative. Opens the CAD file attached to an element in the system&apos;s default application. &quot;(by click)&quot; tells the user the element is chosen by clicking it on the map afterwards.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/drawings_ui.py" line="56"/>
        <source>Click on an element to open its linked drawing</source>
        <extracomment>Tooltip for the entry above; a full sentence instructing the user.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/drawings_ui.py" line="64"/>
        <source>Clear drawing from element</source>
        <extracomment>Menu entry, imperative. Removes the LINK between the element and its CAD file. The file on disk is not deleted and the element is not deleted - only the attachment is dropped. &quot;Clear ... from&quot; = unlink, see tooltip.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/drawings_ui.py" line="66"/>
        <source>Unlink drawing from selected element(s)</source>
        <extracomment>Tooltip for the entry above. &quot;Unlink&quot; confirms nothing is deleted.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>DuctingUI</name>
    <message>
        <location filename="../ui/ducting_ui.py" line="50"/>
        <source>Placing manholes</source>
        <extracomment>Menu entry, gerund (the ACT of placing), plural. Opens a multi-step workflow: pick manhole type, fill in its data, then click on the map to place them one after another. &quot;manhole&quot; = the underground inspection chamber on a duct run (fr: chambre de tirage, never trou d&apos;homme).</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/ducting_ui.py" line="61"/>
        <source>Place PE pipe</source>
        <extracomment>Menu entry, imperative. PE = polyethylene. This is the ordinary buried distribution duct (Ø 40 mm), placed between two points on the route; the dialog then offers capacities 1x1 to 3x3, i.e. how many ducts form the duct bank. NB the rest of the app calls this a &quot;duct&quot;, not a &quot;pipe&quot; - same object; translate both with your single word for duct (fr: fourreau).</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/ducting_ui.py" line="74"/>
        <source>Place transition pipe</source>
        <extracomment>Menu entry, imperative. &quot;Transition&quot; translates the legacy term &quot;prelaz&quot; = a CROSSING. This is the large protective casing (O 110 mm, in PVC / PE / Oki / galvanised steel) laid where the route crosses under a road, railway or watercourse; the smaller PE ducts are pulled through it. Not a fitting or an adapter between two pipe sizes.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/ducting_ui.py" line="95"/>
        <location filename="../ui/ducting_ui.py" line="91"/>
        <location filename="../ui/ducting_ui.py" line="84"/>
        <source>Ducting</source>
        <extracomment>Toolbar drop-down button label, tooltip and status tip - the SAME string is reused 3x here, so one translation must serve all three. Noun: the whole duct infrastructure (manholes + ducts). Keep it short for a toolbar button.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ElementNames</name>
    <message>
        <location filename="../models/element_defs.py" line="120"/>
        <source>ODF</source>
        <extracomment>Element type (acronym), shown in the &quot;Placing elements&quot; menu. Optical Distribution Frame: the passive frame at the head end where feeder fibres terminate. Most languages keep the acronym &quot;ODF&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="131"/>
        <source>TB</source>
        <extracomment>Element type (acronym) = &quot;Terminal Box&quot;. The Serbian backend name is &quot;ZOK&quot; (Zavrsna opticka kutija). Keep the acronym &quot;TB&quot; unless your language has an established equivalent acronym.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="143"/>
        <source>Patch panel</source>
        <extracomment>Element type (noun phrase, not an acronym): the rack panel holding patch connections. Its scope overlaps ODF above -- CONTRIBUTING.md leaves fr &quot;tiroir optique&quot; vs &quot;panneau de brassage&quot; open; keep the two element types clearly distinct in your language.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="155"/>
        <source>OTB</source>
        <extracomment>Element type (acronym) = &quot;Optical Termination Box&quot;. (The Serbian backend name &quot;OD ormar&quot; is legacy wording and does not redefine the term.) Keep the acronym &quot;OTB&quot; unless your language has an established equivalent acronym.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="165"/>
        <source>Indoor OTB</source>
        <extracomment>Element type. &quot;Indoor&quot; is an ADJECTIVE qualifying OTB: an OTB mounted inside a building. Serbian catalogue: &quot;Unutrašnji OD ormar&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="176"/>
        <source>Outdoor OTB</source>
        <extracomment>Element type. &quot;Outdoor&quot; is an ADJECTIVE qualifying OTB: an OTB mounted outside, typically on a wall or facade. Serbian catalogue: &quot;Spoljašnji OD ormar&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="187"/>
        <source>Pole OTB</source>
        <extracomment>Element type. &quot;Pole&quot; is an ADJECTIVE here: an OTB mounted ON a pole. It is one element, not a pole plus an OTB. Serbian catalogue: &quot;OD ormar na stubu&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="200"/>
        <source>TO</source>
        <extracomment>Element type (acronym) = &quot;Termination Outlet&quot;: the subscriber-side optical outlet, the last element before the customer&apos;s equipment. WARNING: this is NOT the English preposition &quot;to&quot; -- the from/to direction words are a separate string. Keep the acronym &quot;TO&quot; unless your language has an established equivalent acronym.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="210"/>
        <source>Indoor TO</source>
        <extracomment>Element type. &quot;Indoor&quot; is an ADJECTIVE qualifying TO: a TO mounted inside a building. Serbian catalogue: &quot;Unutrašnji TO Izvod&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="220"/>
        <source>Outdoor TO</source>
        <extracomment>Element type. &quot;Outdoor&quot; is an ADJECTIVE qualifying TO: a TO mounted outside. Serbian catalogue: &quot;Spoljašnji TO Izvod&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="230"/>
        <source>Pole TO</source>
        <extracomment>Element type. &quot;Pole&quot; is an ADJECTIVE: a TO mounted ON a pole. Serbian catalogue: &quot;TO Izvod na stubu&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../models/element_defs.py" line="241"/>
        <source>Joint Closure TO</source>
        <extracomment>Element type: a TO housed INSIDE a joint (splice) closure. Serbian catalogue: &quot;TO Izvod u nastavku&quot; = &quot;TO outlet in the joint closure&quot;. &quot;Joint Closure&quot; qualifies &quot;TO&quot; -- one element, not two.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ElementPlacementUI</name>
    <message>
        <location filename="../ui/elements_ui.py" line="39"/>
        <source>Place Joint Closure</source>
        <extracomment>Menu entry: starts the tool that places one joint closure (splice closure, fr &quot;BPE&quot;, sr &quot;nastavak&quot;) on the map. &quot;Place&quot; is a VERB in the imperative; &quot;Joint Closure&quot; is a singular noun phrase.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/elements_ui.py" line="71"/>
        <source>Place {name}</source>
        <extracomment>Menu entry: places one network element of the given type on the map. &quot;Place&quot; is a VERB in the imperative. {name} is the element type (ODF, Indoor OTB, Pole TO, ...), translated separately -- keep the {name} placeholder exactly as it is and do not translate it here. Gendered languages: the article cannot be agreed at runtime, since one label serves every element (fr &quot;une chambre&quot; vs &quot;un poteau&quot;), so prefer an article-free construction such as &quot;Placer : {name}&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/elements_ui.py" line="87"/>
        <source>Placing elements</source>
        <extracomment>Toolbar button label, reused as its tooltip and status-bar tip, so the translation must also work as a compact button caption. GERUND -- the activity of placing network elements, naming the whole drop-down group; not an imperative command. &quot;elements&quot; here means the passive optical devices (ODF, OTB, TO, ...), not map features in general.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQ</name>
    <message>
        <location filename="../main_plugin.py" line="4491"/>
        <source>FiberQ – Preview Map</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="4492"/>
        <source>Error opening the preview map:
{details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/quick_toolbar.py" line="45"/>
        <source>Place Pole</source>
        <extracomment>Quick-toolbar button label, imperative. Places one pole (the support that carries aerial cable). NOTE: this is the SAME command as the main toolbar&apos;s &quot;Add pole&quot; (Routing menu) - only the English wording differs. Please use one consistent term for the pole in both.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/quick_toolbar.py" line="56"/>
        <source>Place Manhole</source>
        <extracomment>Quick-toolbar button label, imperative, singular. Same command as the Ducting menu&apos;s &quot;Placing manholes&quot; - only the wording differs. &quot;manhole&quot; = the underground inspection chamber on a duct run (fr: chambre de tirage).</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/quick_toolbar.py" line="67"/>
        <source>Create Route</source>
        <extracomment>Quick-toolbar button label, imperative. &quot;Route&quot; = the physical path on the ground that cables follow (fr: tracé). Same command as the Routing menu&apos;s &quot;Create route&quot; - only the capitalisation differs, so keep one wording.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/quick_toolbar.py" line="79"/>
        <source>Aerial Cable</source>
        <extracomment>Quick-toolbar button label. Noun phrase, &quot;Aerial&quot; = strung overhead on poles (as opposed to buried). Shortcut for laying specifically a BACKBONE /feeder aerial cable - the subtype is fixed to &quot;main&quot; in code even though the label does not say so. The Cable menu offers the full choice.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/quick_toolbar.py" line="90"/>
        <source>Underground Cable</source>
        <extracomment>Quick-toolbar button label. Noun phrase, &quot;Underground&quot; = laid in ducts or a trench below ground; pairs with &quot;Aerial Cable&quot; above. Also fixed to the BACKBONE/feeder subtype in code, though the label does not say so.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/quick_toolbar.py" line="101"/>
        <source>Place ODF</source>
        <extracomment>Quick-toolbar button label, imperative. ODF = Optical Distribution Frame, the passive frame at the head end where feeder fibres terminate. Translate only &quot;Place&quot;; keep the acronym &quot;ODF&quot; - it doubles as the layer name.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/quick_toolbar.py" line="113"/>
        <source>Place OTB</source>
        <extracomment>Quick-toolbar button label, imperative. OTB = &quot;Optical Termination Box&quot;. Translate only &quot;Place&quot; and keep the acronym &quot;OTB&quot; unless your language has an established equivalent acronym.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/quick_toolbar.py" line="126"/>
        <source>Place TO</source>
        <extracomment>Quick-toolbar button label, imperative. WARNING: &quot;TO&quot; is an ACRONYM = &quot;Termination Outlet&quot; (the subscriber-side optical outlet), NOT the English preposition &quot;to&quot; - do not read this as &quot;place ... to ...&quot;. Translate only &quot;Place&quot; and keep the acronym &quot;TO&quot; unless your language has an equivalent.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/quick_toolbar.py" line="139"/>
        <source>Optical Slack</source>
        <extracomment>Quick-toolbar button label, noun phrase (singular). &quot;Slack&quot; = the spare length of cable coiled at a point for later re-splicing. This button places a TERMINAL slack by default. The Slack menu labels the same group &quot;Optical slacks&quot; (plural) - keep the two consistent.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/quick_toolbar.py" line="152"/>
        <source>Undo (FiberQ)</source>
        <extracomment>Quick-toolbar button label, imperative verb. Undoes the last FiberQ action. The &quot;(FiberQ)&quot; qualifier distinguishes it from QGIS&apos;s own Undo, which is a separate history - keep the product name as-is and keep the brackets.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQBOM</name>
    <message>
        <location filename="../dialogs/bom_dialog.py" line="45"/>
        <source>BOM export</source>
        <extracomment>WP4 4.2 item R4. The BOM&apos;s user-facing strings, in the FiberQBOM context.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../dialogs/bom_dialog.py" line="46"/>
        <source>Could not write the bill of materials to {path}. Reason: {reason}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../dialogs/bom_dialog.py" line="48"/>
        <source>Could not write the bill of materials to {path}, and the half-written file has been removed so it cannot be mistaken for a finished export. Reason: {reason}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../dialogs/bom_dialog.py" line="52"/>
        <source>Bill of materials exported:
{path}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../dialogs/bom_dialog.py" line="53"/>
        <source>Excel export needs the xlsxwriter module, which is not installed, so the bill of materials was saved as CSV instead:
{path}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../dialogs/bom_dialog.py" line="57"/>
        <source>Features whose length could not be measured (counted, not included): {count}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../dialogs/bom_dialog.py" line="59"/>
        <source>Slack values that could not be read (not included in the totals): {count}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../dialogs/bom_dialog.py" line="61"/>
        <source>Layers left out of this report entirely: {names}</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQBreak</name>
    <message>
        <location filename="../addons/fiber_break.py" line="31"/>
        <source>Fiber break</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../addons/fiber_break.py" line="365"/>
        <source>there is no fibre break layer to write to</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../addons/fiber_break.py" line="375"/>
        <source>&apos;{layer}&apos; has no cable reference columns, so the break was not recorded</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../addons/fiber_break.py" line="410"/>
        <source>the break point was rejected by the layer</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQCables</name>
    <message>
        <location filename="../core/cable_manager.py" line="53"/>
        <source>Lay cable</source>
        <extracomment>WP4 4.2 item R8. The cable-laying strings, in the FiberQCables context.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/cable_manager.py" line="54"/>
        <source>Cable has been laid along the route!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/cable_manager.py" line="55"/>
        <source>The cable layer was already in edit mode, so this cable is not saved yet. Use Layer &gt; Save Layer Edits when you are ready.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/cable_manager.py" line="59"/>
        <source>the cable layer refused the new cable, so nothing was laid</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/cable_manager.py" line="61"/>
        <source>the cable layer could not be opened for editing, so nothing was laid</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/cable_manager.py" line="63"/>
        <source>the cable layer has no {columns} column, so this cable was laid without its length recorded</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQDrawings</name>
    <message>
        <location filename="../core/drawing_manager.py" line="333"/>
        <source>DWG/DXF drawings</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/drawing_manager.py" line="335"/>
        <source>All files</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQErrors</name>
    <message>
        <location filename="../utils/errors.py" line="175"/>
        <source>{problem} (+{count} more). See Log Messages &gt; FiberQ for the details.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../utils/errors.py" line="181"/>
        <source>{problem}. See Log Messages &gt; FiberQ for the details.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../utils/errors.py" line="257"/>
        <source>the layer was not in edit mode</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../utils/errors.py" line="276"/>
        <source>QGIS refused the commit without saying why</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQExport</name>
    <message>
        <location filename="../core/export_manager.py" line="53"/>
        <source>Successfully exported the selected features of layer &apos;{layer}&apos;
to:
{path}</source>
        <extracomment>WP4 4.2 item R3. These two sentences come from the duplicate export this branch deleted (main_plugin._export_active_layer), where WP1 had put them -- and where nothing could reach them, because that copy only ran when this one raised. The live path had the fragment-assembled form WP1 replaced:     scope_txt = &quot;selected features&quot; if only_selected else &quot;all features&quot;     f&quot;Successfully exported {scope_txt} from layer &apos;{...}&apos;&quot; which is untranslatable into French: &quot;de&quot; + &quot;les&quot; contracts to the mandatory &quot;des&quot;, and no runtime substitution into a fixed &quot;de {scope}&quot; can produce it. So WP1&apos;s delivered fix sat in unreachable code while the bug it fixed was what users saw. Moving them here is what makes WP1 reachable. Keep each as ONE whole sentence; do not reassemble them from fragments. Only the layer name and the path are placeholders. Confirmation shown after exporting ONLY the features the user had selected.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/export_manager.py" line="57"/>
        <source>Successfully exported all features of layer &apos;{layer}&apos;
to:
{path}</source>
        <extracomment>Confirmation shown after exporting the WHOLE layer (no selection filter).</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQImages</name>
    <message>
        <location filename="../utils/image_watcher.py" line="53"/>
        <source>Open image</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQInterchange</name>
    <message>
        <location filename="../core/interchange_bundle.py" line="539"/>
        <source>Not exported, because their coordinates cannot be converted to EPSG:4326: {layers}. Each has no valid CRS, or one with no transformation to EPSG:4326. Set the CRS their coordinates are in (Layer Properties &gt; Source), then export again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="603"/>
        <source>Nothing was exported: the layers {layers} would all be written as the bundle table &apos;{table}&apos;, which holds one layer. Merge their features into one layer, or remove or rename all but one of them, then export again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="669"/>
        <source>temporary scratch layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1373"/>
        <source>{count} kept row(s) of {table} could not be written back: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1511"/>
        <source>Nothing was exported: no FiberQ layer in this project has coordinates that convert to EPSG:4326.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1520"/>
        <source>Not exported, because QGIS cannot open their data: {layers}. Their tables in an existing bundle are kept as they were.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1594"/>
        <source>These columns have the name of a column FiberQ writes, so their values are in fq_extra_json under their own names: {columns}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1602"/>
        <source>{count} key(s) of a feature&apos;s own fq_extra_json were replaced by the column of the same name, whose value the bundle now carries under that key.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1610"/>
        <source>{count} feature(s) have a column that belongs in fq_extra_json, but their fq_extra_json is not a JSON object, so that column&apos;s values were not written.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1657"/>
        <source>The project&apos;s {entry} could not be read, so none were exported; what FiberQ wrote for them in an existing bundle is kept.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1851"/>
        <source>Nothing was exported: this project was saved in QGIS 4, and QGIS 3 cannot read its relations, pass-through elements or what an import kept for other tools. Written over the existing bundle, that would remove them from it. Export from QGIS 4, or to a new file.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1859"/>
        <source>This project was saved in QGIS 4, and QGIS 3 cannot read its relations, pass-through elements or what an import kept for other tools, so this bundle has none of them. Export from QGIS 4 for a complete bundle.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1872"/>
        <source>Removed from the bundle: {names}. FiberQ wrote them there last time, and this export has no layer for them.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1877"/>
        <source>Removed from the folder: {names}. FiberQ wrote them there last time, and this export has no layer for them.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1885"/>
        <source>Could not remove what FiberQ wrote last time for a layer this export does not have: {names}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_bundle.py" line="1910"/>
        <source>The folder&apos;s _fiberq_metadata.json could not be read ({reason}), so it was replaced, and any keys another tool kept in it are lost.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="269"/>
        <source>{count} table(s) of the bundle could not be opened by name and were not imported: {names}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="682"/>
        <source>{count} feature(s) carried an fq_extra_json that is not a JSON object; it was not imported, because it holds no attributes to keep.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="693"/>
        <source>{count} feature(s) have no fiberq_uuid, so FiberQ cannot recognise them: importing this bundle again adds them again. The attributes FiberQ has no column for on {extras} of them could not be kept, since they are kept against a feature&apos;s identity.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="703"/>
        <source>{count} feature(s) have no fiberq_uuid, so FiberQ cannot recognise them: importing this bundle again adds them again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="829"/>
        <source>{count} {layer} row(s) in the bundle carry no cable_uuid column, so they were imported without being attached to a cable.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="850"/>
        <source>&apos;{layer}&apos; has no cable reference columns, so the imported {kind} loops were left unattached to a cable; their cable_uuid is kept and written out again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="879"/>
        <source>{count} {layer} reference(s) name a cable that is not in this project; they were left empty rather than pointed at another cable, and are kept and written out again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="964"/>
        <source>{count} relation member row(s) name no relation in the bundle, so they were not imported.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="1061"/>
        <source>{count} relation(s) already in this project were left as they are; the bundle&apos;s version of them has other members.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="1068"/>
        <source>{count} relation member(s) name a feature FiberQ does not draw; they are kept and written out again with the next bundle.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="1143"/>
        <source>{count} cable(s) already had pass-through elements in this project; the bundle&apos;s for them were not used.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="1152"/>
        <source>{count} path stop(s) name a cable or element FiberQ does not draw; they are kept and written out again with the next bundle.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="1180"/>
        <source>The bundle&apos;s own tables could not be listed: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="1208"/>
        <source>The bundle&apos;s table {table} could not be read, so it is not kept: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="1258"/>
        <source>The bundle&apos;s table &apos;{table}&apos; has a name FiberQ cannot carry safely, so it is not in the next bundle.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="1296"/>
        <source>{count} row(s) of {table} in this bundle have the key of a row an earlier import kept, with other values; the earlier row is kept.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/interchange_import.py" line="1340"/>
        <source>This bundle&apos;s colour standard, {new}, replaces {old}, which an earlier import brought; the next bundle says {new}.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQLayers</name>
    <message>
        <location filename="../core/layer_manager.py" line="39"/>
        <source>could not read which column is {name}&apos;s primary key, so fid/id/gid was assumed. If its key is called something else, moving this element may fail</source>
        <extracomment>WP4 4.2 item R7. _copy_attributes_between_layers&apos; user-facing strings. The context must be a literal at every call site -- pylupdate6 reads the literal argument and can extract neither a constant nor a variable.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/layer_manager.py" line="43"/>
        <source>could not tell what kind of layer {name} is, so no column will be added to it. Any value whose column is missing there will be left empty</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/layer_manager.py" line="47"/>
        <source>could not add the column(s) {columns} to {name}, so those values will be left empty on the moved element</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/layer_manager.py" line="51"/>
        <source>could not read {column} from the element being moved, so it was left empty</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/layer_manager.py" line="53"/>
        <source>Change element type</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQPlugin</name>
    <message>
        <location filename="../main_plugin.py" line="382"/>
        <source>Validation could not run: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="499"/>
        <location filename="../main_plugin.py" line="392"/>
        <source>Some of this project&apos;s validation settings could not be used, and the defaults stood in for them: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="418"/>
        <source>Validation found no issues ({rules} rules, {layers} layers).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="467"/>
        <source>Could not save the report: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="472"/>
        <source>Saved {format} report to {path}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="494"/>
        <source>Could not check lengths: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="507"/>
        <source>Skipped {layers}: lengths cannot be measured without an ellipsoid. Set one in Project Properties &gt; General.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="515"/>
        <source>Could not check {layers}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="544"/>
        <source>Largest change: {field} {old} -&gt; {new} on {layer}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="570"/>
        <source>{layers} left unchanged: save or discard the open edits there, then run this again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="578"/>
        <source>Some layers could not be updated: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="647"/>
        <source>Could not write the bundle: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="662"/>
        <source>Bundle export failed: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="667"/>
        <source>Wrote {path} — {summary}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="691"/>
        <source>The folder {name} already exists. Write the bundle into it?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="703"/>
        <source>Replace the bundle {name}?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="759"/>
        <source>Could not read the bundle: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="767"/>
        <source>Import failed: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="777"/>
        <source>Carried through unchanged, with no FiberQ layer to draw them in: {kinds}. They survive the next export.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="784"/>
        <source>Imported {path} — {summary}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1089"/>
        <source>{columns} could not be written to the moved element, so those values are lost</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3240"/>
        <location filename="../main_plugin.py" line="1125"/>
        <source>this layer could not be opened for editing</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1141"/>
        <location filename="../main_plugin.py" line="1128"/>
        <source>the element was copied but the original could not be removed, so it is now in both layers</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2759"/>
        <source>This project was saved in QGIS 4. Its FiberQ settings -- relations, colour catalogues, pass-through elements, picture and drawing links, the auto-save path, validation settings, and what an interchange import kept for other tools -- cannot be read in QGIS 3. Do not save it here: that removes them permanently.</source>
        <extracomment>Shown once when a project saved in QGIS 4 is opened in QGIS 3. The settings cannot be read here, and saving would remove them for good.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3180"/>
        <source>&apos;{layer}&apos; has no cable reference columns, so no cable total was updated</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3249"/>
        <source>the layer refused to delete one of the features</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3522"/>
        <source>the new layer would not take its &apos;naziv&apos; field</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3563"/>
        <source>the layer would not take its &apos;tip&apos; field</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3583"/>
        <source>{count} point(s) in the file could not be placed and were skipped.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3673"/>
        <source>a point was rejected by the layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3870"/>
        <source>{count} pole or manhole(s) have no position yet and were not checked.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3983"/>
        <source>the end of this route could not be moved</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="4020"/>
        <source>The nearest pole is {distance} map units away and already sits where this route&apos;s next vertex is, so attaching the route to it would collapse the route to nothing. The route was left alone.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="4047"/>
        <source>the route would not take its new shape</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1545"/>
        <location filename="../main_plugin.py" line="1529"/>
        <location filename="../main_plugin.py" line="247"/>
        <location filename="../main_plugin.py" line="230"/>
        <source>Interface language</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="248"/>
        <source>Language set to {language}.

Language will change when QGIS restarts.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="264"/>
        <source>BOM report</source>
        <extracomment>Error-dialog title. &quot;BOM&quot; = Bill of Materials (costed list of materials for the design), NOT the Unicode byte-order mark.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="4287"/>
        <location filename="../main_plugin.py" line="2695"/>
        <location filename="../main_plugin.py" line="2576"/>
        <location filename="../main_plugin.py" line="2550"/>
        <location filename="../main_plugin.py" line="2532"/>
        <location filename="../main_plugin.py" line="2441"/>
        <location filename="../main_plugin.py" line="1302"/>
        <location filename="../main_plugin.py" line="1158"/>
        <location filename="../main_plugin.py" line="1037"/>
        <location filename="../main_plugin.py" line="265"/>
        <source>Error: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="277"/>
        <source>Locator</source>
        <extracomment>Title of an error box. FiberQ&apos;s OWN address-finder dialog (the &quot;Locator&quot; toolbar button), NOT the QGIS &quot;Locator&quot; search bar - do not reuse the QGIS translation. Sense: address finder.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="278"/>
        <source>Error opening locator: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="401"/>
        <source>%n error(s)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="402"/>
        <source>%n warning(s)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="403"/>
        <source>%n info</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="412"/>
        <source>%n rule(s) failed to run; the rules that did found no issues</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="441"/>
        <source>Run a validation before exporting a report.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="450"/>
        <source>Export validation report</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="524"/>
        <source>No lengths were checked. See the warnings above.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="527"/>
        <source>No FiberQ layers with stored lengths in this project.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="530"/>
        <source>All stored lengths already match the geometry.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="535"/>
        <source>%n feature(s) will have their stored length rewritten from the drawn geometry.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="552"/>
        <source>Recalculate lengths</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="553"/>
        <source>Recalculate stored lengths?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="555"/>
        <source>Lengths are measured on the project ellipsoid, the same way the QGIS measure tool does. Slack values are read but never changed.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="567"/>
        <source>Recalculated lengths on %n feature(s).</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="751"/>
        <location filename="../main_plugin.py" line="608"/>
        <source>GeoPackage bundle</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="610"/>
        <source>GeoJSON bundle — a folder, no relations</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="621"/>
        <source>Export FiberQ interchange bundle</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="693"/>
        <source>The GeoJSON files of the element types this export writes are replaced, whoever wrote them, and one FiberQ wrote there before for an element type the project no longer has is removed. _fiberq_metadata.json is rewritten, keeping the keys other tools stored in it. Other files in the folder are left alone.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="705"/>
        <source>Its FiberQ layers, and the members and pass-through elements of FiberQ&apos;s own relations and cables, are rewritten from this project -- import the file first to keep what another tool added to them -- and what FiberQ wrote there for a layer, relation or cable the project no longer has is removed. Everything else another tool stored in the file -- its own metadata keys, tables and rows -- is kept.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="715"/>
        <source>Export interchange bundle</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="749"/>
        <source>Import FiberQ interchange bundle</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="801"/>
        <source>This issue is not tied to a map location.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1638"/>
        <location filename="../main_plugin.py" line="1036"/>
        <source>Publish to PostGIS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2237"/>
        <location filename="../main_plugin.py" line="1157"/>
        <location filename="../main_plugin.py" line="1065"/>
        <source>Change element type</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="4200"/>
        <location filename="../main_plugin.py" line="1256"/>
        <location filename="../main_plugin.py" line="1203"/>
        <source>Select one or more elements and try again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1210"/>
        <source>Choose image</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1212"/>
        <source>Images</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3421"/>
        <location filename="../main_plugin.py" line="1213"/>
        <source>All files</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="1225"/>
        <source>Image linked to %n element(s).</source>
        <extracomment>Confirmation after attaching one photo to the selected map elements. %n is how many elements now point at that image; Qt substitutes it, so keep %n and do not turn it into {count}.</extracomment>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1242"/>
        <source>Image</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1243"/>
        <source>Click on an element to open its image (ESC to exit).</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="1264"/>
        <source>Image link removed for %n element(s).</source>
        <extracomment>Confirmation after detaching the photo from the selected map elements. Only the link is cleared - the image file itself is not deleted. %n is how many elements were unlinked; keep %n.</extracomment>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1290"/>
        <source>Cutting</source>
        <extracomment>Message-bar heading for the geometry-splitting tool. &quot;Cutting&quot; = the act of splitting a line feature in two, NOT a cable fault/outage. Verbal noun; keep it short (banner title). The body text below belongs to the same tool.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1291"/>
        <source>Tool activated. Move mouse over line (red cross), left click to cut, right/ESC exit.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1301"/>
        <source>Infrastructure cutting</source>
        <extracomment>Error-dialog title for the geometry-splitting tool. &quot;cutting&quot; = splitting a line feature at a clicked point, NOT a cable fault. Same tool as the &quot;Cut infrastructure&quot; button.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1355"/>
        <source>{name} – About</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1402"/>
        <source>About dialog error: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1571"/>
        <source>Undo (FiberQ)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1573"/>
        <source>Undo last FiberQ action (Ctrl+Shift+Z)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1581"/>
        <source>Redo (FiberQ)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1583"/>
        <source>Redo last undone FiberQ action (Ctrl+Shift+Y)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1606"/>
        <source>Help / About</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1607"/>
        <source>Help and information about FiberQ</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1644"/>
        <source>Publish the active (or selected) layer to PostGIS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1686"/>
        <source>Terminal slack (shortcut)</source>
        <extracomment>Label of a HIDDEN action that only exists to bind the &quot;R&quot; key; it shows up in the QGIS keyboard-shortcuts list, not on a toolbar. &quot;Slack&quot; = spare cable length coiled at a point for later re-splicing (fr &quot;love&quot;/&quot;reserve&quot;); TERMINAL slack is the type that sits at a cable END - keep it distinct from &quot;mid span&quot; slack. &quot;(shortcut)&quot; refers to the key binding, not to a Windows shortcut file.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1697"/>
        <source>Optical schematic view</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3617"/>
        <location filename="../main_plugin.py" line="3587"/>
        <location filename="../main_plugin.py" line="3577"/>
        <location filename="../main_plugin.py" line="3559"/>
        <location filename="../main_plugin.py" line="3521"/>
        <location filename="../main_plugin.py" line="3457"/>
        <location filename="../main_plugin.py" line="1704"/>
        <source>Import points</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3712"/>
        <location filename="../main_plugin.py" line="3700"/>
        <location filename="../main_plugin.py" line="1715"/>
        <source>Export</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1720"/>
        <source>Export selected...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1724"/>
        <source>Export selected features of the active layer to GPX / KML / KMZ / GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1734"/>
        <source>Export all...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1738"/>
        <source>Export all features of the active layer to GPX / KML / KMZ / GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1750"/>
        <source>Export active layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1770"/>
        <source>Hide locator</source>
        <extracomment>Toolbar button that removes the address marker the Locator dropped on the map. &quot;Hide&quot; is a VERB (imperative); &quot;locator&quot; is the same address-finder feature as the &quot;Locator&quot; button above.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1782"/>
        <source>Relations</source>
        <extracomment>Toolbar button opening &quot;Optical relations management&quot;. A FiberQ &quot;relation&quot; is a named end-to-end optical link (a logical route between two sites) that cables get assigned to - telecom domain sense, plural NOUN. NOT QGIS layer relations (foreign keys between tables), and not &quot;relationship&quot; in the general sense.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1793"/>
        <source>List of latent elements</source>
        <extracomment>Toolbar button opening a table of &quot;latent&quot; elements. In FiberQ a latent element is a passive optical element (joint closure, ODF, OTB, termination box) that sits ON a cable&apos;s path at a recorded distance along it, between the cable&apos;s two endpoints - recorded as data, not drawn as a separate map feature. &quot;latent&quot; = intermediate/pass-through, NOT &quot;faulty&quot;, &quot;hidden bug&quot; or &quot;dormant&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1816"/>
        <source>Cut infrastructure</source>
        <extracomment>Toolbar button. &quot;Cut&quot; is a VERB, imperative, in the GEOMETRY -EDITING sense: the tool splits one line feature into two at the point you click (see addons/infrastructure_cut.py, _split_feature_at_point). It is NOT a cable fault/break - French &quot;decouper&quot;/&quot;scinder&quot;, never &quot;coupure&quot;. The separate fault tool is &quot;Fiber break&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1857"/>
        <source>Fiber break</source>
        <extracomment>Toolbar button. NOUN: a fault - the point where a fibre is broken or severed (fr &quot;coupure&quot;/&quot;rupture&quot;). This IS the fault concept, unlike &quot;Cut infrastructure&quot; above, which is geometry editing. The tool marks a break location on the map. &quot;break&quot; is not a pause and not a rest.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1871"/>
        <source>Color catalog</source>
        <extracomment>Toolbar entry opening the FIBRE COLOUR CODE: the standard sequence of colours identifying each tube and each fibre within a cable (e.g. the TIA-598 or IEC ordering). This is industry cable terminology - it is NOT a QGIS symbology palette or a map-styling colour picker.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1882"/>
        <source>Save all layers to GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1883"/>
        <source>Export all vector layers (including Temporary scratch) to a single .gpkg and redirect the project to it</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1903"/>
        <source>Auto save to GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1905"/>
        <source>When enabled: every new or memory layer is automatically written to the selected .gpkg and redirected to it</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1933"/>
        <source>Preview Map</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1934"/>
        <source>Open the FiberQ Preview Map (PostGIS connection from config.ini)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1948"/>
        <source>Create Service Area</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1949"/>
        <source>Create Service Area from selection (buffer around selected cables/elements)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1964"/>
        <source>Draw Service Area Manually</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1965"/>
        <source>Manual Service Area drawing (like Google Earth) and entry into Service Area layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1991"/>
        <source>Branch info</source>
        <extracomment>Toolbar button. &quot;Branch&quot; is a NOUN in the cable-network sense - a branching/junction point where cables split off (French &quot;derivation&quot;). Click a cable to see how many cables, of which types and capacities, meet at that point. Not a tree branch, not a company branch office, not a version-control branch.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1999"/>
        <source>Click on cable to show number of cables/types/capacities at that point</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2019"/>
        <location filename="../main_plugin.py" line="2016"/>
        <source>Show shortcuts</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2051"/>
        <source>BOM report (XLSX/CSV)</source>
        <extracomment>Toolbar button. &quot;BOM&quot; = Bill of Materials, the costed list of cables/closures/poles a design consumes (fr &quot;nomenclature&quot; / &quot;liste de materiel&quot;). It is NOT the Unicode byte-order mark. XLSX/CSV are file formats and stay untranslated. Expand or keep &quot;BOM&quot; per the convention of your language&apos;s telecom/engineering usage.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2110"/>
        <source>Validate project</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2139"/>
        <source>Recalculate lengths…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2140"/>
        <source>Rewrite stored lengths that disagree with the drawn geometry</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2160"/>
        <source>Export interchange bundle…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2161"/>
        <source>Write the design as an open FiberQ interchange bundle (.gpkg)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2178"/>
        <source>Import interchange bundle…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2179"/>
        <source>Read an open FiberQ interchange bundle into this project</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2215"/>
        <source>Settings</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2238"/>
        <source>Smart selection + change element type (visual style)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2257"/>
        <source>Move elements</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2258"/>
        <source>Move elements on the map (click-move-click)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2262"/>
        <source>Import picture to element</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2266"/>
        <source>Link a .jpg/.png picture to selected element(s)</source>
        <extracomment>Toolbar tooltip. Static text built once at startup, so there is no count to plug in: &quot;(s)&quot; here just means &quot;one or more&quot;. Render it with whatever generic/plural form reads naturally.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2270"/>
        <source>Clear picture from element</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2274"/>
        <source>Unlink picture from selected element(s)</source>
        <extracomment>Toolbar tooltip. &quot;Unlink&quot; = detach the picture reference from the element; the image file on disk is NOT deleted. Static text, so &quot;(s)&quot; just means &quot;one or more&quot; - no count is substituted.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2440"/>
        <source>Placing elements</source>
        <extracomment>Error-dialog title. &quot;Placing elements&quot; is FiberQ&apos;s name for the CATEGORY of passive optical elements you drop on the map (ODF, TB, OTB, TO, patch panel, joint closures) - it is the layer-group label, not the -ing action of placing. Treat as a noun phrase.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2464"/>
        <source>Error activating: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2531"/>
        <location filename="../main_plugin.py" line="2526"/>
        <source>Smart selection</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2527"/>
        <source>Click on the elements to select/deselect them. Selections on other layers are not touched.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2542"/>
        <source>Click on cable to show number of cables/types/capacities at that point (right click or ESC to exit).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2575"/>
        <source>Optical schematic</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2585"/>
        <source>Error opening dialog: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3274"/>
        <location filename="../main_plugin.py" line="3269"/>
        <location filename="../main_plugin.py" line="3206"/>
        <source>Delete</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3270"/>
        <source>No selected features to delete.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3275"/>
        <source>Deleted {count} selected features from all layers.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3341"/>
        <source>Shortcuts</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3403"/>
        <location filename="../main_plugin.py" line="3384"/>
        <source>Lay cable</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3418"/>
        <source>Choose a file with points</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3420"/>
        <source>GIS files</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3429"/>
        <source>Unable to load or invalid file!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3434"/>
        <source>The selected file does not contain points!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3508"/>
        <location filename="../main_plugin.py" line="3504"/>
        <source>Unable to create or find the Poles layer!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3546"/>
        <source>Unable to find the target layer!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3592"/>
        <source>Imported {count} points into layer &apos;{layer}&apos;!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="4043"/>
        <location filename="../main_plugin.py" line="4022"/>
        <location filename="../main_plugin.py" line="3982"/>
        <location filename="../main_plugin.py" line="3874"/>
        <location filename="../main_plugin.py" line="3762"/>
        <location filename="../main_plugin.py" line="3757"/>
        <source>Route correction</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3758"/>
        <source>This project has no Route layer, so nothing was checked.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3763"/>
        <source>This project has no Poles or Manholes layer, so route ends could not be checked.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3883"/>
        <source>No errors found!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3929"/>
        <source>Layer &apos;Poles&apos; not found!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3935"/>
        <source>Route layer &apos;Route&apos; not found!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="4059"/>
        <source>Route has been automatically attached to a pole.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="4221"/>
        <source>Drawing link removed for %n element(s).</source>
        <extracomment>Confirmation after detaching a drawing (a CAD/PDF document attached to an element) from the selected map elements. Only the link is cleared - the drawing file is not deleted. %n is how many elements were actually unlinked; keep %n.</extracomment>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="4282"/>
        <source>Placing manhole</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="4283"/>
        <source>Click on the map to place the manhole (ESC to exit).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="4286"/>
        <source>Manhole</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQRoutes</name>
    <message>
        <location filename="../core/route_manager.py" line="44"/>
        <source>Import route</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="50"/>
        <source>Merge routes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="65"/>
        <source>Route has been created!
Length: {length} m ({km} km)
Type: {type}</source>
        <extracomment>The merge&apos;s user-facing strings. Held as module constants because each one is used twice -- once as the QT_TRANSLATE_NOOP source pylupdate6 extracts, once as safe_format&apos;s fallback if a translator renames a placeholder -- and a literal repeated at both sites is a literal that drifts.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="67"/>
        <source>Merged route</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="68"/>
        <source>{count} of the selected routes had no line to merge and were left alone.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="70"/>
        <source>The routes were not touching. A straight segment {gap} m long was added to join them, so the merged route is longer than the routes it replaces. Undo if that is not what you wanted.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="74"/>
        <source>The Route layer was already in edit mode, so this merge is not saved yet. Use Layer &gt; Save Layer Edits when you are ready.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="78"/>
        <source>{count} of the selected routes had no line in them and could not be merged</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="80"/>
        <source>the Route layer could not be opened for editing, so nothing was changed</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="82"/>
        <source>the layer refused the merged route, so the routes it would have replaced were left alone</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="85"/>
        <source>the merged route was saved, but {count} of the routes it replaces could not be removed. Delete them by hand so the network is not counted twice</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="89"/>
        <source>the Route layer has no {columns} column, so the merged route was saved without it. Its geometry is correct; its length and type are not recorded</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="104"/>
        <source>Route type has been changed to &apos;{type}&apos; for {count} route(s).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="106"/>
        <source>This Route layer has no {column} column, so there is nowhere to record a route type. Save the project to a GeoPackage, or add the column to the layer, and try again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="110"/>
        <source>{count} of the selected routes would not take the new type</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="112"/>
        <source>The Route layer was already in edit mode, so this change is not saved yet. Use Layer &gt; Save Layer Edits when you are ready.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="116"/>
        <source>Change route type</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="118"/>
        <source>Add merged route</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="119"/>
        <source>Remove merged routes</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="732"/>
        <source>a route could not be reprojected and was left out</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="808"/>
        <source>a route was rejected by the layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="817"/>
        <source>Choose a route file</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="819"/>
        <source>GIS files</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="821"/>
        <source>All files</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="857"/>
        <source>{count} feature(s) in the file could not be imported and were skipped.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="875"/>
        <source>{count} route(s) were added to the Route layer but could not be saved. Close any program holding the file open, then use Layer &gt; Save Layer Edits. The reason is in the message bar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="879"/>
        <source>{count} route(s) of type {kind} were added to the Route layer. They are not saved yet, because you already had the layer open for editing -- use Layer &gt; Save Layer Edits when you are ready.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/route_manager.py" line="891"/>
        <source>None of the {count} feature(s) in the file could be imported. The reason is in the message bar.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQSlack</name>
    <message>
        <location filename="../core/slack_manager.py" line="54"/>
        <source>Optical slacks</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/slack_manager.py" line="294"/>
        <source>there is no optical slack layer to total</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/slack_manager.py" line="302"/>
        <source>&apos;{layer}&apos; has no cable reference columns, so the slack total was left alone</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/slack_manager.py" line="311"/>
        <source>&apos;{layer}&apos; has no slack length column, so the slack total was left alone</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/slack_manager.py" line="328"/>
        <source>the cable layer this slack belongs to is not in the project</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/slack_manager.py" line="365"/>
        <source>the cable would not take its new slack total</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../tools/slack_tool.py" line="396"/>
        <location filename="../core/slack_manager.py" line="471"/>
        <source>there is no optical slack layer to write to</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../tools/slack_tool.py" line="405"/>
        <location filename="../core/slack_manager.py" line="481"/>
        <source>&apos;{layer}&apos; has no cable reference columns, so no slack was created</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../tools/slack_tool.py" line="433"/>
        <location filename="../core/slack_manager.py" line="551"/>
        <source>the slack point was rejected by the layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/slack_manager.py" line="828"/>
        <source>Created {count} slacks.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../tools/slack_tool.py" line="378"/>
        <source>No cable found nearby.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../tools/slack_tool.py" line="454"/>
        <source>Slack saved.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQStore</name>
    <message>
        <location filename="../core/color_manager.py" line="23"/>
        <source>Colour catalogues</source>
        <extracomment>WP4 4.2 item R5. See fiberq.core.project_store.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/data_manager.py" line="31"/>
        <source>Optical relations</source>
        <extracomment>WP4 4.2 item R5. What each entry is called when something goes wrong with it. Translated at the call site, where the context stays a literal.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/relations_manager.py" line="32"/>
        <location filename="../core/interchange_import.py" line="1127"/>
        <location filename="../core/data_manager.py" line="32"/>
        <source>Pass-through elements</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/project_store.py" line="99"/>
        <source>Project data</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/project_store.py" line="100"/>
        <source>{what} could not be read from this project and has been left out, so you may see fewer than you saved. The unreadable text has been kept in the project under {key} -- do not save over it if you need it back. Reason: {reason}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/project_store.py" line="105"/>
        <source>{what} is stored in this project in a form FiberQ does not recognise and has been left out. The original text has been kept under {key}. Reason: {reason}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/project_store.py" line="109"/>
        <source>{what} could not be saved into the project. Reason: {reason}</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>FiberQUndo</name>
    <message>
        <location filename="../core/undo_manager.py" line="38"/>
        <source>FiberQ Undo</source>
        <extracomment>WP4 4.2 item R7, the undo/redo half. Strings in the FiberQUndo context, with QT_TRANSLATE_NOOP at the literal so pylupdate6 can read it.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/undo_manager.py" line="39"/>
        <source>the layer could not be opened for editing, so nothing was undone</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/undo_manager.py" line="41"/>
        <source>this could not be saved to {layer} and has been left on the undo list, still showing on the map. Clear whatever is holding the file and undo again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/undo_manager.py" line="45"/>
        <source>{layer} no longer has the column(s) {columns}, so what was restored is missing those values</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/undo_manager.py" line="48"/>
        <source>the layer would not take the earlier shape of this feature</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/undo_manager.py" line="50"/>
        <source>{count} of this feature&apos;s earlier values were refused by the layer</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ObjectsUI</name>
    <message>
        <location filename="../ui/objects_ui.py" line="51"/>
        <source>Object in 3 points</source>
        <extracomment>Menu entry. CRITICAL: throughout FiberQ &quot;Object&quot; means a BUILDING - it renders the legacy Serbian &quot;objekat&quot; (building/premises). Confirmed by the layer it writes to, whose fields are number of floors, number of basement levels, street and house number. Use your word for &quot;building&quot;, NOT a generic &quot;object/item/entity&quot;. Here: draw the footprint from 3 clicked points (the 4th corner of the rectangle is derived).</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/objects_ui.py" line="66"/>
        <source>Object in N points</source>
        <extracomment>Menu entry. &quot;Object&quot; = BUILDING (see above). Draws the footprint from any number of clicked points; N is the mathematical placeholder for &quot;any number&quot; - keep it as the letter N.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/objects_ui.py" line="82"/>
        <source>Object in N points (90°)</source>
        <extracomment>Menu entry. &quot;Object&quot; = BUILDING (see above). Same as &quot;Object in N points&quot; but every corner is forced to a right angle, for orthogonal building outlines. Keep the &quot;90&quot; and the degree sign.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/objects_ui.py" line="100"/>
        <source>Digitized object (from selection)</source>
        <extracomment>Menu entry. &quot;Object&quot; = BUILDING (see above). Turns a polygon ALREADY selected in another layer into a FiberQ building, rather than drawing a new one. &quot;Digitized&quot; is an adjective describing that copied outline.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/objects_ui.py" line="117"/>
        <source>Object</source>
        <extracomment>Message-box title, singular. &quot;Object&quot; = BUILDING (see above). NB the two sibling message boxes below use the PLURAL &quot;Objects&quot; as their title for the same feature - an inconsistency in the English; translate both as the same concept.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/objects_ui.py" line="121"/>
        <source>Activate a polygon layer and select geometry.</source>
        <extracomment>Body of that message box: nothing was selected yet. Instruction to the user - &quot;Activate&quot; = make the layer the active one in the QGIS Layers panel. &quot;geometry&quot; here means a polygon feature.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/objects_ui.py" line="144"/>
        <location filename="../ui/objects_ui.py" line="131"/>
        <source>Objects</source>
        <extracomment>Message-box title, plural. &quot;Objects&quot; = BUILDINGS (see above). Reused as the title of the next message box too.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/objects_ui.py" line="134"/>
        <source>Select one polygon.</source>
        <extracomment>Body: the user must select exactly one polygon. &quot;one&quot; carries the meaning &quot;a single&quot; - the tool handles one at a time.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/objects_ui.py" line="147"/>
        <source>A polygon is required.</source>
        <extracomment>Body: the selected feature was not a polygon (a building footprint must be an area, not a point or a line).</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/objects_ui.py" line="217"/>
        <location filename="../ui/objects_ui.py" line="204"/>
        <location filename="../ui/objects_ui.py" line="198"/>
        <source>Drawing object</source>
        <extracomment>Toolbar button tooltip and status tip, and the fallback button label - the SAME string is reused 3x here. It names the group of tools above, so it means &quot;drawing a BUILDING&quot; (gerund + object), i.e. digitising a footprint. It does NOT mean a drawing/CAD file - that is the separate &quot;Drawings&quot; button. Keep short: this button shows an icon only.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>QuickToolbar</name>
    <message>
        <location filename="../ui/quick_toolbar.py" line="263"/>
        <location filename="../ui/quick_toolbar.py" line="255"/>
        <source>{label} ({shortcut})</source>
        <extracomment>Tooltip pattern for every quick-toolbar button, e.g. &quot;Place Pole (P)&quot;. {label} is the already-translated button label and {shortcut} is a keyboard key such as P or Ctrl+Shift+Z. Keep both placeholders spelled exactly as they are; only the punctuation may be adapted.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>RoutingUI</name>
    <message>
        <location filename="../ui/routing_ui.py" line="281"/>
        <source>The auto-save folder is not there any more: {path}. Choose another file.</source>
        <extracomment>Shown when the project&apos;s auto-save GeoPackage is on a folder that is not there -- typically a project opened on another machine, or an unplugged drive. {path} is a file path, not translated.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="287"/>
        <source>The auto-save file cannot be written to: {path}. Choose another file.</source>
        <extracomment>Shown when the auto-save GeoPackage, or the folder holding it, cannot be written to. {path} is a file path, not translated.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="293"/>
        <source>The auto-save target is a folder, not a GeoPackage: {path}. Choose a file.</source>
        <extracomment>Shown when the stored auto-save target names a folder rather than a file. {path} is a file path, not translated.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="300"/>
        <source>That file is not a GeoPackage: {path}. Choose another file.</source>
        <extracomment>Shown when the stored auto-save target is not a GeoPackage at all -- the file dialog does not stop the user picking something else. {path} is a file path, not translated.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="60"/>
        <source>Add pole</source>
        <extracomment>Menu entry, imperative verb + noun. Places one pole (the physical support that carries aerial cable) at a clicked point. The Quick toolbar exposes this same command as &quot;Place Pole&quot; - keep the two wordings consistent.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="71"/>
        <source>Create route</source>
        <extracomment>Menu entry, imperative. &quot;Route&quot; here is the physical path/alignment on the ground that cables follow (fr: trace), NOT a network or file path. Builds the route line from the poles/manholes currently SELECTED - contrast with &quot;Create a route manually&quot; below. Quick toolbar wording: &quot;Create Route&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="80"/>
        <source>Merge selected routes</source>
        <extracomment>Menu entry, imperative. Joins the currently selected route lines into a single route feature. &quot;Merge&quot; is the geometry operation on the lines.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="89"/>
        <source>Import route from file</source>
        <extracomment>Menu entry, imperative. Loads route lines from an external GIS/CAD file on disk into the Route layer. &quot;file&quot; = a file on disk, not a QGIS project.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="101"/>
        <source>Add breakpoint</source>
        <extracomment>Menu entry, imperative. RESOLVED - this is a ROUTE GEOMETRY operation, not a fault: it SPLITS one route line into two at the clicked point (tool is BreakpointTool; every dialog it raises is titled &quot;Split route&quot;). NOT a fibre break/fault location - that is a separate feature (&quot;Fiber break&quot;). fr: &quot;point de coupure&quot; (split point), never &quot;coupure/rupture de fibre&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="111"/>
        <source>Create a route manually</source>
        <extracomment>Menu entry, imperative. Draws a route by clicking its vertices on the map. &quot;manually&quot; contrasts with &quot;Create route&quot; above, which derives the line automatically from the selected poles/manholes.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="120"/>
        <source>Change route type</source>
        <extracomment>Menu entry, imperative. Edits the &quot;route type&quot; ATTRIBUTE of the selected routes (aerial / underground / ...), leaving the geometry untouched.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="130"/>
        <source>Route correction</source>
        <extracomment>Menu entry AND the title of the dialog it opens; noun phrase. A validation pass: it finds routes whose start or end vertex does not sit on a pole or manhole and offers to snap them. &quot;correction&quot; = repairing those errors.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="151"/>
        <location filename="../ui/routing_ui.py" line="147"/>
        <location filename="../ui/routing_ui.py" line="140"/>
        <source>Routing</source>
        <extracomment>Toolbar drop-down button label, tooltip and status tip - the SAME string is reused 3x here, so one translation must serve all three. Noun: the group of route tools above. Keep it short enough for a toolbar button.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="396"/>
        <location filename="../ui/routing_ui.py" line="336"/>
        <location filename="../ui/routing_ui.py" line="269"/>
        <location filename="../ui/routing_ui.py" line="243"/>
        <location filename="../ui/routing_ui.py" line="224"/>
        <source>Auto GPKG</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="232"/>
        <source>Autosave off.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="269"/>
        <source>Autosave on GeoPackage.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="337"/>
        <source>Autosave off: this project has no GeoPackage chosen yet.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="346"/>
        <source>Choose GeoPackage file for auto-save</source>
        <extracomment>Title of the file-save dialog. &quot;GeoPackage&quot; is the OGC file format (.gpkg) - keep the format name untranslated.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>SelectionUI</name>
    <message>
        <location filename="../ui/selection_ui.py" line="52"/>
        <source>Smart selection (Multiple Layers)</source>
        <extracomment>Menu entry, noun phrase. A click-to-toggle selection tool that can pick features from SEVERAL layers at once without changing the active layer, and leaves selections on other layers untouched. &quot;Smart&quot; qualifies &quot;selection&quot;; the parenthesis explains the scope - keep the brackets.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/selection_ui.py" line="63"/>
        <source>Clear selection</source>
        <extracomment>Menu entry, imperative. NON-DESTRUCTIVE: it only DESELECTS - it removes the selection highlight from every layer and deletes nothing. It sits directly above &quot;Delete selected&quot;, which does destroy data, so the two must be unmistakably different in your language. Use your verb for &quot;deselect&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/selection_ui.py" line="74"/>
        <source>Delete selected</source>
        <extracomment>Menu entry, imperative. DESTRUCTIVE: permanently deletes the selected features from every editable layer. &quot;selected&quot; is an elliptical noun (&quot;the selected features&quot;). Must read as clearly more dangerous than &quot;Clear selection&quot; above, which merely deselects.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/selection_ui.py" line="95"/>
        <location filename="../ui/selection_ui.py" line="91"/>
        <location filename="../ui/selection_ui.py" line="84"/>
        <source>Selection</source>
        <extracomment>Toolbar drop-down button label, tooltip and status tip - the SAME string is reused 3x here, so one translation must serve all three. Noun naming the group of selection tools. Keep it short for a toolbar button.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>SlackUI</name>
    <message>
        <location filename="../ui/slack_ui.py" line="48"/>
        <source>Place terminal slack (interactive)</source>
        <extracomment>Menu entry, imperative. &quot;Slack&quot; = the spare length of cable coiled and stored at a point so it can be re-spliced later (fr: the coil is a &quot;love&quot;, &quot;reserve&quot;; &quot;lovage&quot; is the act of coiling). FiberQ has exactly TWO slack types and they must stay distinct: TERMINAL slack sits at a cable END (legacy name &quot;end slack&quot;, internally &quot;zavrsna&quot;, drawn as a C coil). &quot;(interactive)&quot; = you click the spot, as opposed to the batch entry below.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/slack_ui.py" line="59"/>
        <source>Place mid span slack (interactive)</source>
        <extracomment>Menu entry, imperative. The OTHER slack type: MID SPAN slack sits at an intermediate point where the cable runs THROUGH without being cut (legacy name &quot;thru slack&quot;, internally &quot;prolazna&quot;, drawn as an S coil). It is NOT the same as terminal slack above - do not translate both with one word. Here &quot;span&quot; = the run between two supports/points, not a bridge span.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/slack_ui.py" line="69"/>
        <source>Generate terminal slacks at the ends of selected cables</source>
        <extracomment>Menu entry, imperative. Batch counterpart of the first entry: for every SELECTED cable it creates a terminal slack at BOTH endpoints at once (20 m by default), instead of you clicking each one. &quot;ends&quot; = the cable&apos;s two extremities. Long string, but it is a menu entry only - no width limit.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/slack_ui.py" line="91"/>
        <location filename="../ui/slack_ui.py" line="87"/>
        <source>Optical slacks</source>
        <extracomment>Toolbar button tooltip and status tip (same string twice). Plural noun naming the group of slack tools, and the map layer they write to. This button shows an icon only, so the text appears solely on hover.</extracomment>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ValidationPanel</name>
    <message>
        <location filename="../ui/validation_panel.py" line="281"/>
        <source>No issues found — {rules} rules ran over {layers} layers, {features} features.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="293"/>
        <source>{summary} — showing {shown} of {total}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="96"/>
        <source>FiberQ validation</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="273"/>
        <location filename="../ui/validation_panel.py" line="108"/>
        <source>No validation run yet.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="112"/>
        <source>Re-run</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="113"/>
        <source>Validate the project again</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="117"/>
        <source>Export report…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="118"/>
        <source>Save the results as a report</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="126"/>
        <source>Severity:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="130"/>
        <source>Layer:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="134"/>
        <source>Rule:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="147"/>
        <source>Severity</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="148"/>
        <source>Rule</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="149"/>
        <source>Layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="150"/>
        <source>Feature</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="151"/>
        <source>Message</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="194"/>
        <source>Validating…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="200"/>
        <source>Error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="202"/>
        <source>Warning</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="203"/>
        <source>Info</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/validation_panel.py" line="219"/>
        <location filename="../ui/validation_panel.py" line="215"/>
        <location filename="../ui/validation_panel.py" line="211"/>
        <source>All</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../ui/validation_panel.py" line="287"/>
        <source>%n error(s)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../ui/validation_panel.py" line="288"/>
        <source>%n warning(s)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../ui/validation_panel.py" line="289"/>
        <source>%n info</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../ui/validation_panel.py" line="299"/>
        <source>%n rule(s) failed to run</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
</context>
<context>
    <name>ValidationReport</name>
    <message>
        <location filename="../core/validation_report.py" line="260"/>
        <source>FiberQ validation report</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="261"/>
        <source>Untitled project</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="266"/>
        <source>No errors — project is structurally sound</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="268"/>
        <source>Errors found — not ready to hand over</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="281"/>
        <source>Errors</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="282"/>
        <source>Warnings</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="336"/>
        <location filename="../core/validation_report.py" line="283"/>
        <source>Info</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="284"/>
        <source>Total</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="290"/>
        <source>Coordinate system</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="291"/>
        <source>Schema version</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="292"/>
        <source>Plugin version</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="293"/>
        <source>Run at</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="294"/>
        <source>Rules run</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="297"/>
        <source>Rules skipped</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="305"/>
        <source>Run</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="316"/>
        <source>Rules that failed to run</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="358"/>
        <location filename="../core/validation_report.py" line="323"/>
        <source>Issues</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="326"/>
        <source>No issues found.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="330"/>
        <source>Severity</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="330"/>
        <source>Rule</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="357"/>
        <location filename="../core/validation_report.py" line="330"/>
        <source>Layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="331"/>
        <source>Feature</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="331"/>
        <source>Message</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="335"/>
        <source>Error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="335"/>
        <source>Warning</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="356"/>
        <source>Issues by layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="372"/>
        <source>Generated by the FiberQ QGIS plugin.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="374"/>
        <source>Machine-readable JSON and CSV of the same run are available from the same export menu.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ValidationRules</name>
    <message>
        <location filename="../core/validation_rules.py" line="417"/>
        <source>Cable endpoint is not connected to any element or cable (tolerance {tol})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="448"/>
        <source>Cable endpoint is {distance} from {target} -- just outside the {tol} snapping tolerance; it probably should connect</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="503"/>
        <source>Element is not on or near any cable or route (tolerance {tol})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="564"/>
        <source>Referenced cable layer {layer_id} is not in the project</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="569"/>
        <source>Referenced cable feature {fid} does not exist in layer {layer}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="579"/>
        <source>Referenced layer {layer} is not a cable layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="615"/>
        <source>Feature is {distance} from the cable it references (tolerance {tol}) -- the cable may have been re-routed</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="645"/>
        <source>Layer is missing the fiberq_uuid identity field</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="648"/>
        <source>Re-open the project so migration can add fiberq_uuid, or re-create the layer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="659"/>
        <source>Feature has no fiberq_uuid value</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="668"/>
        <source>Duplicate fiberq_uuid — the same identity is already used by feature {fid} in layer {layer}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="697"/>
        <source>No FiberQ layers found in this project, so nothing was checked.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="703"/>
        <source>Open a FiberQ project, or create the layers with the FiberQ toolbar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="726"/>
        <source>Required field(s) missing or empty: {fields}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="770"/>
        <source>Field {field}: value {value} is not one of the allowed values ({allowed})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="838"/>
        <source>Field {field}: {value} is out of range (expected {bound})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="921"/>
        <source>Length checks skipped: they need either a projected CRS or a project ellipsoid, but this layer uses {crs} with none set</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="946"/>
        <source>Stored {field} ({stored}) does not match the drawn geometry ({computed})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="969"/>
        <source>total_len_m ({total}) should equal duzina_m + slack_m ({expected})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="998"/>
        <source>duzina_km ({km}) does not match duzina/1000 ({expected})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1029"/>
        <source>The project has no coordinate reference system set</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1034"/>
        <source>Set it in Project -&gt; Properties -&gt; CRS, to the same system the layers use. Features drawn without one cannot be placed reliably.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1053"/>
        <source>Layer uses a geographic CRS ({crs}), where the connectivity tolerance is measured in degrees rather than metres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1063"/>
        <source>Reproject the project and its layers to a projected CRS, ideally your national grid.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1072"/>
        <source>No ellipsoid could be resolved for {crs}, so lengths cannot be checked</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1084"/>
        <source>FiberQ layers do not all share one CRS: {list}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1116"/>
        <source>Feature has no geometry</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1129"/>
        <source>Line has zero length</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1133"/>
        <source>Line crosses itself</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1138"/>
        <source>Polygon has zero area</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1140"/>
        <source>Polygon boundary is self-intersecting</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1164"/>
        <source>Cable endpoints are connected</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1172"/>
        <source>Cable endpoints are not near-misses</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1180"/>
        <source>Elements are attached to the network</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1188"/>
        <source>Optical slack references an existing cable</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1196"/>
        <source>Fiber break references an existing cable</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1204"/>
        <source>Cable references are spatially coherent</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1212"/>
        <source>Feature identity present and unique</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1219"/>
        <source>Required attributes present</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1226"/>
        <source>Project contains FiberQ layers</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1233"/>
        <source>Attribute values within allowed domain</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1240"/>
        <source>Numeric attributes within plausible ranges</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1247"/>
        <source>Stored lengths agree with geometry</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1255"/>
        <source>Coordinate reference systems are consistent</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1262"/>
        <source>Geometries are present and well formed</source>
        <translation type="unfinished"></translation>
    </message>
</context>
</TS>
