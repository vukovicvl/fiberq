"""Generate a minimal .qgs that QGIS 4 would have written.

Used by ``tests/test_project_compat.py``. Nothing it produces is committed:
``tests/fixtures/`` holds generators, not their output.

A real QGIS-4 project would do, and was compared against this one on the 3.22
and 3.44 legs -- they are indistinguishable where the test cares
(``lastSaveVersion()`` reports 4.0.3, and every FiberQ project entry reads back
absent). This one is used instead for three reasons: it needs no QGIS 4 to
produce, so anyone can regenerate it; it is 1.5 KB rather than 31 KB and
reviewable as a diff; and a genuine project's root element carries
``saveUser`` and ``saveUserFull``, which is the maintainer's own username and
has no business in a public repository.

The one thing that matters is the nesting. QGIS 3 writes

    <properties><FiberQPlugin><gpkg_path type="QString">...</gpkg_path></FiberQPlugin></properties>

and QGIS 4 writes

    <properties><properties name="FiberQPlugin"><properties name="gpkg_path" type="QString">...

QGIS 3 cannot read the second form, which is why it loses every entry.
"""
import textwrap

#: What a QGIS 4 project reports from lastSaveVersion().
QGIS4_VERSION = "4.0.3-Norrköping"

TEMPLATE = textwrap.dedent("""\
    <?xml version="1.0" encoding="UTF-8"?>
    <qgis projectname="FiberQ newer-project fixture" version="{version}">
      <title>FiberQ newer-project fixture</title>
      <projectCrs>
        <spatialrefsys>
          <authid>EPSG:3857</authid>
        </spatialrefsys>
      </projectCrs>
      <layer-tree-group/>
      <projectlayers/>
      <properties>
        <properties name="FiberQPlugin">
          <properties name="gpkg_path" type="QString">/data/project.gpkg</properties>
        </properties>
        <properties name="StuboviPlugin">
          <properties name="Relacije">
            <properties name="relations_v1" type="QString">{{"relations":[{{"id":1}}]}}</properties>
          </properties>
          <properties name="ColorCatalogs">
            <properties name="catalogs_v1" type="QString">{{"catalogs":[{{"name":"Custom"}}]}}</properties>
          </properties>
        </properties>
      </properties>
    </qgis>
    """)


def generate(path, version=QGIS4_VERSION):
    """Write the fixture to ``path`` and return it."""
    path = str(path)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(TEMPLATE.format(version=version))
    return path


if __name__ == "__main__":
    import sys
    print(generate(sys.argv[1] if len(sys.argv) > 1 else "qgis4_saved.qgs"))
