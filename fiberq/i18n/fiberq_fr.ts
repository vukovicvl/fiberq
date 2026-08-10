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
        <location filename="../main_plugin.py" line="3989"/>
        <source>FiberQ – Preview Map</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3990"/>
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
        <location filename="../main_plugin.py" line="360"/>
        <source>Validation could not run: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="426"/>
        <source>Could not save the report: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="431"/>
        <source>Saved {format} report to {path}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="453"/>
        <source>Could not check lengths: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="458"/>
        <source>Skipped {layers}: lengths cannot be measured without an ellipsoid. Set one in Project Properties &gt; General.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="466"/>
        <source>Could not check {layers}.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="495"/>
        <source>Largest change: {field} {old} -&gt; {new} on {layer}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="521"/>
        <source>{layers} left unchanged: save or discard the open edits there, then run this again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="529"/>
        <source>Some layers could not be updated: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1294"/>
        <location filename="../main_plugin.py" line="1278"/>
        <location filename="../main_plugin.py" line="230"/>
        <location filename="../main_plugin.py" line="214"/>
        <source>Interface language</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="231"/>
        <source>Language set to {language}.

Language will change when QGIS restarts.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="247"/>
        <source>BOM report</source>
        <extracomment>Error-dialog title. &quot;BOM&quot; = Bill of Materials (costed list of materials for the design), NOT the Unicode byte-order mark.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3784"/>
        <location filename="../main_plugin.py" line="2409"/>
        <location filename="../main_plugin.py" line="2288"/>
        <location filename="../main_plugin.py" line="2262"/>
        <location filename="../main_plugin.py" line="2244"/>
        <location filename="../main_plugin.py" line="2153"/>
        <location filename="../main_plugin.py" line="1072"/>
        <location filename="../main_plugin.py" line="927"/>
        <location filename="../main_plugin.py" line="782"/>
        <location filename="../main_plugin.py" line="248"/>
        <source>Error: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="257"/>
        <source>Locator</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="258"/>
        <source>Error opening locator: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="371"/>
        <source>%n error(s)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="372"/>
        <source>%n warning(s)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="373"/>
        <source>%n info</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="381"/>
        <source>Validation found no issues.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="400"/>
        <source>Run a validation before exporting a report.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="409"/>
        <source>Export validation report</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="475"/>
        <source>No lengths were checked. See the warnings above.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="478"/>
        <source>No FiberQ layers with stored lengths in this project.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="481"/>
        <source>All stored lengths already match the geometry.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="486"/>
        <source>%n feature(s) will have their stored length rewritten from the drawn geometry.</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="503"/>
        <source>Recalculate lengths</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="504"/>
        <source>Recalculate stored lengths?</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="506"/>
        <source>Lengths are measured on the project ellipsoid, the same way the QGIS measure tool does. Slack values are read but never changed.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="518"/>
        <source>Recalculated lengths on %n feature(s).</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="549"/>
        <source>This issue is not tied to a map location.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1387"/>
        <location filename="../main_plugin.py" line="781"/>
        <source>Publish to PostGIS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="844"/>
        <source>Health check</source>
        <extracomment>Dialog title. &quot;Health check&quot; = a validation pass over the QGIS PROJECT&apos;s data (are the Route/Poles/Manholes layers present, of the right geometry type, and internally consistent). It is a data-integrity check, NOT a measurement of optical/network health and not hardware diagnostics.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="845"/>
        <source>Error while running detailed route check:
{details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1957"/>
        <location filename="../main_plugin.py" line="926"/>
        <source>Change element type</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3697"/>
        <location filename="../main_plugin.py" line="1025"/>
        <location filename="../main_plugin.py" line="972"/>
        <source>Select one or more elements and try again.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="979"/>
        <source>Choose image</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="981"/>
        <source>Images (*.jpg *.jpeg *.png *.gif);;All files (*.*)</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="994"/>
        <source>Image linked to %n element(s).</source>
        <extracomment>Confirmation after attaching one photo to the selected map elements. %n is how many elements now point at that image; Qt substitutes it, so keep %n and do not turn it into {count}.</extracomment>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1011"/>
        <source>Image</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1012"/>
        <source>Click on an element to open its image (ESC to exit).</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="1034"/>
        <source>Image link removed for %n element(s).</source>
        <extracomment>Confirmation after detaching the photo from the selected map elements. Only the link is cleared - the image file itself is not deleted. %n is how many elements were unlinked; keep %n.</extracomment>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1060"/>
        <source>Cutting</source>
        <extracomment>Message-bar heading for the geometry-splitting tool. &quot;Cutting&quot; = the act of splitting a line feature in two, NOT a cable fault/outage. Verbal noun; keep it short (banner title). The body text below belongs to the same tool.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1061"/>
        <source>Tool activated. Move mouse over line (red cross), left click to cut, right/ESC exit.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1071"/>
        <source>Infrastructure cutting</source>
        <extracomment>Error-dialog title for the geometry-splitting tool. &quot;cutting&quot; = splitting a line feature at a clicked point, NOT a cable fault. Same tool as the &quot;Cut infrastructure&quot; button.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1116"/>
        <source>{name} – About</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1160"/>
        <source>About dialog error: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1320"/>
        <source>Undo (FiberQ)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1322"/>
        <source>Undo last FiberQ action (Ctrl+Shift+Z)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1330"/>
        <source>Redo (FiberQ)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1332"/>
        <source>Redo last undone FiberQ action (Ctrl+Shift+Y)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1355"/>
        <source>Help / About</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1356"/>
        <source>Help and information about FiberQ</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1393"/>
        <source>Publish the active (or selected) layer to PostGIS</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1435"/>
        <source>Terminal slack (shortcut)</source>
        <extracomment>Label of a HIDDEN action that only exists to bind the &quot;R&quot; key; it shows up in the QGIS keyboard-shortcuts list, not on a toolbar. &quot;Slack&quot; = spare cable length coiled at a point for later re-splicing (fr &quot;love&quot;/&quot;reserve&quot;); TERMINAL slack is the type that sits at a cable END - keep it distinct from &quot;mid span&quot; slack. &quot;(shortcut)&quot; refers to the key binding, not to a Windows shortcut file.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1446"/>
        <source>Optical schematic view</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1453"/>
        <source>Import points</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3416"/>
        <location filename="../main_plugin.py" line="3392"/>
        <location filename="../main_plugin.py" line="3372"/>
        <location filename="../main_plugin.py" line="3323"/>
        <location filename="../main_plugin.py" line="3239"/>
        <location filename="../main_plugin.py" line="3228"/>
        <location filename="../main_plugin.py" line="1464"/>
        <source>Export</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1469"/>
        <source>Export selected...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1473"/>
        <source>Export selected features of the active layer to GPX / KML / KMZ / GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1483"/>
        <source>Export all...</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1487"/>
        <source>Export all features of the active layer to GPX / KML / KMZ / GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1499"/>
        <source>Export active layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1519"/>
        <source>Hide locator</source>
        <extracomment>Toolbar button that removes the address marker the Locator dropped on the map. &quot;Hide&quot; is a VERB (imperative); &quot;locator&quot; is the same address-finder feature as the &quot;Locator&quot; button above.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1531"/>
        <source>Relations</source>
        <extracomment>Toolbar button opening &quot;Optical relations management&quot;. A FiberQ &quot;relation&quot; is a named end-to-end optical link (a logical route between two sites) that cables get assigned to - telecom domain sense, plural NOUN. NOT QGIS layer relations (foreign keys between tables), and not &quot;relationship&quot; in the general sense.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1542"/>
        <source>List of latent elements</source>
        <extracomment>Toolbar button opening a table of &quot;latent&quot; elements. In FiberQ a latent element is a passive optical element (joint closure, ODF, OTB, termination box) that sits ON a cable&apos;s path at a recorded distance along it, between the cable&apos;s two endpoints - recorded as data, not drawn as a separate map feature. &quot;latent&quot; = intermediate/pass-through, NOT &quot;faulty&quot;, &quot;hidden bug&quot; or &quot;dormant&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1565"/>
        <source>Cut infrastructure</source>
        <extracomment>Toolbar button. &quot;Cut&quot; is a VERB, imperative, in the GEOMETRY -EDITING sense: the tool splits one line feature into two at the point you click (see addons/infrastructure_cut.py, _split_feature_at_point). It is NOT a cable fault/break - French &quot;decouper&quot;/&quot;scinder&quot;, never &quot;coupure&quot;. The separate fault tool is &quot;Fiber break&quot;.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1606"/>
        <source>Fiber break</source>
        <extracomment>Toolbar button. NOUN: a fault - the point where a fibre is broken or severed (fr &quot;coupure&quot;/&quot;rupture&quot;). This IS the fault concept, unlike &quot;Cut infrastructure&quot; above, which is geometry editing. The tool marks a break location on the map. &quot;break&quot; is not a pause and not a rest.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1620"/>
        <source>Color catalog</source>
        <extracomment>Toolbar entry opening the FIBRE COLOUR CODE: the standard sequence of colours identifying each tube and each fibre within a cable (e.g. the TIA-598 or IEC ordering). This is industry cable terminology - it is NOT a QGIS symbology palette or a map-styling colour picker.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1631"/>
        <source>Save all layers to GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1632"/>
        <source>Export all vector layers (including Temporary scratch) to a single .gpkg and redirect the project to it</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1652"/>
        <source>Auto save to GeoPackage</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1654"/>
        <source>When enabled: every new or memory layer is automatically written to the selected .gpkg and redirected to it</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1672"/>
        <source>Preview Map</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1673"/>
        <source>Open the FiberQ Preview Map (PostGIS connection from config.ini)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1687"/>
        <source>Create Service Area</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1688"/>
        <source>Create Service Area from selection (buffer around selected cables/elements)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1703"/>
        <source>Draw Service Area Manually</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1704"/>
        <source>Manual Service Area drawing (like Google Earth) and entry into Service Area layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1730"/>
        <source>Branch info</source>
        <extracomment>Toolbar button. &quot;Branch&quot; is a NOUN in the cable-network sense - a branching/junction point where cables split off (French &quot;derivation&quot;). Click a cable to see how many cables, of which types and capacities, meet at that point. Not a tree branch, not a company branch office, not a version-control branch.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1738"/>
        <source>Click on cable to show number of cables/types/capacities at that point</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1758"/>
        <location filename="../main_plugin.py" line="1755"/>
        <source>Show shortcuts</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1790"/>
        <source>BOM report (XLSX/CSV)</source>
        <extracomment>Toolbar button. &quot;BOM&quot; = Bill of Materials, the costed list of cables/closures/poles a design consumes (fr &quot;nomenclature&quot; / &quot;liste de materiel&quot;). It is NOT the Unicode byte-order mark. XLSX/CSV are file formats and stay untranslated. Expand or keep &quot;BOM&quot; per the convention of your language&apos;s telecom/engineering usage.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1849"/>
        <source>Check (health check)</source>
        <extracomment>Toolbar action running the project data-integrity check (are the expected FiberQ layers present, right geometry type, routes consistent). Imperative verb + the feature&apos;s name in brackets; it is NOT optical/network health. Same feature as the &quot;Health check&quot; dialog title - keep the bracketed term identical to that one.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1878"/>
        <source>Validate project</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1905"/>
        <source>Recalculate lengths…</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1906"/>
        <source>Rewrite stored lengths that disagree with the drawn geometry</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1935"/>
        <source>Settings</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1958"/>
        <source>Smart selection + change element type (visual style)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1977"/>
        <source>Move elements</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1978"/>
        <source>Move elements on the map (click-move-click)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1982"/>
        <source>Import picture to element</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1986"/>
        <source>Link a .jpg/.png picture to selected element(s)</source>
        <extracomment>Toolbar tooltip. Static text built once at startup, so there is no count to plug in: &quot;(s)&quot; here just means &quot;one or more&quot;. Render it with whatever generic/plural form reads naturally.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1990"/>
        <source>Clear picture from element</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="1994"/>
        <source>Unlink picture from selected element(s)</source>
        <extracomment>Toolbar tooltip. &quot;Unlink&quot; = detach the picture reference from the element; the image file on disk is NOT deleted. Static text, so &quot;(s)&quot; just means &quot;one or more&quot; - no count is substituted.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2152"/>
        <source>Placing elements</source>
        <extracomment>Error-dialog title. &quot;Placing elements&quot; is FiberQ&apos;s name for the CATEGORY of passive optical elements you drop on the map (ODF, TB, OTB, TO, patch panel, joint closures) - it is the layer-group label, not the -ing action of placing. Treat as a noun phrase.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2176"/>
        <source>Error activating: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2243"/>
        <location filename="../main_plugin.py" line="2238"/>
        <source>Smart selection</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2239"/>
        <source>Click on the elements to select/deselect them. Selections on other layers are not touched.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2254"/>
        <source>Click on cable to show number of cables/types/capacities at that point (right click or ESC to exit).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2287"/>
        <source>Optical schematic</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2297"/>
        <source>Error opening dialog: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2901"/>
        <location filename="../main_plugin.py" line="2896"/>
        <source>Delete</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2897"/>
        <source>No selected features to delete.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2902"/>
        <source>Deleted {count} selected features from all layers.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="2968"/>
        <source>Shortcuts</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3034"/>
        <source>Choose a file with points (KML/KMZ/DWG/Shape/GPX)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3036"/>
        <source>GIS files (*.kml *.kmz *.shp *.dwg *.gpx);;All files (*)</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3044"/>
        <source>Unable to load or invalid file!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3049"/>
        <source>The selected file does not contain points!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3120"/>
        <location filename="../main_plugin.py" line="3116"/>
        <source>Unable to create or find the Poles layer!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3155"/>
        <source>Unable to find the target layer!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3217"/>
        <source>Imported {count} points into layer &apos;{layer}&apos;!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3229"/>
        <source>Please select an active vector layer before exporting.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3240"/>
        <source>There are no selected features on the active layer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3253"/>
        <source>Export format</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3254"/>
        <source>Select output format:</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3282"/>
        <source>Export layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3324"/>
        <source>Unknown driver for extension &apos;{ext}&apos;.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3373"/>
        <source>Error while exporting:
{details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3393"/>
        <source>Export failed: {details}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3406"/>
        <source>Successfully exported the selected features of layer &apos;{layer}&apos;
to:
{path}</source>
        <extracomment>Confirmation shown after exporting ONLY the features the user had selected. {layer} is the source layer name, {path} the written file. Keep as one whole sentence - do not split it.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3412"/>
        <source>Successfully exported all features of layer &apos;{layer}&apos;
to:
{path}</source>
        <extracomment>Confirmation shown after exporting the WHOLE layer (no selection filter). {layer} is the source layer name, {path} the written file. Keep as one whole sentence - do not split it.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3493"/>
        <source>Route correction</source>
        <extracomment>Dialog title for the results of the route-consistency check (e.g. route lines whose ends do not meet a pole). &quot;Route&quot; = the physical cable route/trench on the map, not a road and not a network route. &quot;Correction&quot; is a NOUN: the fixing-up of those defects.</extracomment>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3494"/>
        <source>No errors found!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3508"/>
        <source>Layer &apos;Poles&apos; not found!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3548"/>
        <source>Route layer &apos;Route&apos; not found!</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3558"/>
        <source>Route has been automatically attached to a pole.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../main_plugin.py" line="3718"/>
        <source>Drawing link removed for %n element(s).</source>
        <extracomment>Confirmation after detaching a drawing (a CAD/PDF document attached to an element) from the selected map elements. Only the link is cleared - the drawing file is not deleted. %n is how many elements were actually unlinked; keep %n.</extracomment>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3779"/>
        <source>Placing manhole</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3780"/>
        <source>Click on the map to place the manhole (ESC to exit).</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../main_plugin.py" line="3783"/>
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
<context>
    <name>ValidationPanel</name>
    <message>
        <location filename="../ui/validation_panel.py" line="289"/>
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
    <message>
        <location filename="../ui/validation_panel.py" line="278"/>
        <source>No issues found.</source>
        <translation type="unfinished"></translation>
    </message>
    <message numerus="yes">
        <location filename="../ui/validation_panel.py" line="283"/>
        <source>%n error(s)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../ui/validation_panel.py" line="284"/>
        <source>%n warning(s)</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../ui/validation_panel.py" line="285"/>
        <source>%n info</source>
        <translation type="unfinished">
            <numerusform></numerusform>
            <numerusform></numerusform>
        </translation>
    </message>
    <message numerus="yes">
        <location filename="../ui/validation_panel.py" line="293"/>
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
        <location filename="../core/validation_report.py" line="325"/>
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
        <location filename="../core/validation_report.py" line="298"/>
        <source>Run</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="308"/>
        <source>Rules that failed to run</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="348"/>
        <location filename="../core/validation_report.py" line="314"/>
        <source>Issues</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="316"/>
        <source>No issues found.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="319"/>
        <source>Severity</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="319"/>
        <source>Rule</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="347"/>
        <location filename="../core/validation_report.py" line="319"/>
        <source>Layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="320"/>
        <source>Feature</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="320"/>
        <source>Message</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="324"/>
        <source>Error</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="324"/>
        <source>Warning</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="345"/>
        <source>Issues by layer</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="358"/>
        <source>Generated by the FiberQ QGIS plugin.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_report.py" line="360"/>
        <source>Machine-readable JSON and CSV of the same run are available from the same export menu.</source>
        <translation type="unfinished"></translation>
    </message>
</context>
<context>
    <name>ValidationRules</name>
    <message>
        <location filename="../core/validation_rules.py" line="400"/>
        <source>Cable endpoint is not connected to any element or cable (tolerance {tol})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="431"/>
        <source>Cable endpoint is {distance} from {target} -- just outside the {tol} snapping tolerance; it probably should connect</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="486"/>
        <source>Element is not on or near any cable or route (tolerance {tol})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="547"/>
        <source>Referenced cable layer {layer_id} is not in the project</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="552"/>
        <source>Referenced cable feature {fid} does not exist in layer {layer}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="586"/>
        <source>Feature is {distance} from the cable it references (tolerance {tol}) -- the cable may have been re-routed</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="616"/>
        <source>Layer is missing the fiberq_uuid identity field</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="619"/>
        <source>Re-open the project so migration can add fiberq_uuid, or re-create the layer.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="630"/>
        <source>Feature has no fiberq_uuid value</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="639"/>
        <source>Duplicate fiberq_uuid — the same identity is already used by feature {fid} in layer {layer}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="668"/>
        <source>No FiberQ layers found in this project, so nothing was checked.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="674"/>
        <source>Open a FiberQ project, or create the layers with the FiberQ toolbar.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="697"/>
        <source>Required field(s) missing or empty: {fields}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="737"/>
        <source>Field {field}: value {value} is not one of the allowed values ({allowed})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="805"/>
        <source>Field {field}: {value} is out of range (expected {bound})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="888"/>
        <source>Length checks skipped: they need either a projected CRS or a project ellipsoid, but this layer uses {crs} with none set</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="913"/>
        <source>Stored {field} ({stored}) does not match the drawn geometry ({computed})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="936"/>
        <source>total_len_m ({total}) should equal duzina_m + slack_m ({expected})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="965"/>
        <source>duzina_km ({km}) does not match duzina/1000 ({expected})</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="998"/>
        <source>Layer uses a geographic CRS ({crs}), where the connectivity tolerance is measured in degrees rather than metres</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1006"/>
        <source>Reproject to a national grid, or lower the tolerance to a fraction of a degree.</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1015"/>
        <source>No ellipsoid could be resolved for {crs}, so lengths cannot be checked</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1027"/>
        <source>FiberQ layers do not all share one CRS: {list}</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1059"/>
        <source>Feature has no geometry</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1072"/>
        <source>Line has zero length</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1076"/>
        <source>Line crosses itself</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1081"/>
        <source>Polygon has zero area</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1083"/>
        <source>Polygon boundary is self-intersecting</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1107"/>
        <source>Cable endpoints are connected</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1115"/>
        <source>Cable endpoints are not near-misses</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1123"/>
        <source>Elements are attached to the network</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1131"/>
        <source>Optical slack references an existing cable</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1139"/>
        <source>Fiber break references an existing cable</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1147"/>
        <source>Cable references are spatially coherent</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1155"/>
        <source>Feature identity present and unique</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1162"/>
        <source>Required attributes present</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1169"/>
        <source>Project contains FiberQ layers</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1176"/>
        <source>Attribute values within allowed domain</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1183"/>
        <source>Numeric attributes within plausible ranges</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1190"/>
        <source>Stored lengths agree with geometry</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1198"/>
        <source>Coordinate reference systems are consistent</source>
        <translation type="unfinished"></translation>
    </message>
    <message>
        <location filename="../core/validation_rules.py" line="1205"/>
        <source>Geometries are present and well formed</source>
        <translation type="unfinished"></translation>
    </message>
</context>
</TS>
