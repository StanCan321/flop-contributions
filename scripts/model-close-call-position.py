#!/usr/bin/env python3
"""Model one hypothetical Close Call opening position without signing or posting it."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import sys


CENT = Decimal("0.01")
MINT = Decimal("10000")
FEE_RATE = Decimal("0.01")


def amount(value: str, label: str, *, minimum: Decimal = Decimal("0.01")) -> Decimal:
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a decimal string") from exc
    if (not result.is_finite() or result < minimum or result.as_tuple().exponent < -2):
        raise ValueError(f"{label} must be positive with at most two decimal places")
    return result


def fee(side: str, qty: Decimal, entry: Decimal, close: Decimal) -> tuple[Decimal, Decimal]:
    base = FEE_RATE * qty * entry
    gap = (close - entry) * qty
    buyer, seller = max(base, gap), max(base, -gap)
    return (buyer, seller) if side == "buy" else (seller, buyer)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--side", required=True, choices=("buy", "sell"))
    parser.add_argument("--quantity", required=True)
    parser.add_argument("--entry-price", required=True)
    parser.add_argument("--sweep-close", required=True,
                        help="hypothetical closing reference for the execution sweep")
    parser.add_argument("--reference", help="previous signed reference used for the 5%% limit")
    parser.add_argument("--settlement-price", action="append", required=True)
    args = parser.parse_args()
    try:
        qty = amount(args.quantity, "quantity", minimum=Decimal("0.10"))
        entry = amount(args.entry_price, "entry price")
        close = amount(args.sweep_close, "sweep close")
        maker_fee, counterparty_fee = fee(args.side, qty, entry, close)
        collateral = qty * entry
        required_cash = collateral + maker_fee
        if required_cash > MINT:
            raise ValueError("hypothetical position exceeds the initial account's cash requirement")
        within_limits = None
        reference = None
        if args.reference is not None:
            reference = amount(args.reference, "reference")
            within_limits = abs(entry - reference) <= Decimal("0.05") * reference
        direction = Decimal(1) if args.side == "buy" else Decimal(-1)
        scenarios = []
        for value in args.settlement_price:
            settlement = amount(value, "settlement price")
            score = direction * qty * (settlement - entry) - maker_fee
            scenarios.append({"settlement_price": str(settlement),
                              "score_after_fee": str(score.quantize(CENT)),
                              "ending_value": str((MINT + score).quantize(CENT))})
        break_even = entry + direction * (maker_fee / qty)
        report = {
            "schema_version": 1, "mode": "offline_hypothetical_position",
            "side": args.side, "quantity": str(qty), "entry_price": str(entry),
            "sweep_close": str(close), "reference": str(reference) if reference else None,
            "within_five_percent_limit": within_limits,
            "maker_fee": str(maker_fee.quantize(CENT)),
            "counterparty_fee": str(counterparty_fee.quantize(CENT)),
            "opening_collateral": str(collateral.quantize(CENT)),
            "required_cash": str(required_cash.quantize(CENT)),
            "cash_headroom": str((MINT - required_cash).quantize(CENT)),
            "break_even_settlement_price": str(break_even.quantize(CENT)),
            "scenarios": scenarios,
            "limitations": [
                "assumes the trade settles in full and opens a new position",
                "does not predict NVDA, ranking, counterparty behavior, or execution",
                "does not create terms, signatures, messages, or network requests",
            ],
            "network_access": False, "side_effects": False,
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
