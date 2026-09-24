from __future__ import annotations

import json
import os
from pathlib import Path

from .config import Settings
from .editor import auto_edit
from .metadata import make_metadata
from .providers.drive import DriveProvider


def main():
    settings = Settings.load()
    drive = DriveProvider()
    siblings = drive.resolve_siblings(settings.inbox_id)
    candidates = (
        drive.list_ready(settings.inbox_id, siblings["ready"], 20)
        or drive.list_new(settings.inbox_id, 20)
    )
    if not candidates:
        raise SystemExit("No video found")

    index = int(os.getenv("JUDM_PREVIEW_INDEX", "0"))
    if index < 0 or index >= len(candidates):
        raise SystemExit(
            f"Preview index {index} unavailable; candidates={len(candidates)}"
        )

    source = candidates[index]
    raw = Path("out") / "source" / source["name"]
    drive.download(source["id"], raw)
    outputs = auto_edit(
        raw,
        Path("out") / "edited",
        make_metadata(source["name"]),
    )
    print(
        json.dumps(
            {"preview_index": index, "source": source["name"], "outputs": outputs},
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
