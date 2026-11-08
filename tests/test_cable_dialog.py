"""Regression: the cable "Number of fibers" field must follow the computed total
(tubes x fibers-per-tube) as the user types, instead of freezing at an
intermediate keystroke value (the reported bug showed 2 for 2 tubes x 12)."""


def test_number_of_fibers_follows_total(qgis_app):
    from fiberq.dialogs.cable_dialog import CablePickerDialog
    dlg = CablePickerDialog()
    dlg.sb_cevcice.setValue(2)
    # Simulate typing "12": valueChanged fires at the intermediate 1, then 12.
    dlg.sb_fibers_per_tube.setValue(1)     # old code froze sb_vlakna at 2 here
    dlg.sb_fibers_per_tube.setValue(12)
    assert dlg.lbl_total_fibers.text() == "24"
    assert dlg.sb_vlakna.value() == 24     # follows total (old code: stuck at 2)


def test_manual_fiber_count_is_respected(qgis_app):
    """Once the user types their own fiber count, later tube/fpt changes must not
    clobber it."""
    from fiberq.dialogs.cable_dialog import CablePickerDialog
    dlg = CablePickerDialog()
    dlg.sb_cevcice.setValue(2)
    dlg.sb_fibers_per_tube.setValue(12)    # auto-fills 24
    dlg.sb_vlakna.setValue(30)             # user override
    dlg.sb_cevcice.setValue(4)             # total would be 48
    assert dlg.sb_vlakna.value() == 30     # manual value preserved
    assert dlg.lbl_total_fibers.text() == "48"


def test_every_cable_type_the_dialog_offers_is_one_the_form_lists(qgis_app):
    """The dialog stores its code; the form shows a code its value map lacks in
    brackets, which is how every cable came to read "(Optical)" (v1.6.0 QA)."""
    from fiberq.dialogs.cable_dialog import CablePickerDialog
    from fiberq.utils.field_aliases import CABLE_TYPE_VALUE_MAP
    dlg = CablePickerDialog()
    offered = set()
    for row in range(dlg.cb_vrsta.count()):
        dlg.cb_vrsta.setCurrentIndex(row)
        offered |= {dlg.cb_tip.itemData(i) for i in range(dlg.cb_tip.count())}
    assert offered, "premise: the dialog offers cable types"
    assert offered <= set(CABLE_TYPE_VALUE_MAP.values()), offered
