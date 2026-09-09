"""Kivi phonetic-memory CLI - the same core the web UI uses, on the terminal.

    python -m cli.kivi --help

Common flows:

    python -m cli.kivi reset                 # wipe + reseed
    python -m cli.kivi memory                # inspect memory state
    python -m cli.kivi teach-correction \\
        --formatted "Tell Aditya." --corrected "Tell Aaditya." --category person
    python -m cli.kivi teach-word --canonical Kivi --category product --alias kiwi
    python -m cli.kivi format \\
        --asr "ask aditya about kivi" --formatted "Ask Aditya about Kiwi."
    python -m cli.kivi walkthrough           # scripted end-to-end demo
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from app.db.migrate import migrate
from app.services import admin, learning, repo
from app.services.pipeline import process

GREEN, RED, DIM, BOLD, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[1m", "\033[0m"


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_migrate(_: argparse.Namespace) -> int:
    applied = migrate()
    print("applied:", ", ".join(applied) if applied else "(nothing pending)")
    return 0


def cmd_seed(_: argparse.Namespace) -> int:
    from app.db.seed import seed

    _print_json(seed())
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    _print_json(admin.reset(seed=not args.no_seed))
    return 0


def cmd_memory(args: argparse.Namespace) -> int:
    entries = repo.list_entries(status=args.status)
    if args.json:
        _print_json(entries)
        return 0
    if not entries:
        print("(memory is empty)")
        return 0
    for e in entries:
        aliases = ", ".join(a["surface_form"] for a in e["aliases"]) or "-"
        print(f"{BOLD}#{e['id']} {e['canonical']}{RESET}  [{e['category']}] "
              f"{e['status']}  conf={e['confidence']:.2f}")
        print(f"    aliases: {aliases}")
        if e["note"]:
            print(f"    note: {e['note']}")
    print(f"\n{DIM}{repo.stats()}{RESET}")
    return 0


def cmd_teach_correction(args: argparse.Namespace) -> int:
    res = learning.learn_from_correction(
        asr_text=args.asr or "", formatted_text=args.formatted,
        corrected_text=args.corrected, category=args.category, note=args.note or "",
    )
    _print_json({"changes": [asdict(c) for c in res.changes], "notes": res.notes})
    return 0


def cmd_teach_word(args: argparse.Namespace) -> int:
    res = learning.learn_from_dictionary(
        canonical=args.canonical, category=args.category,
        aliases=args.alias or [], note=args.note or "",
    )
    _print_json({"changes": [asdict(c) for c in res.changes], "notes": res.notes})
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    res = learning.learn_from_rejection(entry_id=args.entry_id, note=args.note or "")
    _print_json({"changes": [asdict(c) for c in res.changes], "notes": res.notes})
    return 0


def cmd_format(args: argparse.Namespace) -> int:
    r = process(args.asr or "", args.formatted, persist=not args.no_persist)
    if args.json:
        _print_json({
            "asr_text": r.asr_text, "formatted_text": r.formatted_text,
            "memory_aware_text": r.memory_aware_text, "intervened": r.intervened,
            "decisions": [asdict(d) for d in r.decisions], "trace": r.trace,
        })
        return 0
    print(f"{DIM}ASR       :{RESET} {r.asr_text}")
    print(f"{DIM}formatted :{RESET} {r.formatted_text}")
    mark = f"{GREEN}(intervened){RESET}" if r.intervened else f"{DIM}(unchanged){RESET}"
    print(f"{BOLD}memory    :{RESET} {r.memory_aware_text}  {mark}")
    print("decisions:")
    for d in r.decisions:
        colour = GREEN if d.action == "apply" else RED
        print(f"  {colour}{d.action:5}{RESET} {d.span_text!r} -> {d.canonical!r}  "
              f"{d.reason_tag}  (phon={d.phonetic_score}, score={d.combined_score}, "
              f"thr={d.threshold})")
        if d.detail:
            print(f"        {DIM}{d.detail}{RESET}")
    return 0


def cmd_walkthrough(_: argparse.Namespace) -> int:
    admin.reset(seed=False)
    steps = [
        ("Nothing taught yet - Kivi cannot know these words",
         lambda: cmd_format(_ns(asr="ask aditya to review the sarvam kiwi service",
                                formatted="Ask Aditya to review the Sarvam Kiwi service.",
                                no_persist=True, json=False))),
        ("Teach 'Kivi' explicitly (dictionary)",
         lambda: cmd_teach_word(_ns(canonical="Kivi", category="product",
                                    alias=["kiwi"], note=""))),
        ("Teach 'Aaditya' by correcting a transcript (x1 -> candidate)",
         lambda: cmd_teach_correction(_ns(asr="tell aditya", formatted="Tell Aditya.",
                                          corrected="Tell Aaditya.", category="person", note=""))),
        ("Same sentence again - only 'Kivi' fires; 'Aaditya' still weak",
         lambda: cmd_format(_ns(asr="ask aditya to review the sarvam kiwi service",
                                formatted="Ask Aditya to review the Sarvam Kiwi service.",
                                no_persist=True, json=False))),
        ("Correct 'Aaditya' a second time -> promoted to active",
         lambda: cmd_teach_correction(_ns(asr="did aditya reply", formatted="Did Aditya reply?",
                                          corrected="Did Aaditya reply?", category="person", note=""))),
        ("Now both fire",
         lambda: cmd_format(_ns(asr="ask aditya to review the sarvam kiwi service",
                                formatted="Ask Aditya to review the Sarvam Kiwi service.",
                                no_persist=True, json=False))),
        ("Homophone: food context -> Kivi deliberately does nothing",
         lambda: cmd_format(_ns(asr="i ate a kiwi for breakfast",
                                formatted="I ate a kiwi for breakfast.",
                                no_persist=True, json=False))),
    ]
    for i, (title, fn) in enumerate(steps, 1):
        print(f"\n{BOLD}=== Step {i}: {title} ==={RESET}")
        fn()
    print(f"\n{BOLD}=== Final memory state ==={RESET}")
    return cmd_memory(_ns(status=None, json=False))


def _ns(**kw) -> argparse.Namespace:
    base = dict(asr=None, formatted=None, corrected=None, category="other", note=None,
                canonical=None, alias=None, entry_id=None, no_persist=False,
                status=None, json=False, no_seed=False)
    base.update(kw)
    return argparse.Namespace(**base)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="kivi", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("migrate", help="apply pending migrations").set_defaults(func=cmd_migrate)
    sub.add_parser("seed", help="load reproducible seed data").set_defaults(func=cmd_seed)

    r = sub.add_parser("reset", help="wipe all learned state")
    r.add_argument("--no-seed", action="store_true", help="reset to an empty memory")
    r.set_defaults(func=cmd_reset)

    m = sub.add_parser("memory", help="inspect memory state")
    m.add_argument("--status", choices=list(repo.STATUSES))
    m.add_argument("--json", action="store_true")
    m.set_defaults(func=cmd_memory)

    c = sub.add_parser("teach-correction", help="learn from a formatted->corrected edit")
    c.add_argument("--asr", default="")
    c.add_argument("--formatted", required=True)
    c.add_argument("--corrected", required=True)
    c.add_argument("--category", default="other", choices=list(repo.CATEGORIES))
    c.add_argument("--note", default="")
    c.set_defaults(func=cmd_teach_correction)

    w = sub.add_parser("teach-word", help="add a word explicitly (trusted)")
    w.add_argument("--canonical", required=True)
    w.add_argument("--category", default="other", choices=list(repo.CATEGORIES))
    w.add_argument("--alias", action="append", help="repeatable")
    w.add_argument("--note", default="")
    w.set_defaults(func=cmd_teach_word)

    j = sub.add_parser("reject", help="record that an intervention was undone")
    j.add_argument("--entry-id", type=int, required=True, dest="entry_id")
    j.add_argument("--note", default="")
    j.set_defaults(func=cmd_reject)

    f = sub.add_parser("format", help="run ASR+formatted -> memory-aware")
    f.add_argument("--asr", default="")
    f.add_argument("--formatted", required=True)
    f.add_argument("--no-persist", action="store_true")
    f.add_argument("--json", action="store_true")
    f.set_defaults(func=cmd_format)

    sub.add_parser("walkthrough", help="scripted end-to-end demo").set_defaults(func=cmd_walkthrough)
    return p


def main(argv: list[str] | None = None) -> int:
    migrate()
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
