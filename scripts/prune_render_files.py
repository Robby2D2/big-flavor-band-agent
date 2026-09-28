"""Delete the in-between files that fix renders left behind.

Every step of a fix chain used to keep its full-length WAV, though only the
chain's final file is ever read again (see ``_chain_apply_tools``, which now
deletes them as it goes). This clears the ones written before that change.

In each chain directory (files named ``NN_tool_timestamp.wav``) the file with
the highest step number is the chain's result and is kept; so is any file a
``song_versions`` or ``song_stems`` row points at. Everything else in the chain
is deleted. Compressed ``previews/`` copies and downmixes are left alone.

Dry run by default — pass ``--apply`` to delete:

    docker exec bigflavor-backend python scripts/prune_render_files.py
    docker exec bigflavor-backend python scripts/prune_render_files.py --apply
"""
import asyncio
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from database import DatabaseManager  # noqa: E402

PRODUCED = Path("/app/audio_library/produced")
RENDER_DIRS = ("accept_fixes", "stem_preview", "master_preview")
STEP_FILE = re.compile(r"^(\d{2})_.+_\d+\.wav$")


async def referenced_paths() -> Set[str]:
    db = DatabaseManager()
    await db.connect()
    try:
        async with db.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT audio_path AS path FROM song_versions UNION SELECT path FROM song_stems"
            )
    finally:
        await db.close()
    return {row["path"] for row in rows}


def chain_dirs() -> List[Path]:
    found = []
    for kind in RENDER_DIRS:
        for directory in PRODUCED.glob(f"*/{kind}/**/"):
            if directory.name != "previews" and any(
                STEP_FILE.match(f.name) for f in directory.iterdir() if f.is_file()
            ):
                found.append(directory)
    return found


def doomed(directory: Path, keep: Set[str]) -> List[Path]:
    steps: Dict[Path, int] = {
        f: int(STEP_FILE.match(f.name).group(1))
        for f in directory.iterdir()
        if f.is_file() and STEP_FILE.match(f.name)
    }
    final = max(steps.values())
    return [f for f, step in steps.items() if step != final and str(f) not in keep]


async def main(apply: bool) -> None:
    keep = await referenced_paths()
    files = [f for directory in chain_dirs() for f in doomed(directory, keep)]
    size = sum(f.stat().st_size for f in files)
    print(f"{len(files)} in-between files, {size / 1e9:.2f} GB")
    if not apply:
        print("Dry run — pass --apply to delete them.")
        return
    for f in files:
        f.unlink(missing_ok=True)
    print("Deleted.")


if __name__ == "__main__":
    asyncio.run(main("--apply" in sys.argv[1:]))
