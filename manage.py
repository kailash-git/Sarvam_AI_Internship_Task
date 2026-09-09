#!/usr/bin/env python
"""Project entry point.

    python manage.py migrate     # apply migrations
    python manage.py seed        # load seed data
    python manage.py reset       # delete db, migrate, seed  (reset/repeat workflow)
    python manage.py serve       # run the HTTP API + frontend on http://127.0.0.1:8000
    python manage.py eval        # run the evaluation harness, write evaluation/results/
    python manage.py process "Open the kiwi service."   # one-shot pipeline from the CLI
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    cmd, rest = argv[0], argv[1:]

    if cmd == "migrate":
        from kivi.db.migrate import migrate
        print("migrations applied:", migrate() or "(nothing new)")
    elif cmd == "seed":
        from kivi.db.seed import seed
        print(json.dumps(seed(), indent=2))
    elif cmd == "reset":
        from kivi.db.reset import reset
        print(json.dumps(reset(), indent=2))
    elif cmd == "serve":
        import uvicorn
        uvicorn.run("api.main:app", host="127.0.0.1", port=8000, reload=False)
    elif cmd == "eval":
        from evaluation.run import run_eval
        summary = run_eval()
        print(json.dumps(summary["headline"], indent=2))
    elif cmd == "process":
        from kivi.db.reset import reset  # ensure db exists
        from kivi.db.migrate import migrate
        migrate()
        from kivi.pipeline import process
        text = " ".join(rest) or "Open the kiwi service."
        print(json.dumps(process(text=text), indent=2))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))  # for `evaluation` package
    raise SystemExit(main(sys.argv[1:]))
