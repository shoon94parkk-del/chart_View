# GPT daily TOP3 publishing contract

The automated Korean screener is a **candidate generator only**. It must never
write public AI recommendations. The scheduled GPT review reads the exact-date
candidate input and writes the final three reviewed picks to GitHub.

## Daily GPT task prompt

Use this as the scheduled GPT task instruction:

```text
Open static/data/screener_top100.json in shoon94parkk-del/chart_View after the
Korean market close. It is the candidate universe, not a recommendation list.
Review the candidates using company growth first: earnings/revenue outlook,
competitive position, industry tailwinds, valuation, catalysts and risks. Use
technical signals only as entry-timing evidence.

Select exactly three Korean stocks. Update static/data/ai_daily_rankings.json by
adding or replacing only the entry whose tradeDate equals screener_top100.json's
tradeDate. Set analysis.sourceType to gpt_screener_review, analysis.status to
complete, analysis.model to the model actually used, analysis.candidateTradeDate
to that trade date, and analysis.analyzedAt to the current KST timestamp.

Use scorePolicy weights companyGrowth 35, industry 15, valuation 10,
catalystRisk 10, technical 30. Fundamental factors therefore total 70 points
and technical timing is limited to 30 points. Every pick needs all five component scores,
their exact summed totalScore, closing price from the candidate file, grade, and
a concise Korean reason that states both the growth thesis and a material risk.

Do not publish a ranking when the candidate file is stale, incomplete, or cannot
be reviewed. Do not replace historical dates. Commit only the ranking JSON with
the message: data: publish GPT-reviewed TOP3 YYYY-MM-DD.
```

## Required record shape

```json
{
  "tradeDate": "YYYY-MM-DD",
  "status": "GPT 검토 TOP3 — YYYY-MM-DD 종가 기준",
  "analysis": {
    "sourceType": "gpt_screener_review",
    "status": "complete",
    "model": "actual GPT model name",
    "candidateTradeDate": "YYYY-MM-DD",
    "analyzedAt": "YYYY-MM-DDTHH:mm:ss+09:00",
    "candidateFile": "static/data/screener_top100.json"
  },
  "scorePolicy": {
    "version": "growth-first-v2",
    "weights": {"companyGrowth": 35, "industry": 15, "valuation": 10, "catalystRisk": 10, "technical": 30}
  },
  "top3": ["exactly three complete, ranked pick objects"]
}
```

Run `py -3.13 scripts/validate_ai_rankings.py` before committing when a local
checkout is available. The website reads the ranking file directly with a fresh
request, so a successful GitHub commit is displayed after Render deploys it.
