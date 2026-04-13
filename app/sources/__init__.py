"""Source connectors for job ingestion."""

# Lookback window in days — set by pipeline before fetching.
# 30 for initial ingestion (empty DB), 7 for daily sync.
_lookback_days: int = 7
