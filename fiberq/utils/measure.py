"""Ground-truth length measurement.

Every length the plugin stores or shows to the user is a **real-world** distance:
metres of cable to buy, metres of trench to dig. ``QgsGeometry.length()`` does not
give that -- it returns the length in the layer's *map* units, which in a
conformal projection is the ground length multiplied by the local scale factor.

In Web Mercator (EPSG:3857), by far the most common working CRS because it is what
the web basemaps use, that factor is ``1 / cos(latitude)``. It is 1.00 on the
equator, 1.41 in Serbia, 1.55 in the Netherlands and 1.86 in Finland. A cable
digitised over a 276 m street in Niš therefore stores as 389 m, and the bill of
materials over-orders by 41%.

So: never call ``geom.length()`` on a value that reaches a field or a user. Call
:func:`ground_length`, which measures on the project ellipsoid the way the QGIS
measure tool does, and agrees with what a surveyor would find on site.
"""
from qgis.core import QgsDistanceArea, QgsProject

from .logger import get_logger

logger = get_logger(__name__)

#: QgsDistanceArea is not free to build, and these calls happen per feature during
#: route import. Keyed on (CRS, ellipsoid) so it re-derives if either changes.
_CACHE = {}


def _project(project=None):
    return project if project is not None else QgsProject.instance()


def _resolve_crs(crs, project):
    if crs is None or not crs.isValid():
        return _project(project).crs()
    return crs


def resolve_ellipsoid(crs=None, project=None) -> str:
    """The ellipsoid to measure on: the project's if set, else the CRS's own.

    QGIS leaves a brand-new project on ``'NONE'`` -- and keeps it there even after
    the project CRS is set. Taking that at face value turns every measurement back
    into map units, which in Web Mercator overstates distance by 1/cos(latitude):
    1.37x at Serbian latitudes. That is the very error this module exists to
    remove, so an unconfigured project falls back to the ellipsoid its own CRS
    names (EPSG:3857 -> EPSG:7030), which is what the QGIS measure tool shows and
    is right wherever the project has simply never been configured.

    Returns ``''`` when neither is available; the caller then measures in map
    units, and :func:`measures_metres` reports that honestly.
    """
    prj = _project(project)
    ellipsoid = (prj.ellipsoid() or "").strip()
    if ellipsoid and ellipsoid.upper() != "NONE":
        return ellipsoid
    try:
        return (_resolve_crs(crs, prj).ellipsoidAcronym() or "").strip()
    except Exception as e:
        logger.debug(f"Could not read the ellipsoid from the CRS: {e}")
        return ""


def distance_area(crs=None, project=None):
    """A :class:`QgsDistanceArea` configured from the project's measurement settings."""
    prj = _project(project)
    crs = _resolve_crs(crs, prj)
    ellipsoid = resolve_ellipsoid(crs, prj)
    key = (crs.authid() or crs.toWkt(), ellipsoid)

    cached = _CACHE.get(key)
    if cached is None:
        cached = QgsDistanceArea()
        try:
            cached.setSourceCrs(crs, prj.transformContext())
        except Exception as e:
            logger.debug(f"Could not set measurement CRS to {key[0]}: {e}")
        try:
            cached.setEllipsoid(ellipsoid)
        except Exception as e:
            logger.debug(f"Could not set measurement ellipsoid to {ellipsoid}: {e}")
        _CACHE[key] = cached
    return cached


def measures_metres(layer=None, crs=None, project=None) -> bool:
    """Whether :func:`ground_length` will really return metres.

    Asks the configured measurer rather than inferring from the CRS. "Projected,
    therefore linear, therefore metres" is the trap: a projected CRS with no
    usable ellipsoid measures in *map* units, and Web Mercator map units are not
    metres. ``willUseEllipsoid()`` is the only thing that knows which mode the
    measurement will actually run in.
    """
    if crs is None and layer is not None:
        try:
            crs = layer.crs()
        except Exception:
            crs = None
    try:
        return bool(distance_area(crs, project).willUseEllipsoid())
    except Exception as e:
        logger.debug(f"Could not determine the measurement mode: {e}")
        return False


def ground_length(geom, layer=None, crs=None, project=None) -> float:
    """Length of ``geom`` in metres on the ground.

    Pass the ``layer`` the geometry belongs to (or its ``crs``) so the measurement
    starts from the right coordinate system; without either, the project CRS is
    assumed, which is right for anything drawn on the canvas.

    Falls back to the planar length rather than raising -- a slightly wrong number
    beats losing the attribute -- and says so in the log.
    """
    if geom is None:
        return 0.0
    try:
        if geom.isEmpty():
            return 0.0
    except Exception:
        return 0.0

    if crs is None and layer is not None:
        try:
            crs = layer.crs()
        except Exception:
            crs = None

    try:
        return float(distance_area(crs, project).measureLength(geom))
    except Exception as e:
        logger.debug(f"Ellipsoidal measurement failed, using planar length: {e}")
        try:
            return float(geom.length())
        except Exception:
            return 0.0


def ground_length_km(geom, layer=None, crs=None, project=None, places: int = 2) -> float:
    """:func:`ground_length` in kilometres, rounded the way the layers store it."""
    return round(ground_length(geom, layer, crs, project) / 1000.0, places)


def clear_cache():
    """Drop the cached measurers (call if the project's ellipsoid changes)."""
    _CACHE.clear()
