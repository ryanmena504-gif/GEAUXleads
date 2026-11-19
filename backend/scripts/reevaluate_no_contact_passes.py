"""Re-open leads that were passed only because they had no phone or email.

A real interior job with a named person and a street address is restored
and tagged mail-door. Exterior-only permits, and LLC-owned multi-family
properties with no named person, stay passed.

This script does not connect to Airtable unless you pass --dry-run or
--apply. --dry-run only prints the plan. --apply writes. Do not pass
--apply until Ryan says to run it against the live base.

Nothing here calls Perplexity, OpenAI, or any other paid lookup.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List


def _print_plan(plan: Dict[str, Any]) -> None:
    print(json.dumps({
        "restore_count": plan["restore_count"],
        "keep_passed_count": plan["keep_passed_count"],
        "leave_count": plan["leave_count"],
        "writes": plan["writes"],
        "restore": plan["restore"],
        "keep_passed": plan["keep_passed"],
        "leave": plan["leave"],
    }, indent=2))


def plan_from_file(path: str) -> Dict[str, Any]:
    from services.mail_door import review_no_contact_passes

    with open(path, encoding="utf-8") as handle:
        rows = json.load(handle)
    if not isinstance(rows, list):
        raise SystemExit(f"{path} must be a JSON list of lead objects")
    return review_no_contact_passes(rows)


def plan_from_airtable() -> tuple:
    """Read the live Leads table. Caller decides whether to write."""
    from services.mail_door import review_no_contact_passes
    from services.opportunity_service import get_opportunity_service

    svc = get_opportunity_service()
    if svc is None or not hasattr(svc, "all"):
        raise SystemExit("Airtable is not configured. Nothing was read and nothing was written.")
    rows = svc.all()
    return svc, review_no_contact_passes(rows)


def apply_plan(svc, plan: Dict[str, Any]) -> int:
    """Write the restore set. Exterior-only and LLC multi-family rows are skipped."""
    written = 0
    for row in plan["restore"]:
        updates = row.get("updates") or {}
        if not row.get("id") or not updates:
            continue
        svc.update_fields(row["id"], updates)
        if row.get("disposition") == "keep-mail-door":
            note = "Restored. Interior job with a name and a street address, no phone or email. Contact channel: mail-door."
        else:
            note = "Restored. Passed earlier for no contact; a phone or email is on the record now."
        try:
            svc.add_activity(row["id"], "restored", note)
        except Exception as exc:  # noqa: BLE001
            print(f"Activity log failed for {row['id']}: {exc}", file=sys.stderr)
        written += 1
    return written


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", help="JSON list of leads. Prints a plan and does not connect.")
    parser.add_argument("--dry-run", action="store_true", help="Read Airtable and print the plan. No writes.")
    parser.add_argument("--apply", action="store_true", help="Read Airtable and write the restore set.")
    args = parser.parse_args(argv)

    if args.file:
        plan = plan_from_file(args.file)
        _print_plan(plan)
        if args.apply:
            print("Refusing --apply with --file. Apply only reads the live table, and only when you mean it.", file=sys.stderr)
            return 2
        return 0

    if not args.dry_run and not args.apply:
        print(
            "Not connected. Pass --dry-run to print the plan, or --apply to restore "
            "mail-door leads. This script does not run on its own, and --apply "
            "should wait until Ryan says to use it on the live base."
        )
        return 0

    svc, plan = plan_from_airtable()
    if args.apply:
        written = apply_plan(svc, plan)
        plan["writes"] = True
        plan["written"] = written
    _print_plan(plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
