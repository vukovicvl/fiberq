# pyright: reportMissingImports=false, reportMissingModuleSource=false
"""FiberQ Optical Schematic Dialog.

This module contains the optical schematic view dialog for visualizing
fiber network topology with filtering, search, and export capabilities.
"""

from qgis.PyQt.QtCore import Qt, QStringListModel, QTimer, QSize, QRect
from qgis.PyQt.QtGui import QPen, QColor, QPainterPath, QFont
from qgis.PyQt.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QCheckBox,
    QSpinBox,
    QToolButton,
    QFrame,
    QWidget,
    QGraphicsView,
    QGraphicsScene,
    QCompleter,
    QFileDialog,
)

from qgis.core import (
    QgsVectorLayer,
    QgsProject,
    QgsWkbTypes,
    QgsPointXY,
    QgsCoordinateTransform,
)

# Phase 5.2: Logging
from ..utils.logger import get_logger
logger = get_logger(__name__)


class SchematicView(QGraphicsView):
    """QGraphicsView with practical zooming and panning.

    Pan modes:
    - Middle mouse button drag (always works)
    - Left mouse drag when Pan button is toggled on
    - Wheel zoom centered on mouse
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from qgis.PyQt.QtGui import QPainter
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        # We do NOT use Qt's built-in ScrollHandDrag here because its
        # left-button drag dispatch behaves differently on Qt5 vs Qt6.
        # Instead we set NoDrag and handle pan explicitly in the mouse
        # event overrides below — this works identically on both Qt
        # versions.
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setInteractive(True)
        self._panning = False
        self._pan_start = None
        self._pan_mode = True  # True when the Pan toolbar button is toggled on

    def set_pan_mode(self, on: bool):
        """Called by OpticalSchematicDialog when the Pan button is toggled."""
        self._pan_mode = bool(on)
        if on:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def wheelEvent(self, event):
        """Zoom with mouse wheel."""
        factor = 1.15 if event.angleDelta().y() > 0 else 1/1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event):
        """Start panning on middle-button press, or on left-button press
        when Pan mode is active."""
        btn = event.button()
        if btn == Qt.MouseButton.MiddleButton or (self._pan_mode and btn == Qt.MouseButton.LeftButton):
            self._panning = True
            self._pan_start = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Apply pan delta while dragging. Scroll-bar setValue requires int
        on PyQt6 (stricter than PyQt5), so we cast the deltas."""
        if self._panning and self._pan_start is not None:
            cur = event.pos()
            delta = cur - self._pan_start
            self._pan_start = cur
            hbar = self.horizontalScrollBar()
            vbar = self.verticalScrollBar()
            hbar.setValue(hbar.value() - int(delta.x()))
            vbar.setValue(vbar.value() - int(delta.y()))
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Stop panning."""
        btn = event.button()
        if self._panning and (btn == Qt.MouseButton.MiddleButton or btn == Qt.MouseButton.LeftButton):
            self._panning = False
            self._pan_start = None
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._pan_mode else Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)


class OpticalSchematicDialog(QDialog):
    """
    Optical schematic view with:
      - pan/zoom (wheel, Pan toggle, Zoom+/Zoom-, Fit)
      - filters (backbone/distributive/drop, underground/aerial, capacity, relation, show labels)
      - search and centering on element
      - layout rule: OR → backbone (axis), branches downward
      - mini color legend
      - export PNG/SVG
    """

    def __init__(self, core):
        super().__init__(core.iface.mainWindow())
        self.core = core
        self.setWindowTitle("Optical Schematic View")
        self.resize(1200, 760)

        # Scene & View
        self.scene = QGraphicsScene(self)
        self.view = SchematicView(self.scene, self)

        # --- Top bar: controls ---
        top = QHBoxLayout()

        # Pan / Zoom controls
        self.btn_pan = QToolButton()
        self.btn_pan.setText("Pan")
        self.btn_pan.setCheckable(True)
        self.btn_pan.setChecked(True)  # Issue #4: Enable pan by default
        self.btn_pan.toggled.connect(self._toggle_pan)
        # Ensure SchematicView picks up the initial checked state (setChecked
        # before connect() does not emit toggled on either Qt5 or Qt6).
        self._toggle_pan(self.btn_pan.isChecked())
        self.btn_zoom_in = QPushButton("Zoom +")
        self.btn_zoom_in.clicked.connect(lambda: self.view.scale(1.25, 1.25))
        self.btn_zoom_out = QPushButton("Zoom −")
        self.btn_zoom_out.clicked.connect(lambda: self.view.scale(0.8, 0.8))
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.clicked.connect(self._fit)

        # Type filters
        self.chk_glavni = QCheckBox("Backbone")
        self.chk_glavni.setChecked(True)
        self.chk_distrib = QCheckBox("Distributive")
        self.chk_distrib.setChecked(True)
        self.chk_razvod = QCheckBox("Drop")
        self.chk_razvod.setChecked(True)
        self.chk_podzemni = QCheckBox("Underground")
        self.chk_podzemni.setChecked(True)
        self.chk_vazdusni = QCheckBox("Aerial")
        self.chk_vazdusni.setChecked(True)
        self.chk_labels = QCheckBox("Show labels")
        self.chk_labels.setChecked(True)
        self.chk_map_layout = QCheckBox("Match map styling")
        self.chk_map_layout.setChecked(False)

        # Capacity/relation filters
        self.cap_min = QSpinBox()
        self.cap_min.setPrefix("Cap ≥ ")
        self.cap_min.setMaximum(9999)
        self.cap_min.setValue(0)
        self.cap_max = QSpinBox()
        self.cap_max.setPrefix("Cap ≤ ")
        self.cap_max.setMaximum(9999)
        self.cap_max.setValue(0)
        self.txt_rel = QLineEdit()
        self.txt_rel.setPlaceholderText("Relation contains…")

        # Search / centering
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("Find element…")
        self.btn_center = QPushButton("Center")
        self.btn_center.clicked.connect(self._center_on_query)
        self._completer = QCompleter([])
        self._completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.txt_search.setCompleter(self._completer)

        # Apply/refresh + export buttons
        self.btn_apply = QPushButton("Apply")
        self.btn_apply.clicked.connect(self.rebuild)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.rebuild)
        self.btn_png = QPushButton("PNG")
        self.btn_png.clicked.connect(self._export_png)
        self.btn_jpg = QPushButton("JPG")
        self.btn_jpg.clicked.connect(self._export_jpg)
        self.btn_svg = QPushButton("SVG")
        self.btn_svg.clicked.connect(self._export_svg)

        for w in [self.btn_pan, self.btn_zoom_in, self.btn_zoom_out, self.btn_fit, self.chk_map_layout,
                  self.chk_glavni, self.chk_distrib, self.chk_razvod,
                  self.chk_podzemni, self.chk_vazdusni, self.chk_labels,
                  self.cap_min, self.cap_max, self.txt_rel,
                  self.txt_search, self.btn_center,
                  self.btn_apply, self.btn_refresh, self.btn_png, self.btn_jpg, self.btn_svg]:
            top.addWidget(w)
        top.addStretch()

        # --- Legend (small bar) ---
        legend = QHBoxLayout()
        legend.addWidget(QLabel("Legend:"))

        def swatch(color, text):
            box = QFrame()
            box.setFixedSize(20, 10)
            box.setStyleSheet("background:%s; border:1px solid #333;" % color)
            legend.addWidget(box)
            legend.addWidget(QLabel(text))

        swatch("#003399", "Backbone")
        swatch("#cc0000", "Distributive")
        swatch("#a52a2a", "Drop")
        swatch("#ff8c00", "Pipes")
        legend_w = QWidget()
        legend_w.setLayout(legend)

        lay = QVBoxLayout(self)
        lay.addLayout(top)
        lay.addWidget(legend_w)
        lay.addWidget(self.view)

        # Debounce timer for automatic rebuild
        self._rebuild_timer = QTimer(self)
        self._rebuild_timer.setSingleShot(True)
        self._rebuild_timer.setInterval(400)  # ms
        self._rebuild_timer.timeout.connect(self._do_rebuild_if_needed)
        self._rebuild_pending = False

        # Auto-refresh
        self._wired_layers = set()
        self._wire_all_layers()

        self.rebuild()

    # ---------- UTIL ----------
    def _toggle_pan(self, on):
        # Explicit pan-mode flag — SchematicView handles left-button drag
        # manually so the behaviour is identical on Qt5 and Qt6.
        self.view.set_pan_mode(bool(on))

    def _fit(self):
        rect = self.scene.itemsBoundingRect().adjusted(-40, -40, 40, 40)
        self.view.setSceneRect(rect)
        self.view.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def _parse_capacity(self, value):
        """Extract first number from capacity; if no number, return None."""
        import re as _re
        if value is None:
            return None
        m = _re.search(r'\d+', str(value))
        return int(m.group(0)) if m else None

    def _center_on_query(self):
        name = self.txt_search.text().strip()
        if name:
            self._center_on(name)

    def _center_on(self, name):
        pos = getattr(self, "_last_positions", {})
        if name in pos:
            x, y = pos[name]
            self.view.centerOn(x, y)
            # highlight momentarily
            r = 12.0
            item = self.scene.addEllipse(x-r, y-r, 2*r, 2*r, QPen(QColor(255,165,0), 2.4), Qt.BrushStyle.NoBrush)
            item.setZValue(10)
            def _remove():
                self.scene.removeItem(item)
            QTimer.singleShot(1300, _remove)

    # ---------- DATA ----------
    def _collect_nodes(self):
        nodes = {}
        for lyr in QgsProject.instance().mapLayers().values():
            try:
                if isinstance(lyr, QgsVectorLayer) and lyr.geometryType() == QgsWkbTypes.PointGeometry:
                    lname = lyr.name()
                    fields = lyr.fields()
                    has_naziv = fields.indexFromName('naziv') != -1

                    is_manhole_layer = lname in ('OKNA', 'Manholes')
                    has_broj_okna = (
                        fields.indexFromName('broj_okna') != -1
                        if is_manhole_layer
                        else False
                    )

                    for f in lyr.getFeatures():
                        nm = None
                        # 1) Manholes (OKNA): MH + broj_okna
                        if is_manhole_layer and has_broj_okna:
                            val = f['broj_okna']
                            if val is not None and str(val).strip():
                                nm = f"MH {str(val).strip()}"  # Issue #9: KO -> MH

                        # 2) other layers with 'naziv' field
                        if nm is None and has_naziv:
                            val = f['naziv']
                            if val is not None and str(val).strip():
                                nm = str(val).strip()

                        # 3) Poles fallback
                        if nm is None and lname == 'Poles':
                            try:
                                tip = (
                                    str(f['tip']).strip()
                                    if fields.indexFromName('tip') != -1 and f['tip'] is not None
                                    else ''
                                )
                            except Exception as e:
                                tip = ''
                            nm = ("Pole " + tip).strip() or f"Pole {int(f.id())}"  # Stub -> Pole

                        if nm and nm not in nodes:
                            nodes[nm] = {
                                "layer_id": lyr.id(),
                                "layer_name": lname,
                                "fid": int(f.id()),
                            }
            except Exception as e:
                continue
        return nodes

    def _collect_edges(self):
        """List all cables + read attributes from layer; returns list of dicts."""
        items = self.core.list_all_cables() + self.core.list_all_pipes()
        edges = []
        for it in items:
            lyr = QgsProject.instance().mapLayer(it.get('layer_id'))
            if not lyr or not isinstance(lyr, QgsVectorLayer):
                continue
            feat = None
            for _f in lyr.getFeatures():
                if int(_f.id()) == int(it.get('fid')):
                    feat = _f
                    break
            if not feat:
                continue

            geom = feat.geometry()
            # collect geometry coordinates (transformed to project CRS)
            try:
                srcCrs = lyr.crs()
                dstCrs = QgsProject.instance().crs()
                xform = QgsCoordinateTransform(srcCrs, dstCrs, QgsProject.instance())
                coords = []
                if geom.isMultipart():
                    parts = geom.asMultiPolyline()
                    for pl in parts:
                        for p in pl:
                            pt = xform.transform(QgsPointXY(p.x(), p.y()))
                            coords.append((pt.x(), pt.y()))
                else:
                    pl = geom.asPolyline()
                    for p in pl:
                        pt = xform.transform(QgsPointXY(p.x(), p.y()))
                        coords.append((pt.x(), pt.y()))
            except Exception as e:
                coords = []
            try:
                length_m = float(geom.length())
            except Exception as e:
                length_m = 0.0

            lname = (it.get('layer_name') or lyr.name() or '').lower()
            vrsta = 'vazdusni' if ('vazdu' in lname or 'aerial' in lname) else 'podzemni'

            # Attributes: take from 'it' if available, otherwise from feature fields
            def gv(key):
                if it.get(key) not in (None, ''):
                    return it.get(key)
                idx = lyr.fields().indexFromName(key)
                return feat[key] if idx != -1 else ''

            # Detect pipe (vs cable) by source layer name so the schematic
            # can render them and skip cable-only filters. Layer names cover
            # both English ("PE pipes", "Transition pipes", "PE ducts",
            # "Transition ducts") and legacy Serbian ("PE cevi", "Prelazne cevi").
            raw_lname = (it.get('layer_name') or lyr.name() or '')
            low_lname = raw_lname.lower()
            is_pipe = (
                'cevi' in low_lname
                or 'pipe' in low_lname
                or 'duct' in low_lname
                or (it.get('tip') or '').lower() == 'pipe'
            )

            edges.append({
                "from": str(gv('od')).strip(),
                "to":   str(gv('do')).strip(),
                "podtip": str(gv('podtip')).lower(),
                "kapacitet": gv('kapacitet'),
                "geom_coords": coords,
                "length": length_m,
                "vrsta": vrsta,
                "relacija": str(gv('relacija')).lower(),
                "is_pipe": is_pipe,
                "layer_name": raw_lname,
            })
        return edges

    # ---------- LAYOUT ----------
    def _rank_for_layer(self, layer_name: str):
        lname = (layer_name or "").lower()
        if lname.strip() == "or":
            return 0
        if "nastav" in lname:
            return 1
        return 2

    def _main_chain_from_or(self, nodes, edges):
        # adjacency for 'glavni'
        adj = {}
        for e in edges:
            if e['podtip'] != 'glavni':
                continue
            a, b = e['from'], e['to']
            if not a or not b:
                continue
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)

        if not adj:
            return []

        layer_by_name = {n: nodes[n]['layer_name'] for n in nodes}
        or_nodes = [n for n in adj if self._rank_for_layer(layer_by_name.get(n, "")) == 0]
        start = max(or_nodes, key=lambda n: len(adj.get(n, []))) if or_nodes else max(adj, key=lambda n: len(adj.get(n, [])))

        chain = []
        visited = set()
        cur = start
        prev = None
        while cur is not None:
            chain.append(cur)
            visited.add(cur)
            nxts = [n for n in adj.get(cur, []) if n != prev]
            if not nxts:
                break
            prev, cur = cur, nxts[0]
        return chain

    def _build_layout(self, nodes, edges):
        """Filtering + node positions + ortho-polylines for branches."""
        # Filters subtype/kind
        keep_podtip = {
            t for t, chk in [
                ('glavni', self.chk_glavni),
                ('distributivni', self.chk_distrib),
                ('razvodni', self.chk_razvod),
            ]
            if chk.isChecked()
        }
        keep_vrsta = {
            t for t, chk in [
                ('podzemni', self.chk_podzemni),
                ('vazdusni', self.chk_vazdusni),
            ]
            if chk.isChecked()
        }

        # Relation filter
        rel_q = self.txt_rel.text().strip().lower()
        # Capacity filter
        cap_min = self.cap_min.value() or 0
        cap_max = self.cap_max.value() or 0  # 0 = no upper bound

        def pass_filters(e):
            # Pipes (PE / transition ducts) don't have cable subtypes like
            # glavni/distributivni/razvodni and aren't aerial/underground
            # cables, so they fail the cable filters and vanish from the
            # schematic. Keep them in based on the "Show pipes" state of
            # the aerial/underground checkboxes (pipes count as underground
            # infrastructure by convention) and skip the cable-only checks.
            if e.get('is_pipe'):
                if not self.chk_podzemni.isChecked():
                    return False
                if rel_q and rel_q not in (e.get('relacija') or ''):
                    return False
                return bool(e['from']) and bool(e['to'])
            if e['podtip'] not in keep_podtip or e['vrsta'] not in keep_vrsta:
                return False
            if rel_q and rel_q not in (e.get('relacija') or ''):
                return False
            cap_val = self._parse_capacity(e.get('kapacitet'))
            if cap_min and (cap_val is None or cap_val < cap_min):
                return False
            if cap_max and (cap_val is not None and cap_val > cap_max):
                return False
            return e['from'] and e['to']

        edges_f = [e for e in edges if pass_filters(e)]

        # --- MAP LAYOUT: use real coordinates from map ---
        if getattr(self, 'chk_map_layout', None) and self.chk_map_layout.isChecked():
            # Prepare node positions from centroids/points
            pos = {}
            world_points = []
            for name, info in nodes.items():
                try:
                    lyr = QgsProject.instance().mapLayer(info.get('layer_id'))
                    fid = int(info.get('fid'))
                    feat = next((f for f in lyr.getFeatures() if int(f.id()) == fid), None)
                    if not feat:
                        continue
                    g = feat.geometry()
                    # Extract one representative point
                    pt = None
                    if g.isEmpty():
                        continue
                    if g.type() == QgsWkbTypes.PointGeometry:
                        pt = g.asPoint()
                    elif g.type() == QgsWkbTypes.LineGeometry:
                        try:
                            d = g.length()
                            pt = g.interpolate(d / 2.0).asPoint()
                        except Exception as e:
                            ps = g.asPolyline()
                            pt = ps[len(ps) // 2] if ps else None
                    else:
                        try:
                            pt = g.centroid().asPoint()
                        except Exception as e:
                            pt = None
                    if pt is None:
                        continue
                    # transform to project CRS
                    src = lyr.crs()
                    dst = QgsProject.instance().crs()
                    tr = QgsCoordinateTransform(src, dst, QgsProject.instance())
                    ptt = tr.transform(QgsPointXY(pt.x(), pt.y()))
                    pos[name] = (ptt.x(), ptt.y())
                    world_points.append((ptt.x(), ptt.y()))
                except Exception as e:
                    continue

            # Add all points from cable/pipe geometry
            for e in edges_f:
                coords = e.get('geom_coords') or []
                for x, y in coords:
                    world_points.append((x, y))

            # If no points, return empty layout
            if not world_points:
                return {}, []

            minx = min(x for x, _ in world_points)
            maxx = max(x for x, _ in world_points)
            miny = min(y for _, y in world_points)
            maxy = max(y for _, y in world_points)
            w = max(1.0, maxx - minx)
            h = max(1.0, maxy - miny)
            target_w, target_h = 1600.0, 1000.0
            scale = min(target_w / w, target_h / h)
            pad = 20.0

            def tx(x, y):
                # keep north up (invert Y for QGraphics)
                X = (x - minx) * scale + pad
                Y = (maxy - y) * scale + pad
                return (X, Y)

            # transform node positions
            pos = {name: tx(x, y) for name, (x, y) in pos.items()}

            # build line paths based on original geometry
            lines = []
            for e in edges_f:
                coords = e.get('geom_coords') or []
                if coords:
                    path = [tx(x, y) for (x, y) in coords]
                else:
                    a = pos.get(e.get('from'))
                    b = pos.get(e.get('to'))
                    if not a or not b:
                        continue
                    path = [a, b]
                lines.append((e, path))

            # save positions for search
            self._last_positions = pos
            try:
                model = self._completer.model()
                if not isinstance(model, QStringListModel):
                    model = QStringListModel()
                    self._completer.setModel(model)
                model.setStringList(sorted(pos.keys()))
            except Exception as e:
                logger.debug(f"Error in OpticalSchematicDialog.tx: {e}")

            return pos, lines

        # ---------- SCHEMATIC LAYOUT (without 'Match map styling') ----------

        # Indices by nodes
        by_from = {}
        for e in edges_f:
            by_from.setdefault(e['from'], []).append(e)
            by_from.setdefault(e['to'], []).append({**e, 'from': e['to'], 'to': e['from']})

        # Main axis (OR chain by backbone cables)
        main_nodes = self._main_chain_from_or(nodes, edges_f)
        pos = {}
        x_step = 190.0
        y_step = 140.0

        if main_nodes:
            # --- Backbone cables exist: keep old algorithm ---
            for i, n in enumerate(main_nodes):
                pos[n] = (i * x_step, 0.0)

            # Branches downward
            branch_rank = {'distributivni': 0, 'razvodni': 1}
            taken = set()
            for src in main_nodes:
                outs = [e for e in by_from.get(src, []) if e['podtip'] != 'glavni']
                outs.sort(key=lambda e: branch_rank.get(e['podtip'], 99))
                col = 0
                for e in outs:
                    child = e['to']
                    if (src, child) in taken:
                        continue
                    taken.add((src, child))
                    taken.add((child, src))
                    bx, by = pos[src]
                    x = bx + 35 + col * 26
                    chain = [src, child]
                    seen = set(chain)
                    cur = child
                    while True:
                        nxts = [
                            ed for ed in by_from.get(cur, [])
                            if ed['podtip'] != 'glavni' and ed['to'] not in seen
                        ]
                        if not nxts:
                            break
                        cur = nxts[0]['to']
                        chain.append(cur)
                        seen.add(cur)
                    for j, node_name in enumerate(chain[1:], start=1):
                        pos[node_name] = (x, -j * y_step)
                    col += 1

            # Uninitialized nodes – right of main axis
            leftovers = [n for n in nodes.keys() if n not in pos]
            leftovers.sort(
                key=lambda n: (self._rank_for_layer(nodes[n].get('layer_name', '')), n)
            )
            for i, n in enumerate(leftovers, start=1):
                pos[n] = (len(main_nodes) * x_step + (i // 8) * x_step,
                          -(i % 8) * y_step)
        else:
            # --- NO backbone cables: group by components ---
            # adj list by all cables (regardless of subtype)
            adj = {}
            for e in edges_f:
                a, b = e['from'], e['to']
                if not a or not b:
                    continue
                adj.setdefault(a, set()).add(b)
                adj.setdefault(b, set()).add(a)
            # ensure isolated nodes also appear
            for n in nodes.keys():
                adj.setdefault(n, set())

            # split into components
            visited = set()
            components = []

            for n in nodes.keys():
                if n in visited:
                    continue
                stack = [n]
                comp = []
                while stack:
                    cur = stack.pop()
                    if cur in visited:
                        continue
                    visited.add(cur)
                    comp.append(cur)
                    for nb in adj.get(cur, []):
                        if nb not in visited:
                            stack.append(nb)
                components.append(comp)

            def node_sort_key(nn):
                return (self._rank_for_layer(nodes[nn].get('layer_name', '')), nn)

            # sort components by "most important" node
            components.sort(key=lambda comp: min(node_sort_key(nn) for nn in comp))

            # each component gets its own column
            for ci, comp in enumerate(components):
                comp_sorted = sorted(comp, key=node_sort_key)
                x = ci * x_step
                for j, n in enumerate(comp_sorted):
                    pos[n] = (x, -j * y_step)

        # Polylines
        lines = []
        for e in edges_f:
            a, b = e['from'], e['to']
            if a in pos and b in pos:
                ax, ay = pos[a]
                bx, by = pos[b]
                midy = (ay + by) / 2.0
                path = [(ax, ay), (ax, midy), (bx, midy), (bx, by)]
                lines.append((e, path))

        # remember for search
        self._last_positions = pos
        # refresh completer
        try:
            model = self._completer.model()
            if not isinstance(model, QStringListModel):
                model = QStringListModel()
                self._completer.setModel(model)
            model.setStringList(sorted(pos.keys()))
        except Exception as e:
            logger.debug(f"Error in OpticalSchematicDialog.node_sort_key: {e}")

        return pos, lines

    # ---------- DRAWING ----------
    def rebuild(self):
        self.scene.clear()
        nodes = self._collect_nodes()
        edges = self._collect_edges()
        pos, lines = self._build_layout(nodes, edges)

        def color_for(e):
            t = (e.get('podtip') or '').lower()
            lname = (e.get('layer_name') or '').lower()
            if 'glavni' in t:
                return QColor(0, 51, 153)
            if 'distribut' in t:
                return QColor(204, 0, 0)
            if 'razvod' in t:
                return QColor(165, 42, 42)
            if 'cev' in t or 'cevi' in lname:
                return QColor(255, 140, 0)
            return QColor(60, 60, 60)

        # label collision avoidance
        occupied = []

        def place_text(x, y, txt, color):
            if not txt:
                return
            ti = self.scene.addText(txt, QFont("Arial", 9))
            ti.setDefaultTextColor(color)
            offsets = [(8, -8), (10, 10), (-22, -10), (-22, 12), (8, 12), (12, 0)]
            for dx, dy in offsets:
                ti.setPos(x + dx, y + dy)
                rect = ti.mapRectToScene(ti.boundingRect())
                if not any(rect.intersects(r) for r in occupied):
                    bg = rect.adjusted(-2, -1, 2, 2)
                    self.scene.addRect(bg, QPen(Qt.PenStyle.NoPen), QColor(255,255,255,210)).setZValue(ti.zValue()-1)
                    occupied.append(bg)
                    return
            occupied.append(ti.mapRectToScene(ti.boundingRect()))

        # branches + labels
        for e, path in lines:
            pen = QPen(color_for(e))
            pen.setWidthF(2.2)
            # Pipes – draw dashed for easier distinction
            try:
                if e.get('is_pipe'):
                    pen.setStyle(Qt.PenStyle.DashLine)
            except Exception as _err:
                logger.debug(f"Error applying pipe dash style: {_err}")
            gp = QPainterPath()
            x0, y0 = path[0]
            gp.moveTo(x0, y0)
            for x, y in path[1:]:
                gp.lineTo(x, y)
            self.scene.addPath(gp, pen)
            if self.chk_labels.isChecked():
                mid_idx = len(path) // 2
                mx, my = path[mid_idx]
                text = f"{e.get('kapacitet','')}".strip()
                if e.get('length', 0.0):
                    text = (text + (" / " if text else "")) + f"{round(e['length'],1)} m"
                place_text(mx, my, text, pen.color())

        # nodes + labels
        for name, meta in nodes.items():
            x, y = pos.get(name, (0.0, 0.0))
            r = 6.0
            self.scene.addEllipse(x-r, y-r, 2*r, 2*r, QPen(Qt.GlobalColor.black), QColor(240,240,240))
            if self.chk_labels.isChecked():
                place_text(x, y, str(name), QColor(10,10,10))

        self._fit()

    # ---------- EXPORT ----------
    def _export_png(self):
        from qgis.PyQt.QtGui import QImage, QPainter
        rect = self.scene.itemsBoundingRect().adjusted(10,10,10,10)
        img = QImage(int(rect.width())+40, int(rect.height())+40, QImage.Format.Format_ARGB32)
        img.fill(0x00ffffff)
        p = QPainter(img)
        p.translate(-rect.x()+20, -rect.y()+20)
        self.scene.render(p)
        p.end()
        fn, _ = QFileDialog.getSaveFileName(self, "Save PNG", "optical_schematic.png", "PNG (*.png)")
        if fn:
            img.save(fn, "PNG")

    def _export_jpg(self):
        from qgis.PyQt.QtGui import QImage, QPainter
        rect = self.scene.itemsBoundingRect().adjusted(10,10,10,10)
        img = QImage(int(rect.width())+40, int(rect.height())+40, QImage.Format.Format_RGB32)
        img.fill(0xffffffff)
        p = QPainter(img)
        p.translate(-rect.x()+20, -rect.y()+20)
        self.scene.render(p)
        p.end()
        fn, _ = QFileDialog.getSaveFileName(self, "Save JPG", "optical_schematic.jpg", "JPG (*.jpg)")
        if fn:
            img.save(fn, "JPG")

    def _export_svg(self):
        try:
            from qgis.PyQt.QtSvg import QSvgGenerator
            from qgis.PyQt.QtGui import QPainter

        except Exception as e:
            return
        rect = self.scene.itemsBoundingRect().adjusted(10,10,10,10)
        fn, _ = QFileDialog.getSaveFileName(self, "Save SVG", "optical_schematic.svg", "SVG (*.svg)")
        if not fn:
            return
        gen = QSvgGenerator()
        gen.setFileName(fn)
        gen.setSize(QSize(int(rect.width())+40, int(rect.height())+40))
        gen.setViewBox(QRect(0,0,int(rect.width())+40,int(rect.height())+40))
        p = QPainter(gen)
        p.translate(-rect.x()+20, -rect.y()+20)
        self.scene.render(p)
        p.end()

    def _schedule_rebuild(self):
        """Debounced rebuild – used for automatic layer changes."""
        try:
            self._rebuild_pending = True
            if getattr(self, "_rebuild_timer", None) is not None:
                # restart timer – multiple changes in short time -> one rebuild
                self._rebuild_timer.start()
            else:
                # fallback, if no timer
                self._rebuild_pending = False
                self.rebuild()
        except Exception as e:
            # if something goes wrong, don't block – do direct rebuild
            self._rebuild_pending = False
            self.rebuild()

    def _do_rebuild_if_needed(self):
        """Called from QTimer.timeout – actually rebuilds if needed."""
        if not getattr(self, "_rebuild_pending", False):
            return
        self._rebuild_pending = False
        self.rebuild()

    # ---------- SIGNALS ----------
    def _wire_all_layers(self):
        prj = QgsProject.instance()
        try:
            prj.layersAdded.connect(lambda *_: self._schedule_rebuild())
            prj.layerWillBeRemoved.connect(lambda *_: self._schedule_rebuild())
        except Exception as e:
            logger.debug(f"Error in OpticalSchematicDialog._wire_all_layers: {e}")
        for lyr in QgsProject.instance().mapLayers().values():
            self._wire_layer(lyr)

    def _layer_committed(self, *args, **kwargs):
        # instead of direct rebuild, do debounce
        self._schedule_rebuild()

    def _wire_layer(self, lyr):
        if not isinstance(lyr, QgsVectorLayer):
            return
        if lyr.id() in getattr(self, "_wired_layers", set()):
            return
        self._wired_layers.add(lyr.id())
        try:
            lyr.committedFeaturesAdded.connect(self._layer_committed)
            lyr.committedFeaturesRemoved.connect(self._layer_committed)
            lyr.committedAttributeValuesChanges.connect(self._layer_committed)
            lyr.committedGeometriesChanges.connect(self._layer_committed)
            lyr.layerModified.connect(self._layer_committed)
        except Exception as e:
            logger.debug(f"Error in OpticalSchematicDialog._wire_layer: {e}")


__all__ = ['SchematicView', 'OpticalSchematicDialog']
