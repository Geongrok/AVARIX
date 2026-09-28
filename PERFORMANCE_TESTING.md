# Intellex Performance Testing

This version adds **diagnostic timing only**. It does not intentionally change the
answer-routing behavior.

After deployment, ask 2–3 normal questions and inspect the server/Render logs.

Look for lines such as:

```text
[PERF] index_ready: 0.123s
[PERF] query_normalization: 0.001s
[PERF] db_search (8 candidates): 0.210s
[PERF] db_relevance (2 accepted): 7.842s
[PERF] db_evidence_excerpts: 0.002s
[PERF] answer_generation mode=openrouter: 5.931s
[PERF] TOTAL: 14.109s
[PERF] HTTP /api/chat TOTAL: 14.115s
```

For web fallback, the logs also show individual search attempts:

```text
[PERF] web.primary[duckduckgo]: 2.104s
[PERF] web.retry[bing]: 12.002s
[PERF] web.retry[brave]: 1.221s
```

### What to send back

Copy the `[PERF]` lines from **one database question** and **one web-fallback
question**.

Do not send API keys or other secrets.

### After profiling

Set:

```text
INTELLEX_PERF_LOG=0
```

in Render if you want to turn the diagnostic logs off.
