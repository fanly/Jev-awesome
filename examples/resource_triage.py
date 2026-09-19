#!/usr/bin/env python3
"""Minimal TypeSafe / Jev triage example using the official Python SDK surface.

Default mode is offline mock — never calls a paid API unless you pass --live
and set TYPESAFE_API_KEY.
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass


@dataclass
class TriageResult:
    category: str
    needs_human: bool
    source: str


def mock_triage(document: str) -> TriageResult:
    """Structural stand-in. Not a Jev judgment."""
    lower = document.lower()
    if "charge" in lower or "billing" in lower or "扣款" in document:
        category = "billing"
    elif "crash" in lower or "error" in lower or "报错" in document:
        category = "technical"
    else:
        category = "other"
    needs_human = "asap" in lower or "紧急" in document
    return TriageResult(category=category, needs_human=needs_human, source="mock")


def live_triage(document: str) -> TriageResult:
    """Real SDK call. Requires TYPESAFE_API_KEY and network access."""
    from typesafe_sdk import Choice, Noul, TypeSafeClient

    with TypeSafeClient() as client:
        response = client.system_one(
            state={"document": document},
            questions={
                "category": Choice(
                    instructions="What is this support ticket about?",
                    criteria={
                        "billing": "Charges, invoices, refunds, payments",
                        "technical": "Bugs, crashes, API errors, integrations",
                        "other": "Anything else",
                    },
                ),
                "needs_human": Noul(
                    instructions="Does this need urgent human attention?",
                ),
            },
        )
    category = response.choices["category"].choice
    needs_human = bool(response.nouls["needs_human"].noul)
    return TriageResult(category=str(category), needs_human=needs_human, source="typesafe_sdk")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Call the real TypeSafe API (requires TYPESAFE_API_KEY).",
    )
    parser.add_argument(
        "--document",
        default="I was charged twice. Please fix this ASAP.",
        help="Ticket text to triage.",
    )
    args = parser.parse_args(argv)

    if args.live:
        if not os.environ.get("TYPESAFE_API_KEY"):
            print("TYPESAFE_API_KEY is not set; refusing --live.", file=sys.stderr)
            return 2
        result = live_triage(args.document)
    else:
        result = mock_triage(args.document)

    print(f"source={result.source}")
    print(f"category={result.category}")
    print(f"needs_human={result.needs_human}")
    if result.source == "mock":
        print(
            "note=mock only; structure mirrors Choice+Noul usage, not real Jev output",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
