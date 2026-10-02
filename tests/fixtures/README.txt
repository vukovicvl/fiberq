# Demo GeoPackage fixtures go here (sample_project.gpkg).
# Created in Phase 0 / WP6; reused by WP4 benchmark, WP3 round-trip, WP5 integration.
#
# Generators in this directory (none of their output is committed):
#   make_demo_project.py   the WP2 sample report's worked example, with planted faults
#   make_sample_project.py a pre-1.0 (pre-fiberq_uuid) GeoPackage for the migration tests
#   make_scale_project.py  WP2's volume fixture, calibrated to tests/test_scale.py
#   make_city_project.py   WP4's seeded city benchmark dataset (--size XS|XS4|S|M|L),
#                          validation-clean at every size; writes a manifest.json
#                          whose sha256 digest covers the rows and the project
#                          entries, not the file (GeoPackage bytes carry clock
#                          stamps, so they are not reproducible).
#                          tests/test_city_fixture.py pins the XS digest: change the
#                          generator and the benchmark baseline has to be re-measured
