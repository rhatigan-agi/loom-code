"""Entry point: python -m loom_mcp"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)

from loom_mcp.embeddings import warmup  # noqa: E402
from loom_mcp.init_db import init_database  # noqa: E402
from loom_mcp.server import mcp  # noqa: E402

init_database()
warmup()
mcp.run(transport="stdio")
