#!/usr/bin/env python3
"""Generate a *pre-1.0* (pre-``fiberq_uuid``) FiberQ GeoPackage fixture.

This synthesises a GeoPackage that looks like a project saved by an older FiberQ
build: legacy Serbian layer/table names, realistic field rosters, and real
features -- but crucially WITHOUT the ``fiberq_uuid`` identity column and WITHOUT
a ``schema_version`` row in ``_fiberq_metadata``. Loading it and running the WP1b
migration runner therefore has real work to do (add + backfill ``fiberq_uuid``,
stamp the marker), which is exactly what the migration tests exercise.

It is written with ``osgeo.ogr`` + ``sqlite3`` directly (no QGIS needed), which
matches how ``ExportManager`` writes GeoPackages: the GDAL GPKG driver for the
spatial layers and raw ``sqlite3`` for the ``_fiberq_metadata`` key/value table.

Usage (also importable):
    python tests/fixtures/make_sample_project.py [output.gpkg]

    from make_sample_project import build_pre_uuid_gpkg
    build_pre_uuid_gpkg("/tmp/legacy_pre_uuid.gpkg")

The rosters mirror ``fiberq/models/schema.py`` as-built, minus ``fiberq_uuid``
(and minus the same-era cable "Designer" fields fibers_per_tube / total_fibers /
color_standard) so the fixture is authentically pre-1.0.
"""
import os
import sqlite3
import sys

#: A realistic projected CRS for the region (UTM zone 34N).
EPSG = 32634

#: Logical field type -> OGR field-type attribute name (resolved lazily so the
#: module imports without GDAL until build time). int/year/bool all map to
#: OFTInteger; the migration does not depend on the boolean subtype.
_OGR_TYPE = {
    "text": "OFTString",
    "enum": "OFTString",
    "int": "OFTInteger",
    "year": "OFTInteger",
    "bool": "OFTInteger",
    "double": "OFTReal",
}


# Each layer: table name (legacy on-disk name), wkb geometry-type attr, the field
# roster as (name, logical_type) minus fiberq_uuid, and a few real features as
# (wkt, {attrs}). Coordinates sit in valid UTM 34N ranges.
_LAYERS = [
    {
        "table": "ODF",  # canonical: ODF (element roster, schema.py:267-283)
        "wkb": "wkbPoint",
        "fields": [
            ("naziv", "text"), ("proizvodjac", "text"), ("oznaka", "text"),
            ("kapacitet", "int"), ("ukupno_kj", "int"), ("zahtev_kapaciteta", "int"),
            ("zahtev_rezerve", "int"), ("oznaka_izvoda", "text"), ("numeracija", "text"),
            ("naziv_objekta", "text"), ("adresa_ulica", "text"), ("adresa_broj", "text"),
            ("address_id", "text"), ("stanje", "text"), ("godina_ugradnje", "year"),
        ],
        "features": [
            ("POINT(455000 4965000)", {
                "naziv": "ODF-01", "proizvodjac": "Corning", "oznaka": "A1",
                "kapacitet": 24, "ukupno_kj": 24, "stanje": "Postojece",
                "adresa_ulica": "Njegoseva", "adresa_broj": "12",
                "godina_ugradnje": 2019,
            }),
            ("POINT(455120 4965080)", {
                "naziv": "ODF-02", "proizvodjac": "Corning", "oznaka": "A2",
                "kapacitet": 48, "ukupno_kj": 48, "stanje": "Projektovano",
                "godina_ugradnje": 2021,
            }),
        ],
    },
    {
        "table": "Kablovi_podzemni",  # canonical: Underground cables (schema.py:401-433)
        "wkb": "wkbLineString",
        "fields": [
            ("tip", "text"), ("podtip", "text"), ("color_code", "text"),
            ("broj_cevcica", "int"), ("broj_vlakana", "int"), ("tip_kabla", "text"),
            ("vrsta_vlakana", "text"), ("vrsta_omotaca", "text"), ("vrsta_armature", "text"),
            ("talasno_podrucje", "text"), ("naziv", "text"), ("slabljenje_dbkm", "double"),
            ("hrom_disp_ps_nmxkm", "double"), ("stanje_kabla", "text"), ("cable_laying", "text"),
            ("vrsta_mreze", "text"), ("godina_ugradnje", "int"),
            ("konstr_vlakna_u_cevcicama", "int"), ("konstr_sa_uzlepljenim_elementom", "int"),
            ("konstr_punjeni_kabl", "int"), ("konstr_sa_arm_vlaknima", "int"),
            ("konstr_bez_metalnih", "int"), ("od", "text"), ("do", "text"),
            ("duzina_m", "double"), ("slack_m", "double"), ("total_len_m", "double"),
        ],
        "features": [
            ("LINESTRING(455000 4965000, 455100 4965050)", {
                "tip": "opticki", "podtip": "glavni", "broj_cevcica": 1,
                "broj_vlakana": 24, "tip_kabla": "TOSM-24", "naziv": "MC-01",
                "stanje_kabla": "Projektovano", "cable_laying": "Podzemno",
                "od": "ODF-01", "do": "OKNO-1", "duzina_m": 812.5,
                "slack_m": 20.0, "total_len_m": 832.5,
            }),
            ("LINESTRING(455100 4965050, 455260 4965180)", {
                "tip": "opticki", "podtip": "razvodni", "broj_cevcica": 1,
                "broj_vlakana": 12, "tip_kabla": "TOSM-12", "naziv": "MC-02",
                "stanje_kabla": "Postojece", "cable_laying": "Podzemno",
                "duzina_m": 204.0, "total_len_m": 204.0,
            }),
        ],
    },
    {
        "table": "Trasa",  # canonical: Route (schema.py:349-355)
        "wkb": "wkbLineString",
        "fields": [
            ("naziv", "text"), ("duzina", "double"), ("duzina_km", "double"),
            ("tip_trase", "text"),
        ],
        "features": [
            ("LINESTRING(455000 4965000, 455100 4965050)", {
                "naziv": "Trasa-1", "duzina": 812.5, "duzina_km": 0.8125,
                "tip_trase": "podzemna",
            }),
        ],
    },
    {
        "table": "OKNA",  # canonical: Manholes (schema.py:328-347)
        "wkb": "wkbPoint",
        "fields": [
            ("broj_okna", "text"), ("tip_okna", "text"), ("vrsta_okna", "text"),
            ("polozaj_okna", "text"), ("adresa", "text"), ("stanje", "text"),
            ("god_ugrad", "int"), ("opis", "text"), ("dimenzije", "text"),
            ("mat_zida", "text"), ("mat_poklop", "text"), ("odvodnj", "text"),
            ("poklop_tes", "bool"), ("poklop_lak", "bool"), ("br_nosaca", "int"),
            ("debl_zida", "double"), ("lestve", "text"),
        ],
        "features": [
            ("POINT(455100 4965050)", {
                "broj_okna": "O-1", "tip_okna": "D1", "stanje": "Postojece",
                "god_ugrad": 2018, "poklop_tes": 1, "poklop_lak": 0, "br_nosaca": 2,
            }),
            ("POINT(455260 4965180)", {
                "broj_okna": "O-2", "tip_okna": "D2", "stanje": "Projektovano",
                "god_ugrad": 2021, "poklop_tes": 0, "poklop_lak": 1,
            }),
        ],
    },
    {
        "table": "Objekti",  # canonical: Objects (schema.py:387-396)
        "wkb": "wkbPolygon",
        "fields": [
            ("tip", "text"), ("spratova", "int"), ("podzemnih", "int"),
            ("ulica", "text"), ("broj", "text"), ("naziv", "text"), ("napomena", "text"),
        ],
        "features": [
            ("POLYGON((455000 4965000, 455050 4965000, 455050 4965050, "
             "455000 4965050, 455000 4965000))", {
                 "tip": "stambeni", "spratova": 4, "podzemnih": 1,
                 "ulica": "Njegoseva", "broj": "12", "naziv": "Zgrada A",
             }),
        ],
    },
]

#: Legacy ``_fiberq_metadata`` rows. Deliberately carries ``project_version`` but
#: NOT ``schema_version`` -- the load-bearing "this project predates the marker"
#: signal, alongside a plausible pre-WP1a plugin version.
_LEGACY_METADATA = {
    "project_version": "1.2.1",
    "relations_json": '{"relations": []}',
    "latent_elements_json": '{"cables": {}}',
    "color_standard": "TIA-598-C",
    "crs_epsg": str(EPSG),
    "export_timestamp": "2025-11-01T09:30:00Z",
}


def build_pre_uuid_gpkg(path, with_metadata_table=True):
    """Write a pre-1.0 FiberQ GeoPackage fixture at ``path`` and return ``path``.

    Args:
        path: output ``.gpkg`` path (overwritten if it exists).
        with_metadata_table: if True, add a legacy ``_fiberq_metadata`` table
            (with ``project_version`` but no ``schema_version``). Set False for a
            "truly ancient" variant with no metadata table at all.
    """
    from osgeo import gdal, ogr, osr

    # Fail fast on any OGR/GDAL error (and silence the GDAL 4.0 FutureWarning)
    # instead of silently producing a malformed fixture.
    gdal.UseExceptions()
    ogr.UseExceptions()

    if os.path.exists(path):
        os.remove(path)

    drv = ogr.GetDriverByName("GPKG")
    if drv is None:
        raise RuntimeError("GDAL GPKG driver unavailable")
    ds = drv.CreateDataSource(path)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(EPSG)

    for spec in _LAYERS:
        lyr = ds.CreateLayer(spec["table"], srs, getattr(ogr, spec["wkb"]))
        for fname, ftype in spec["fields"]:
            lyr.CreateField(ogr.FieldDefn(fname, getattr(ogr, _OGR_TYPE[ftype])))
        defn = lyr.GetLayerDefn()
        for wkt, attrs in spec["features"]:
            feat = ogr.Feature(defn)
            for key, value in attrs.items():
                feat.SetField(key, value)
            feat.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
            lyr.CreateFeature(feat)
            feat = None
        lyr = None
    ds = None  # flush + close before opening with sqlite3

    if with_metadata_table:
        _write_legacy_metadata(path)
    return path


def _write_legacy_metadata(path):
    """Add a pre-1.0 ``_fiberq_metadata`` table (no ``schema_version`` row)."""
    conn = sqlite3.connect(path)
    try:
        cur = conn.cursor()
        cur.execute("DROP TABLE IF EXISTS _fiberq_metadata")
        cur.execute(
            "CREATE TABLE _fiberq_metadata (key TEXT PRIMARY KEY, value TEXT)"
        )
        for key, value in _LEGACY_METADATA.items():
            cur.execute(
                "INSERT INTO _fiberq_metadata (key, value) VALUES (?, ?)",
                (key, value),
            )
        # Register as a non-spatial attributes table, mirroring ExportManager.
        cur.execute(
            "INSERT OR IGNORE INTO gpkg_contents "
            "(table_name, data_type, identifier, srs_id) "
            "VALUES (?, 'attributes', ?, 0)",
            ("_fiberq_metadata", "_fiberq_metadata"),
        )
        conn.commit()
    finally:
        conn.close()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    out = argv[0] if argv else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "legacy_pre_uuid.gpkg"
    )
    build_pre_uuid_gpkg(out)
    print(f"Wrote pre-1.0 fixture: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
