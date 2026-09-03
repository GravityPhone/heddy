"""Allow ``python -m heddy``."""

import sys

from heddy.app import main

if __name__ == "__main__":
    sys.exit(main())
