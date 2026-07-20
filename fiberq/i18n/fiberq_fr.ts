<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE TS>
<TS version="2.1" language="fr" sourcelanguage="en">
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
        <location filename="../main_plugin.py" line="3645"/>
        <source>FiberQ – Preview Map</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3646"/>
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
    <name>FiberQPlugin</name>
    <message>
        <location filename="../main_plugin.py" line="1020"/>
        <location filename="../main_plugin.py" line="1004"/>
        <location filename="../main_plugin.py" line="231"/>
        <location filename="../main_plugin.py" line="215"/>
        <source>Interface language</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="232"/>
        <source>Language set to {language}.

Language will change when QGIS restarts.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="248"/>
        <source>BOM report</source>
        <extracomment>Error-dialog title. &quot;BOM&quot; = Bill of Materials (costed list of materials for the design), NOT the Unicode byte-order mark.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3440"/>
        <location filename="../main_plugin.py" line="2077"/>
        <location filename="../main_plugin.py" line="1956"/>
        <location filename="../main_plugin.py" line="1930"/>
        <location filename="../main_plugin.py" line="1912"/>
        <location filename="../main_plugin.py" line="1821"/>
        <location filename="../main_plugin.py" line="798"/>
        <location filename="../main_plugin.py" line="653"/>
        <location filename="../main_plugin.py" line="508"/>
        <location filename="../main_plugin.py" line="249"/>
        <source>Error: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="258"/>
        <source>Locator</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="259"/>
        <source>Error opening locator: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1113"/>
        <location filename="../main_plugin.py" line="507"/>
        <source>Publish to PostGIS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="570"/>
        <source>Health check</source>
        <extracomment>Dialog title. &quot;Health check&quot; = a validation pass over the QGIS PROJECT&apos;s data (are the Route/Poles/Manholes layers present, of the right geometry type, and internally consistent). It is a data-integrity check, NOT a measurement of optical/network health and not hardware diagnostics.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="571"/>
        <source>Error while running detailed route check:
{details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1633"/>
        <location filename="../main_plugin.py" line="652"/>
        <source>Change element type</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3353"/>
        <location filename="../main_plugin.py" line="751"/>
        <location filename="../main_plugin.py" line="698"/>
        <source>Select one or more elements and try again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="705"/>
        <source>Choose image</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="707"/>
        <source>Images (*.jpg *.jpeg *.png *.gif);;All files (*.*)</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="720"/>
        <source>Image linked to %n element(s).</source>
        <extracomment>Confirmation after attaching one photo to the selected map elements. %n is how many elements now point at that image; Qt substitutes it, so keep %n and do not turn it into {count}.</extracomment>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="737"/>
        <source>Image</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="738"/>
        <source>Click on an element to open its image (ESC to exit).</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="760"/>
        <source>Image link removed for %n element(s).</source>
        <extracomment>Confirmation after detaching the photo from the selected map elements. Only the link is cleared - the image file itself is not deleted. %n is how many elements were unlinked; keep %n.</extracomment>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="786"/>
        <source>Cutting</source>
        <extracomment>Message-bar heading for the geometry-splitting tool. &quot;Cutting&quot; = the act of splitting a line feature in two, NOT a cable fault/outage. Verbal noun; keep it short (banner title). The body text below belongs to the same tool.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="787"/>
        <source>Tool activated. Move mouse over line (red cross), left click to cut, right/ESC exit.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="797"/>
        <source>Infrastructure cutting</source>
        <extracomment>Error-dialog title for the geometry-splitting tool. &quot;cutting&quot; = splitting a line feature at a clicked point, NOT a cable fault. Same tool as the &quot;Cut infrastructure&quot; button.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="842"/>
        <source>{name} – About</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="886"/>
        <source>About dialog error: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1046"/>
        <source>Undo (FiberQ)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1048"/>
        <source>Undo last FiberQ action (Ctrl+Shift+Z)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1056"/>
        <source>Redo (FiberQ)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1058"/>
        <source>Redo last undone FiberQ action (Ctrl+Shift+Y)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1081"/>
        <source>Help / About</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1082"/>
        <source>Help and information about FiberQ</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1119"/>
        <source>Publish the active (or selected) layer to PostGIS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1161"/>
        <source>Terminal slack (shortcut)</source>
        <extracomment>Label of a HIDDEN action that only exists to bind the &quot;R&quot; key; it shows up in the QGIS keyboard-shortcuts list, not on a toolbar. &quot;Slack&quot; = spare cable length coiled at a point for later re-splicing (fr &quot;love&quot;/&quot;reserve&quot;); TERMINAL slack is the type that sits at a cable END - keep it distinct from &quot;mid span&quot; slack. &quot;(shortcut)&quot; refers to the key binding, not to a Windows shortcut file.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1172"/>
        <source>Optical schematic view</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1179"/>
        <source>Import points</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3072"/>
        <location filename="../main_plugin.py" line="3048"/>
        <location filename="../main_plugin.py" line="3028"/>
        <location filename="../main_plugin.py" line="2979"/>
        <location filename="../main_plugin.py" line="2895"/>
        <location filename="../main_plugin.py" line="2884"/>
        <location filename="../main_plugin.py" line="1190"/>
        <source>Export</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1195"/>
        <source>Export selected...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1199"/>
        <source>Export selected features of the active layer to GPX / KML / KMZ / GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1209"/>
        <source>Export all...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1213"/>
        <source>Export all features of the active layer to GPX / KML / KMZ / GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1225"/>
        <source>Export active layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1245"/>
        <source>Hide locator</source>
        <extracomment>Toolbar button that removes the address marker the Locator dropped on the map. &quot;Hide&quot; is a VERB (imperative); &quot;locator&quot; is the same address-finder feature as the &quot;Locator&quot; button above.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1257"/>
        <source>Relations</source>
        <extracomment>Toolbar button opening &quot;Optical relations management&quot;. A FiberQ &quot;relation&quot; is a named end-to-end optical link (a logical route between two sites) that cables get assigned to - telecom domain sense, plural NOUN. NOT QGIS layer relations (foreign keys between tables), and not &quot;relationship&quot; in the general sense.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1268"/>
        <source>List of latent elements</source>
        <extracomment>Toolbar button opening a table of &quot;latent&quot; elements. In FiberQ a latent element is a passive optical element (joint closure, ODF, OTB, termination box) that sits ON a cable&apos;s path at a recorded distance along it, between the cable&apos;s two endpoints - recorded as data, not drawn as a separate map feature. &quot;latent&quot; = intermediate/pass-through, NOT &quot;faulty&quot;, &quot;hidden bug&quot; or &quot;dormant&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1291"/>
        <source>Cut infrastructure</source>
        <extracomment>Toolbar button. &quot;Cut&quot; is a VERB, imperative, in the GEOMETRY -EDITING sense: the tool splits one line feature into two at the point you click (see addons/infrastructure_cut.py, _split_feature_at_point). It is NOT a cable fault/break - French &quot;decouper&quot;/&quot;scinder&quot;, never &quot;coupure&quot;. The separate fault tool is &quot;Fiber break&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1332"/>
        <source>Fiber break</source>
        <extracomment>Toolbar button. NOUN: a fault - the point where a fibre is broken or severed (fr &quot;coupure&quot;/&quot;rupture&quot;). This IS the fault concept, unlike &quot;Cut infrastructure&quot; above, which is geometry editing. The tool marks a break location on the map. &quot;break&quot; is not a pause and not a rest.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1346"/>
        <source>Color catalog</source>
        <extracomment>Toolbar entry opening the FIBRE COLOUR CODE: the standard sequence of colours identifying each tube and each fibre within a cable (e.g. the TIA-598 or IEC ordering). This is industry cable terminology - it is NOT a QGIS symbology palette or a map-styling colour picker.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1357"/>
        <source>Save all layers to GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1358"/>
        <source>Export all vector layers (including Temporary scratch) to a single .gpkg and redirect the project to it</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1378"/>
        <source>Auto save to GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1380"/>
        <source>When enabled: every new or memory layer is automatically written to the selected .gpkg and redirected to it</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1398"/>
        <source>Preview Map</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1399"/>
        <source>Open the FiberQ Preview Map (PostGIS connection from config.ini)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1413"/>
        <source>Create Service Area</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1414"/>
        <source>Create Service Area from selection (buffer around selected cables/elements)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1429"/>
        <source>Draw Service Area Manually</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1430"/>
        <source>Manual Service Area drawing (like Google Earth) and entry into Service Area layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1456"/>
        <source>Branch info</source>
        <extracomment>Toolbar button. &quot;Branch&quot; is a NOUN in the cable-network sense - a branching/junction point where cables split off (French &quot;derivation&quot;). Click a cable to see how many cables, of which types and capacities, meet at that point. Not a tree branch, not a company branch office, not a version-control branch.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1464"/>
        <source>Click on cable to show number of cables/types/capacities at that point</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1484"/>
        <location filename="../main_plugin.py" line="1481"/>
        <source>Show shortcuts</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1516"/>
        <source>BOM report (XLSX/CSV)</source>
        <extracomment>Toolbar button. &quot;BOM&quot; = Bill of Materials, the costed list of cables/closures/poles a design consumes (fr &quot;nomenclature&quot; / &quot;liste de materiel&quot;). It is NOT the Unicode byte-order mark. XLSX/CSV are file formats and stay untranslated. Expand or keep &quot;BOM&quot; per the convention of your language&apos;s telecom/engineering usage.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1575"/>
        <source>Check (health check)</source>
        <extracomment>Toolbar action running the project data-integrity check (are the expected FiberQ layers present, right geometry type, routes consistent). Imperative verb + the feature&apos;s name in brackets; it is NOT optical/network health. Same feature as the &quot;Health check&quot; dialog title - keep the bracketed term identical to that one.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1611"/>
        <source>Settings</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1634"/>
        <source>Smart selection + change element type (visual style)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1653"/>
        <source>Move elements</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1654"/>
        <source>Move elements on the map (click-move-click)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1658"/>
        <source>Import picture to element</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1662"/>
        <source>Link a .jpg/.png picture to selected element(s)</source>
        <extracomment>Toolbar tooltip. Static text built once at startup, so there is no count to plug in: &quot;(s)&quot; here just means &quot;one or more&quot;. Render it with whatever generic/plural form reads naturally.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1666"/>
        <source>Clear picture from element</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1670"/>
        <source>Unlink picture from selected element(s)</source>
        <extracomment>Toolbar tooltip. &quot;Unlink&quot; = detach the picture reference from the element; the image file on disk is NOT deleted. Static text, so &quot;(s)&quot; just means &quot;one or more&quot; - no count is substituted.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1820"/>
        <source>Placing elements</source>
        <extracomment>Error-dialog title. &quot;Placing elements&quot; is FiberQ&apos;s name for the CATEGORY of passive optical elements you drop on the map (ODF, TB, OTB, TO, patch panel, joint closures) - it is the layer-group label, not the -ing action of placing. Treat as a noun phrase.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1844"/>
        <source>Error activating: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1911"/>
        <location filename="../main_plugin.py" line="1906"/>
        <source>Smart selection</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1907"/>
        <source>Click on the elements to select/deselect them. Selections on other layers are not touched.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1922"/>
        <source>Click on cable to show number of cables/types/capacities at that point (right click or ESC to exit).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1955"/>
        <source>Optical schematic</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1965"/>
        <source>Error opening dialog: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2557"/>
        <location filename="../main_plugin.py" line="2552"/>
        <source>Delete</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2553"/>
        <source>No selected features to delete.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2558"/>
        <source>Deleted {count} selected features from all layers.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2624"/>
        <source>Shortcuts</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2690"/>
        <source>Choose a file with points (KML/KMZ/DWG/Shape/GPX)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2692"/>
        <source>GIS files (*.kml *.kmz *.shp *.dwg *.gpx);;All files (*)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2700"/>
        <source>Unable to load or invalid file!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2705"/>
        <source>The selected file does not contain points!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2776"/>
        <location filename="../main_plugin.py" line="2772"/>
        <source>Unable to create or find the Poles layer!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2811"/>
        <source>Unable to find the target layer!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2873"/>
        <source>Imported {count} points into layer &apos;{layer}&apos;!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2885"/>
        <source>Please select an active vector layer before exporting.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2896"/>
        <source>There are no selected features on the active layer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2909"/>
        <source>Export format</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2910"/>
        <source>Select output format:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2938"/>
        <source>Export layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2980"/>
        <source>Unknown driver for extension &apos;{ext}&apos;.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3029"/>
        <source>Error while exporting:
{details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3049"/>
        <source>Export failed: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3062"/>
        <source>Successfully exported the selected features of layer &apos;{layer}&apos;
to:
{path}</source>
        <extracomment>Confirmation shown after exporting ONLY the features the user had selected. {layer} is the source layer name, {path} the written file. Keep as one whole sentence - do not split it.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3068"/>
        <source>Successfully exported all features of layer &apos;{layer}&apos;
to:
{path}</source>
        <extracomment>Confirmation shown after exporting the WHOLE layer (no selection filter). {layer} is the source layer name, {path} the written file. Keep as one whole sentence - do not split it.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3149"/>
        <source>Route correction</source>
        <extracomment>Dialog title for the results of the route-consistency check (e.g. route lines whose ends do not meet a pole). &quot;Route&quot; = the physical cable route/trench on the map, not a road and not a network route. &quot;Correction&quot; is a NOUN: the fixing-up of those defects.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3150"/>
        <source>No errors found!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3164"/>
        <source>Layer &apos;Poles&apos; not found!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3204"/>
        <source>Route layer &apos;Route&apos; not found!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3214"/>
        <source>Route has been automatically attached to a pole.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="3374"/>
        <source>Drawing link removed for %n element(s).</source>
        <extracomment>Confirmation after detaching a drawing (a CAD/PDF document attached to an element) from the selected map elements. Only the link is cleared - the drawing file is not deleted. %n is how many elements were actually unlinked; keep %n.</extracomment>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3435"/>
        <source>Placing manhole</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3436"/>
        <source>Click on the map to place the manhole (ESC to exit).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3439"/>
        <source>Manhole</source>
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
        <location filename="../ui/routing_ui.py" line="52"/>
        <source>Add pole</source>
        <extracomment>Menu entry, imperative verb + noun. Places one pole (the physical support that carries aerial cable) at a clicked point. The Quick toolbar exposes this same command as &quot;Place Pole&quot; - keep the two wordings consistent.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="63"/>
        <source>Create route</source>
        <extracomment>Menu entry, imperative. &quot;Route&quot; here is the physical path/alignment on the ground that cables follow (fr: trace), NOT a network or file path. Builds the route line from the poles/manholes currently SELECTED - contrast with &quot;Create a route manually&quot; below. Quick toolbar wording: &quot;Create Route&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="72"/>
        <source>Merge selected routes</source>
        <extracomment>Menu entry, imperative. Joins the currently selected route lines into a single route feature. &quot;Merge&quot; is the geometry operation on the lines.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="81"/>
        <source>Import route from file</source>
        <extracomment>Menu entry, imperative. Loads route lines from an external GIS/CAD file on disk into the Route layer. &quot;file&quot; = a file on disk, not a QGIS project.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="93"/>
        <source>Add breakpoint</source>
        <extracomment>Menu entry, imperative. RESOLVED - this is a ROUTE GEOMETRY operation, not a fault: it SPLITS one route line into two at the clicked point (tool is BreakpointTool; every dialog it raises is titled &quot;Split route&quot;). NOT a fibre break/fault location - that is a separate feature (&quot;Fiber break&quot;). fr: &quot;point de coupure&quot; (split point), never &quot;coupure/rupture de fibre&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="103"/>
        <source>Create a route manually</source>
        <extracomment>Menu entry, imperative. Draws a route by clicking its vertices on the map. &quot;manually&quot; contrasts with &quot;Create route&quot; above, which derives the line automatically from the selected poles/manholes.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="112"/>
        <source>Change route type</source>
        <extracomment>Menu entry, imperative. Edits the &quot;route type&quot; ATTRIBUTE of the selected routes (aerial / underground / ...), leaving the geometry untouched.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="122"/>
        <source>Route correction</source>
        <extracomment>Menu entry AND the title of the dialog it opens; noun phrase. A validation pass: it finds routes whose start or end vertex does not sit on a pole or manhole and offers to snap them. &quot;correction&quot; = repairing those errors.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="143"/>
        <location filename="../ui/routing_ui.py" line="139"/>
        <location filename="../ui/routing_ui.py" line="132"/>
        <source>Routing</source>
        <extracomment>Toolbar drop-down button label, tooltip and status tip - the SAME string is reused 3x here, so one translation must serve all three. Noun: the group of route tools above. Keep it short enough for a toolbar button.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="207"/>
        <source>Choose GeoPackage file for auto-save</source>
        <extracomment>Title of the file-save dialog. &quot;GeoPackage&quot; is the OGC file format (.gpkg) - keep the format name untranslated.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="252"/>
        <location filename="../ui/routing_ui.py" line="239"/>
        <source>Auto GPKG</source>
        <extracomment>Message-bar heading, reused for both the on and the off message. &quot;Auto GPKG&quot; = automatic saving to a GeoPackage; GPKG is that format&apos;s file extension. Keep &quot;GPKG&quot; as-is. The message beside it (&quot;Autosave on GeoPackage.&quot;) means autosaving is now ENABLED.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="239"/>
        <source>Autosave on GeoPackage.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../ui/routing_ui.py" line="252"/>
        <source>Autosave off.</source>
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
</TS>
