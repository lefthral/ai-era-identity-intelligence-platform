"""Latency benchmark for the real-time scorer.

Measures p50/p95/p99/max for the full compute-features + score pipeline
across N synthetic events. Use this to validate the 200ms p99 target
from the architecture document.

Run:
    python -m scripts.benchmark
    python -m scripts.benchmark --n 10000
"""

from __future__ import annotations

import argparse
import logging
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.application.scoring import RealTimeScorer
from src.domain.decisions import ModelVersion
from src.generators.arup_pattern import generate_arup_events
from src.generators.baseline import generate_baseline_events
from src.generators.singapore_pattern import generate_singapore_events

logger = logging.getLogger("benchmark")


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    parser = argparse.ArgumentParser(description="Scorer latency benchmark")
    parser.add_argument("--n", type=int, default=5000, help="Total events to score")
    parser.add_argument("--warmup", type=int, default=100, help="Warmup events (excluded)")
    parser.add_argument("--use-model", action="store_true", help="Use XGBoost if available")
    args = parser.parse_args()

    # Build the event set
    events = []
    events.extend(generate_baseline_events(seed=42, n_events=args.n - 18))
    events.extend(generate_arup_events(seed=20240115))
    events.extend(generate_singapore_events(seed=20250326))
    events.sort(key=lambda e: e.event_time)
    events = events[: args.n]

    model_path = Path("models/xgb_v1.ubj") if args.use_model else None
    if args.use_model and not model_path.exists():
        print(f"[warn] {model_path} not found; falling back to heuristic")
        model_path = None

    scorer = RealTimeScorer(
        model_path=model_path,
        model_version=ModelVersion(
            run_id="bench_v1",
            model_name="identity_intel_xgb",
            stage="Production",
            algorithm="xgboost" if model_path else "heuristic",
            trained_at=datetime.now(UTC),
            metrics={},
        ),
    )
    # Warmup
    for event in events[: args.warmup]:
        scorer.score(event)

    # Measure
    latencies = []
    t0_all = time.perf_counter()
    for event in events[args.warmup :]:
        t0 = time.perf_counter()
        scorer.score(event)
        latencies.append((time.perf_counter() - t0) * 1000)
    elapsed_s = time.perf_counter() - t0_all

    latencies.sort()
    p50 = latencies[len(latencies) // 2]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    pmax = latencies[-1]
    avg = statistics.mean(latencies)
    throughput = len(latencies) / elapsed_s

    print(f"\nLatency benchmark (n={len(latencies)}, model={'xgb' if model_path else 'heuristic'})")
    print(f"  p50:    {p50:7.2f} ms")
    print(f"  p95:    {p95:7.2f} ms")
    print(f"  p99:    {p99:7.2f} ms")
    print(f"  max:    {pmax:7.2f} ms")
    print(f"  mean:   {avg:7.2f} ms")
    print(f"  total:  {elapsed_s:7.2f} s")
    print(f"  throughput: {throughput:7.0f} events/sec")
    print()
    if p99 < 200:
        print("  [PASS] p99 < 200ms (production target)")
    else:
        print(f"  [WARN] p99 = {p99:.1f}ms exceeds 200ms target")


if __name__ == "__main__":
    main()
