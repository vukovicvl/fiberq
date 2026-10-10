"""Batched reads: one request per layer where there was one scan per feature.

WP4 task 4.1 (PF-1, PF-2). The schematic view and the latent-elements list found
each feature they needed by reading its layer from the top until the id came
up -- a whole-layer scan per cable, pipe or map node. Opening the schematic view
at the benchmark's size S read 2,156,690 features to find 3,919 cables and
pipes, and its "Match map styling" layout read another 1,471,859 to place 3,304
nodes (v1.5.0, QGIS 3.44.15).

``features_by_id`` asks each layer once, for every id it is wanted for.
"""
from qgis.core import QgsFeatureRequest, QgsProject, QgsVectorLayer


def features_by_id(pairs):
    """``{layer_id: {fid: QgsFeature}}`` for ``(layer_id, fid)`` pairs, one request per layer.

    It reads through the layer's edit buffer exactly as the scans did: a feature
    added and not yet saved (negative fid) is found, a deleted one is not, and
    an edited attribute or geometry comes back edited (measured on 3.22.16,
    3.40.15, 3.44.15, 4.0.3 and 4.2.3). An id the layer does not hold is simply
    absent, and so is a layer id that is not a vector layer in the project.

    A dict, because the request's own order is no order to rely on: ascending
    fid on a GeoPackage, but Qt hash order on a memory layer, different in every
    session (measured).
    """
    wanted = {}
    for layer_id, fid in pairs:
        wanted.setdefault(layer_id, []).append(int(fid))
    found = {}
    project = QgsProject.instance()
    for layer_id, fids in wanted.items():
        layer = project.mapLayer(layer_id)
        if not isinstance(layer, QgsVectorLayer):
            continue
        # A list: setFilterFids raises TypeError on a set, a tuple or a generator.
        request = QgsFeatureRequest().setFilterFids(fids)
        by_fid = found[layer_id] = {}
        for feature in layer.getFeatures(request):
            # The first, as the scan stopped at its first match, should a
            # provider ever answer one fid twice (a view without a unique key).
            by_fid.setdefault(feature.id(), feature)
    return found


__all__ = ['features_by_id']
