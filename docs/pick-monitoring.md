# PICK monitoring design

## Purpose
Track every published Chart View PICK after publication and compare current facts with the thesis that existed at selection time.

## State machine
- `PENDING_REVIEW`: baseline exists but no fresh post-pick review has been completed yet.
- `KEEP`: thesis remains intact.
- `WATCH`: thesis is weaker or an important fact needs confirmation.
- `SELL_REVIEW`: material thesis damage has been detected and user review is required.
- `EXIT`: only after explicit user confirmation.

## Safety rules
1. Price decline, RSI, moving-average breaks, volume decline, foreign selling, or a single target-price cut never trigger `SELL_REVIEW` by themselves.
2. `SELL_REVIEW` requires either one material verified fact or at least two independent weakening signals.
3. Technical signals are timing/context only.
4. The system never changes `SELL_REVIEW` to `EXIT` automatically.
5. Historical `ai_daily_rankings.json` entries remain immutable; monitoring state lives separately.

## Files
- `static/data/pick_monitor.json`: latest state per published pick.
- `static/data/pick_monitor_history.json`: append-only state/baseline events.
- `scripts/build_pick_monitor.py`: synchronizes new published PICKs without overwriting review state.
- `tests/test_pick_monitor.py`: regression coverage for fail-safe behavior.

## Future publication contract
New PICK rows may include an optional `monitoring` object:

```json
{
  "monitoring": {
    "summary": "one-line investment thesis",
    "thesisPillars": ["pillar 1", "pillar 2"],
    "invalidationCriteria": ["fact that would break the thesis"],
    "catalysts": ["expected catalyst"],
    "keyMetrics": ["metric to re-check"]
  }
}
```

Legacy picks are initialized from their published `reason` only and marked `legacy_baseline`; the system must not invent missing invalidation criteria.
