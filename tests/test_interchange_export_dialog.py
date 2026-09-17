"""The export dialog must not let the native "replace?" prompt delete the target.

Found in manual QA, and it is worth stating plainly because the symptom is the
one this whole format exists to prevent.

Re-exporting over an existing bundle destroyed the metadata another tool had
written into it -- and reported success. The writer was correct: exporting to the
same path from the Python console preserved the foreign key exactly as designed.
The loss happened *before* any FiberQ code ran. The native save dialog's
"file exists, replace?" deletes the file when you confirm, so the writer opened a
path with nothing at it, found no metadata to merge, and wrote a fresh bundle.

Nothing in the writer could detect that: a deleted file and a new file are the
same thing by the time you are called. The fix has to be to stop the deletion,
which means owning the overwrite prompt instead of delegating it.
"""
import inspect

import pytest

from fiberq.main_plugin import FiberQPlugin

SOURCE = inspect.getsource(FiberQPlugin.export_interchange_bundle)


def test_the_native_overwrite_prompt_is_disabled():
    """Without this flag the dialog deletes the bundle before we can read it.

    Asserts the flag is *passed to the dialog*, not merely looked up: reading it
    into a variable and then not using it is exactly the shape a careless edit
    would leave behind, and it would restore the bug in full.
    """
    assert "DontConfirmOverwrite" in SOURCE
    assert "getSaveFileName(*args, '', no_confirm)" in SOURCE


def test_the_flag_exists_in_this_qt_binding():
    """Qt5 exposes it as a plain attribute, Qt6 under a scoped Option enum."""
    from qgis.PyQt.QtWidgets import QFileDialog
    holder = getattr(QFileDialog, "Option", QFileDialog)
    assert getattr(holder, "DontConfirmOverwrite", None) is not None


def test_the_overwrite_is_confirmed_before_anything_is_written():
    """Suppressing the dialog's prompt without asking at all would be worse:
    the user would overwrite a bundle with no warning."""
    assert "_confirm_bundle_overwrite" in SOURCE
    ask = SOURCE.index("_confirm_bundle_overwrite")
    write = SOURCE.index("InterchangeBundleWriter(prj)")
    assert ask < write, "the overwrite is confirmed after the writer is built"


def test_a_target_that_does_not_exist_is_not_queried(tmp_path):
    """No prompt for a new file -- the check runs before any Qt is touched, so
    this exercises the real method rather than a stand-in."""
    stub = type("Stub", (), {})()
    assert FiberQPlugin._confirm_bundle_overwrite(
        stub, str(tmp_path / "brand-new.gpkg"), False) is True
    assert FiberQPlugin._confirm_bundle_overwrite(
        stub, str(tmp_path / "brand-new-folder"), True) is True


def test_a_geojson_target_is_judged_as_a_folder(tmp_path):
    """The dialog suggests a .gpkg name even for the GeoJSON profile, which
    writes a folder. Testing the wrong thing for existence would prompt about a
    file that is never written, or skip the prompt for a folder that is."""
    folder = tmp_path / "bundle"
    folder.mkdir()
    stub = type("Stub", (), {})()
    # A .gpkg path whose folder-equivalent exists must NOT pass unchallenged.
    with pytest.raises(AttributeError):
        # Reaching the QMessageBox needs self.iface; getting that far is the
        # assertion -- it means the folder was recognised as existing.
        FiberQPlugin._confirm_bundle_overwrite(stub, str(folder) + ".gpkg", True)
