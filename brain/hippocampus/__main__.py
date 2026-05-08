"""Console entry point for the Hippocampus service.

Installed by pyproject's [project.scripts] as `hippocampus`. Reads
HIPPOCAMPUS_HOST / HIPPOCAMPUS_PORT from the environment so the systemd
unit and dev runs share configuration.
"""

from __future__ import annotations

import os

import uvicorn


def main() -> None:
    uvicorn.run(
        "brain.hippocampus.app:app",
        host=os.environ.get("HIPPOCAMPUS_HOST", "0.0.0.0"),
        port=int(os.environ.get("HIPPOCAMPUS_PORT", "54321")),
        reload=False,
    )


if __name__ == "__main__":
    main()
