#!/usr/bin/env python3
"""
Calibration analysis for Tianjin's predicted_prob vs. observed win rate.

Usage: python scripts/calibrate.py [path/to/trades.jsonl]
"""
import json
import sys
from collections import defaultdict
from pathlib import Path


def load_trades(path: str) -> list[dict]:
    trades = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                trades.append(json.loads(line))
    return [t for t in trades if t.get("outcome") in ("win", "loss")]


def calibration_report(trades: list[dict]):
    # Bucket by edge range
    buckets = defaultdict(list)
    for t in trades:
        edge = t.get("edge", 0)
        if edge < 0.05:
            buckets["[0.01-0.05)"].append(t)
        elif edge < 0.08:
            buckets["[0.05-0.08)"].append(t)
        else:
            buckets["[0.08+]"].append(t)

    total_wins = sum(1 for t in trades if t["outcome"] == "win")
    total_pnl = sum(t.get("pnl", 0) for t in trades)

    print(f"Total settled trades: {len(trades)}")
    print(f"Overall: {total_wins}W / {len(trades) - total_wins}L "
          f"({total_wins / len(trades) * 100:.1f}%) PnL: ${total_pnl:+.2f}\n")

    print(f"{'Bucket':<15} {'N':>5} {'Wins':>6} {'Win%':>7} {'Avg Edge':>10} {'PnL':>10}")
    print("-" * 55)
    for label in ["[0.01-0.05)", "[0.05-0.08)", "[0.08+]"]:
        bucket = buckets[label]
        if not bucket:
            continue
        wins = sum(1 for t in bucket if t["outcome"] == "win")
        avg_edge = sum(t.get("edge", 0) for t in bucket) / len(bucket)
        pnl = sum(t.get("pnl", 0) for t in bucket)
        print(f"{label:<15} {len(bucket):>5} {wins:>6} "
              f"{wins / len(bucket) * 100:>6.1f}% {avg_edge:>10.3f} ${pnl:>+9.2f}")

    # Direction breakdown
    print(f"\n{'Direction':<10} {'N':>5} {'Wins':>6} {'Win%':>7}")
    print("-" * 30)
    for d in ["UP", "DOWN"]:
        dt = [t for t in trades if t.get("direction") == d]
        if dt:
            dw = sum(1 for t in dt if t["outcome"] == "win")
            print(f"{d:<10} {len(dt):>5} {dw:>6} {dw / len(dt) * 100:>6.1f}%")

    print(f"\nIf win rates are similar across edge buckets, k needs recalibration.")
    print(f"If higher-edge buckets win more, the model is working.")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "trades.jsonl"
    if not Path(path).exists():
        print(f"No trades file at {path}")
        sys.exit(1)
    trades = load_trades(path)
    if len(trades) < 5:
        print(f"Only {len(trades)} settled trades — need more for meaningful calibration.")
        sys.exit(0)
    calibration_report(trades)
