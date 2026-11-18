"""Code for tests to share. It holds no tests itself.

- ``child.py``: ``run_driver()``, which runs a driver script in a child Python and reads back what it prints.
  It imports only the standard library.
- ``fake_iface.py``: ``FakeIface``, a stand-in for QGIS's ``iface`` with what the plugin's ``initGui()`` and
  ``unload()`` use. It imports QGIS.
- ``toolbar_driver.py``: a driver that builds the plugin's toolbars with ``FakeIface`` and prints what they
  show. It runs as a script, in a child process.
- ``initgui_snapshot.py``: the record of what the plugin's ``initGui()`` builds, its comparison with the golden
  file ``tests/initgui_golden.json`` and the golden file's writer. It imports only the standard library at its
  top. ``tests/test_initgui_snapshot.py`` imports it and runs it as a driver script, in a child process;
  ``tests/app/smoke.py`` imports it in the real QGIS app.
- ``lifecycle_driver.py``: a driver that runs load-and-unload cycles of the plugin (two, unless the
  ``options.json`` in the folder it runs in says otherwise) and counts what each step leaves behind, for
  ``tests/test_lifecycle_ratchet.py``. It runs as a script, in a child process, and is never imported.

``initgui_snapshot.py`` and ``lifecycle_driver.py`` belong to WP5's test files: no other test file or module
imports or runs them, so the coverage procedure can remove WP5's test files and leave every other test as it is
(docs/testing.md).

pyproject.toml puts ``tests/`` on pytest's ``sys.path``, so a test file imports from here as ``support``
(``from support.child import run_driver``), in any import mode. A driver puts the repository root and
``tests/`` on its own ``sys.path`` and then imports ``support.fake_iface``, if it uses ``FakeIface``.

The fast stage picks a test file only if it imports without QGIS, so what a test file imports from here at
its top must import without QGIS: ``child.py`` and ``initgui_snapshot.py`` do, ``fake_iface.py`` does not
(docs/testing.md).

``toolbar_driver.py``, ``initgui_snapshot.py`` and ``lifecycle_driver.py`` run from this folder as scripts,
and Python puts a script's folder first on ``sys.path``. So no module here may be named like a standard-library,
QGIS or installed module, and code here imports another module here as ``support.<module>``, never by its bare
name.
"""
