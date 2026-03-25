"""Allow ``python -m runner`` as shortcut for ``python -m runner.main``."""

from .main import main
import sys

sys.exit(main())
