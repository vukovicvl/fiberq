"""Seeds a package whose __init__ takes its own submodules down with it.

This is the shape of fiberq/addons: the package imports each submodule in turn,
so one bad import makes every one of them unavailable. It is also the shape that
fooled the first version of the gate -- `fine` is imported BEFORE `broken`, so it
lands in sys.modules, and an in-process import of it afterwards finds it cached
and answers a false OK even though no user could ever reach it.
"""
from . import fine     # noqa: F401  - succeeds, and gets cached
from . import broken   # noqa: F401  - raises, and unregisters this package
