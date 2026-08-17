"""FiberQ validation results panel (WP2, task 2.1 - UI).

A dockable list of :class:`~fiberq.core.validation_manager.ValidationIssue`, with
severity/layer/rule filters, live counts, a Re-run button and click-to-zoom.

This is the first QDockWidget in the plugin, so it sets the pattern: the widget
owns no validation logic and never touches QgsProject. It renders a
``ValidationResult`` and emits signals; the plugin decides what running and
zooming actually mean. That keeps the panel constructible (and testable) without
a live project.

i18n: ``tr()`` below must keep the context string equal to the class name --
pylupdate6 derives the catalogue context from the enclosing class, so renaming
the class without renaming the context silently reverts every string to English.
"""
from qgis.PyQt.QtCore import QT_TRANSLATE_NOOP, QCoreApplication, Qt, pyqtSignal
from qgis.PyQt.QtGui import QBrush, QColor
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..core.validation_manager import SEVERITY_ORDER, Severity
from ..i18n import safe_format
from ..utils.logger import get_logger

logger = get_logger(__name__)

#: Foreground colours per severity. Chosen to stay legible on both the light and
#: dark QGIS themes (mid-tones rather than saturated primaries).
_SEVERITY_COLOUR = {
    Severity.ERROR: QColor(200, 60, 60),
    Severity.WARNING: QColor(200, 140, 30),
    Severity.INFO: QColor(90, 140, 200),
}

_ALL = "__all__"  # sentinel stored as combo item data; never displayed

#: Item data roles for values that must sort differently from how they display.
_ROLE_ISSUE = Qt.ItemDataRole.UserRole
_ROLE_RANK = Qt.ItemDataRole.UserRole + 1


class _IssueItem(QTreeWidgetItem):
    """A row that sorts on meaning rather than on displayed text.

    Column 0 shows a translated severity label, so the default string sort would
    order Error/Warning/Info differently in every language; it sorts on the
    numeric severity rank instead. Column 3 holds a feature id, where a string
    sort puts "10" before "9".
    """

    def __lt__(self, other):
        tree = self.treeWidget()
        column = tree.sortColumn() if tree is not None else 0
        if column == 0:
            mine = self.data(0, _ROLE_RANK)
            theirs = other.data(0, _ROLE_RANK)
            if mine is not None and theirs is not None:
                return mine < theirs
        if column == 3:
            try:
                return int(self.text(3) or -1) < int(other.text(3) or -1)
            except (TypeError, ValueError):
                pass
        return super().__lt__(other)


class ValidationPanel(QDockWidget):
    """Dockable results list for a validation run."""

    #: The user asked for the validation to run again.
    rerunRequested = pyqtSignal()
    #: The user activated an issue (wants the map to go there). Carries the
    #: ValidationIssue; typed as ``object`` because it is a plain dataclass.
    issueActivated = pyqtSignal(object)
    #: The user asked to export the current result.
    exportRequested = pyqtSignal()

    def tr(self, message, disambiguation=None, n=-1):
        """Context must stay equal to the class name (pylupdate6 keys on it)."""
        return QCoreApplication.translate(
            'ValidationPanel', message, disambiguation, n)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('FiberQValidationPanel')
        self.setWindowTitle(self.tr('FiberQ validation'))

        self._issues = []
        self._result = None

        body = QWidget(self)
        outer = QVBoxLayout(body)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.setSpacing(6)

        # --- summary + actions -------------------------------------------------
        top = QHBoxLayout()
        self.lbl_summary = QLabel(self.tr('No validation run yet.'), body)
        self.lbl_summary.setWordWrap(True)
        top.addWidget(self.lbl_summary, 1)

        self.btn_rerun = QPushButton(self.tr('Re-run'), body)
        self.btn_rerun.setToolTip(self.tr('Validate the project again'))
        self.btn_rerun.clicked.connect(self.rerunRequested)
        top.addWidget(self.btn_rerun, 0)

        self.btn_export = QPushButton(self.tr('Export report…'), body)
        self.btn_export.setToolTip(self.tr('Save the results as a report'))
        self.btn_export.clicked.connect(self.exportRequested)
        self.btn_export.setEnabled(False)
        top.addWidget(self.btn_export, 0)
        outer.addLayout(top)

        # --- filters -----------------------------------------------------------
        filters = QHBoxLayout()
        filters.addWidget(QLabel(self.tr('Severity:'), body), 0)
        self.cb_severity = QComboBox(body)
        filters.addWidget(self.cb_severity, 0)

        filters.addWidget(QLabel(self.tr('Layer:'), body), 0)
        self.cb_layer = QComboBox(body)
        filters.addWidget(self.cb_layer, 1)

        filters.addWidget(QLabel(self.tr('Rule:'), body), 0)
        self.cb_rule = QComboBox(body)
        filters.addWidget(self.cb_rule, 0)
        filters.addStretch(1)
        outer.addLayout(filters)

        for combo in (self.cb_severity, self.cb_layer, self.cb_rule):
            combo.currentIndexChanged.connect(self._apply_filters)

        # --- issue list --------------------------------------------------------
        self.tree = QTreeWidget(body)
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels([
            self.tr('Severity'),
            self.tr('Rule'),
            self.tr('Layer'),
            self.tr('Feature'),
            self.tr('Message'),
        ])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.setSelectionBehavior(
            QTreeWidget.SelectionBehavior.SelectRows)
        header = self.tree.header()
        header.setStretchLastSection(True)
        for col in range(4):
            header.setSectionResizeMode(
                col, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.itemActivated.connect(self._on_item_activated)
        self.tree.itemDoubleClicked.connect(self._on_item_activated)
        outer.addWidget(self.tree, 1)

        self.setWidget(body)
        self._reset_filters()

    # -- public API ---------------------------------------------------------

    def set_result(self, result):
        """Render a :class:`ValidationResult` (or ``None`` to clear)."""
        self._result = result
        self._issues = list(result.sorted_issues()) if result else []
        self.btn_export.setEnabled(bool(result))
        self._reset_filters()
        self._populate()
        self._update_summary()

    def result(self):
        """The rendered :class:`ValidationResult`, or ``None`` before a run.

        The export handler needs the result the user is looking at, and reaching
        into ``_result`` from the plugin would make a private attribute part of
        the contract by accident.
        """
        return self._result

    def set_busy(self, busy: bool):
        """Disable the controls while a run is in flight."""
        self.btn_rerun.setEnabled(not busy)
        if busy:
            self.lbl_summary.setText(self.tr('Validating…'))

    # -- internals ----------------------------------------------------------

    def _severity_label(self, severity) -> str:
        if severity == Severity.ERROR:
            return self.tr('Error')
        if severity == Severity.WARNING:
            return self.tr('Warning')
        return self.tr('Info')

    def _reset_filters(self):
        """Rebuild the filter combos from the current issue set."""
        for combo in (self.cb_severity, self.cb_layer, self.cb_rule):
            combo.blockSignals(True)
            combo.clear()

        self.cb_severity.addItem(self.tr('All'), _ALL)
        for severity in sorted(_SEVERITY_COLOUR, key=lambda s: SEVERITY_ORDER[s]):
            self.cb_severity.addItem(self._severity_label(severity), severity.value)

        self.cb_layer.addItem(self.tr('All'), _ALL)
        for name in sorted({i.layer_name for i in self._issues if i.layer_name}):
            self.cb_layer.addItem(name, name)

        self.cb_rule.addItem(self.tr('All'), _ALL)
        for rule_id in sorted({i.rule_id for i in self._issues}):
            self.cb_rule.addItem(rule_id, rule_id)

        for combo in (self.cb_severity, self.cb_layer, self.cb_rule):
            combo.blockSignals(False)

    def _populate(self):
        self.tree.setSortingEnabled(False)
        self.tree.clear()
        for issue in self._issues:
            item = _IssueItem([
                self._severity_label(issue.severity),
                issue.rule_id,
                issue.layer_name,
                str(issue.feature_id) if issue.feature_id >= 0 else '',
                issue.message,
            ])
            colour = _SEVERITY_COLOUR.get(issue.severity)
            if colour is not None:
                item.setForeground(0, QBrush(colour))
            item.setData(0, _ROLE_RANK, SEVERITY_ORDER.get(issue.severity, 9))
            item.setData(0, _ROLE_ISSUE, issue)
            if issue.fix_hint:
                item.setToolTip(4, issue.fix_hint)
            self.tree.addTopLevelItem(item)
        # Sort by severity rank ascending, i.e. errors first, before handing
        # sorting back to the user.
        self.tree.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tree.setSortingEnabled(True)
        self._apply_filters()

    def _apply_filters(self):
        severity = self.cb_severity.currentData()
        layer = self.cb_layer.currentData()
        rule = self.cb_rule.currentData()

        shown = 0
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            issue = item.data(0, _ROLE_ISSUE)
            if issue is None:
                continue
            visible = (
                (severity in (None, _ALL) or issue.severity.value == severity)
                and (layer in (None, _ALL) or issue.layer_name == layer)  # noqa: W503
                and (rule in (None, _ALL) or issue.rule_id == rule)  # noqa: W503
            )
            item.setHidden(not visible)
            shown += 1 if visible else 0
        self._update_summary(shown)

    def _update_summary(self, shown=None):
        if self._result is None:
            self.lbl_summary.setText(self.tr('No validation run yet.'))
            return

        counts = self._result.counts_by_severity()
        if not self._issues:
            # A bare "No issues found." reads the same whether fourteen rules
            # examined the project or none of them found a layer to look at.
            # State the scope so a clean bill of health carries its evidence.
            src = QT_TRANSLATE_NOOP(
                'ValidationPanel', 'No issues found — {rules} rules ran over {layers} layers, {features} features.')
            text = safe_format(self.tr(src), src, **self._scope())
        else:
            # %n plurals: Qt picks the right form per language from the count.
            parts = [
                self.tr('%n error(s)', '', counts['error']),
                self.tr('%n warning(s)', '', counts['warning']),
                self.tr('%n info', '', counts['info']),
            ]
            text = ', '.join(parts)
            if shown is not None and shown != len(self._issues):
                src = QT_TRANSLATE_NOOP('ValidationPanel', '{summary} — showing {shown} of {total}')
                text = safe_format(self.tr(src), src,
                                   summary=text, shown=shown, total=len(self._issues))
        # Outside the branch on purpose: a run where every rule crashed produces
        # no issues, and must not be reported as a clean project.
        if self._result.rule_errors:
            text += '\n' + self.tr('%n rule(s) failed to run',
                                   '', len(self._result.rule_errors))
        self.lbl_summary.setText(text)

    def _scope(self):
        """What the run actually covered, for the empty-result summary."""
        counts = self._result.feature_counts or {}
        return {
            'rules': len(self._result.ran_rules),
            'layers': len(counts),
            'features': sum(counts.values()),
        }

    def _on_item_activated(self, item, _column=0):
        issue = item.data(0, _ROLE_ISSUE) if item else None
        if issue is not None:
            self.issueActivated.emit(issue)
