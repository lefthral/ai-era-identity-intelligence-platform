"""Investigator CLI.

A small command-line tool for working cases without a browser.
Connects to the same Postgres database the API uses.

Examples:
    # List the 10 most recent cases
    python -m examples.investigator_cli list --limit 10

    # Show a single case by ID
    python -m examples.investigator_cli show CASE-UUID

    # Mark a case as confirmed fraud
    python -m examples.investigator_cli act CASE-UUID \\
        --action confirm_fraud --investigator alice@bank.com \\
        --notes "Caller was a deepfake; funds traced via FRONTIER+"

    # Mark a case as false positive
    python -m examples.investigator_cli act CASE-UUID \\
        --action false_positive --investigator bob@bank.com

    # Export all open cases to CSV (for compliance reporting)
    python -m examples.investigator_cli export --output cases.csv

    # Stats: how many BLOCKs in the last 24h?
    python -m examples.investigator_cli stats --window-hours 24

The CLI uses the same repos as the API. The output is JSON by
default, --human for pretty-printed.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logger = logging.getLogger("investigator_cli")


def _human(v) -> str:
    """Pretty-print a value (datetime, UUID, etc.)."""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, dict):
        return json.dumps(v, indent=2, default=str)
    if isinstance(v, list):
        return json.dumps(v, indent=2, default=str)
    return str(v)


def cmd_list(args) -> int:
    from src.infrastructure.persistence.repos import CaseRepository

    repo = CaseRepository()
    cases = repo.list_recent(limit=args.limit, status=args.status)
    if args.human:
        for case in cases:
            print(
                f"[{case.case_id}] {case.status:12s} "
                f"score={case.decision.final_score:.2f} "
                f"opened={_human(case.opened_at)}"
            )
    else:
        print(json.dumps([c.model_dump() for c in cases], indent=2, default=str))
    return 0


def cmd_show(args) -> int:
    from src.infrastructure.persistence.repos import CaseRepository

    repo = CaseRepository()
    case = repo.get(UUID(args.case_id))
    if case is None:
        print(f"Case {args.case_id} not found", file=sys.stderr)
        return 1
    if args.human:
        print(f"Case:      {case.case_id}")
        print(f"Status:    {case.status}")
        print(f"Opened:    {_human(case.opened_at)}")
        print(f"Closed:    {_human(case.closed_at) if case.closed_at else '—'}")
        print(f"Investigator: {case.investigator or '—'}")
        print()
        print("=== Decision ===")
        d = case.decision
        print(f"  Action:    {d.action.value}")
        print(f"  Final:     {d.final_score:.3f}")
        print(f"  XGBoost:   {d.xgb_score:.3f}")
        print(f"  Rule:      {d.rule_score:.3f}")
        print(f"  Model:     {d.model_version.run_id} ({d.model_version.algorithm})")
        print(
            f"  Policy:    {d.policy_version.policy_name} hash={d.policy_version.policy_hash[:8]}"
        )
        print()
        print("=== Rules fired ===")
        for hit in d.rule_hits:
            print(f"  {hit.rule_id} [{hit.severity}] {hit.reason}")
        if d.rule_hits:
            print()
        print("=== Notes ===")
        print(case.notes or "—")
    else:
        print(json.dumps(case.model_dump(), indent=2, default=str))
    return 0


def cmd_act(args) -> int:
    from src.infrastructure.persistence.repos import CaseRepository

    repo = CaseRepository()
    try:
        repo.record_action(
            case_id=UUID(args.case_id),
            action=args.action,
            investigator=args.investigator,
            notes=args.notes,
        )
    except ValueError as e:
        print(f"Invalid action: {e}", file=sys.stderr)
        return 2
    print(
        f"Recorded: case={args.case_id} action={args.action} " f"investigator={args.investigator}"
    )
    return 0


def cmd_export(args) -> int:
    from src.infrastructure.persistence.repos import CaseRepository

    repo = CaseRepository()
    cases = repo.list_recent(limit=10_000, status=args.status)
    out = Path(args.output)
    with open(out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "case_id",
                "status",
                "opened_at",
                "closed_at",
                "investigator",
                "action",
                "final_score",
                "xgb_score",
                "rule_score",
                "model_run_id",
                "policy_hash",
                "rule_codes_hit",
                "amount_usd",
                "actor_account_id",
                "counterparty_country",
                "notes",
            ]
        )
        for case in cases:
            d = case.decision
            writer.writerow(
                [
                    case.case_id,
                    case.status,
                    case.opened_at,
                    case.closed_at,
                    case.investigator,
                    d.action.value,
                    d.final_score,
                    d.xgb_score,
                    d.rule_score,
                    d.model_version.run_id,
                    d.policy_version.policy_hash,
                    ",".join(h.rule_id for h in d.rule_hits),
                    "—",  # amount is on the event, not the decision
                    "—",  # actor_account_id is on the event
                    "—",  # counterparty_country is on the event
                    case.notes or "",
                ]
            )
    print(f"Exported {len(cases)} cases to {out}")
    return 0


def cmd_stats(args) -> int:
    from src.infrastructure.persistence.repos import StatsRepository

    repo = StatsRepository()
    stats = repo.window(window_minutes=args.window_hours * 60)
    if args.human:
        for k, v in stats.items():
            print(f"  {k:25s} {v}")
    else:
        print(json.dumps(stats, indent=2, default=str))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Investigator CLI for the Identity Intelligence Platform"
    )
    parser.add_argument("--human", action="store_true", help="Pretty-print output for terminals")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List recent cases")
    p_list.add_argument("--limit", type=int, default=20)
    p_list.add_argument(
        "--status", choices=["OPEN", "IN_REVIEW", "CONFIRMED_FRAUD", "FALSE_POSITIVE", "ESCALATED"]
    )
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show a single case")
    p_show.add_argument("case_id")
    p_show.set_defaults(func=cmd_show)

    p_act = sub.add_parser("act", help="Record an action on a case")
    p_act.add_argument("case_id")
    p_act.add_argument(
        "--action", required=True, choices=["confirm_fraud", "false_positive", "escalate"]
    )
    p_act.add_argument("--investigator", required=True)
    p_act.add_argument("--notes", default=None)
    p_act.set_defaults(func=cmd_act)

    p_export = sub.add_parser("export", help="Export cases to CSV")
    p_export.add_argument("--output", default="cases.csv")
    p_export.add_argument(
        "--status", choices=["OPEN", "IN_REVIEW", "CONFIRMED_FRAUD", "FALSE_POSITIVE", "ESCALATED"]
    )
    p_export.set_defaults(func=cmd_export)

    p_stats = sub.add_parser("stats", help="Operational stats")
    p_stats.add_argument("--window-hours", type=int, default=1)
    p_stats.set_defaults(func=cmd_stats)

    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as e:
        if args.human:
            print(f"Error: {e}", file=sys.stderr)
        else:
            print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    sys.exit(main())
