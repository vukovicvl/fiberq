"""The QGIS call FiberQ makes through ``utils.compat`` so that it does not print.

Found in the v1.6.0 QA on QGIS 3.40 LTR: the Python warning tab filled with
"QgsField constructor is deprecated", one line per place FiberQ builds a field
(49 in one session). It still worked; it is the kind of noise that hides a real
warning.
"""
import warnings

import pytest
from qgis.core import Qgis, QgsField, QgsVectorLayer
from qgis.PyQt.QtCore import QMetaType

from fiberq.utils.compat import FieldType

#: Qt's number for each built-in type, the same in QVariant and QMetaType.
NUMBERS = {"Bool": 1, "Int": 2, "LongLong": 4, "Double": 6, "String": 10}


def _deprecations(caught):
    return [str(w.message) for w in caught if issubclass(w.category, DeprecationWarning)]


def _number(kind):
    return int(getattr(kind, "value", kind))


@pytest.mark.parametrize("name", sorted(NUMBERS))
def test_a_field_type_builds_its_field_without_a_deprecation(qgis_app, name):
    kind = getattr(FieldType, name)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        field = QgsField("f", kind)
    assert _deprecations(caught) == []
    assert field.type() == kind
    assert _number(field.type()) == NUMBERS[name]


def test_qgis_3_22_gets_the_old_form_and_3_40_the_new_one():
    """Asked of QgsField itself; this pins the answer the versions measured gave."""
    if Qgis.QGIS_VERSION_INT >= 34000:
        assert isinstance(FieldType.String, QMetaType.Type)
    elif Qgis.QGIS_VERSION_INT < 33800:
        assert not isinstance(FieldType.String, QMetaType.Type)


def test_adding_the_identity_field_prints_no_deprecation(qgis_app):
    """The first FiberQ field of the QA session's 49: ``uuid_utils.ensure_uuid_field``."""
    from fiberq.utils.uuid_utils import FIBERQ_UUID_FIELD, ensure_uuid_field
    layer = QgsVectorLayer("Point?crs=EPSG:3857&field=naziv:string", "Poles", "memory")
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert ensure_uuid_field(layer)
    assert _deprecations(caught) == []
    assert layer.fields().indexOf(FIBERQ_UUID_FIELD) >= 0
