# Small public reference series used by the Findings section

`btc_price_daily.csv` — daily Bitcoin market price in USD (`market-price` chart: average USD market price across major
exchanges, one value per UTC day), from the Blockchain.com Charts API,
`https://api.blockchain.info/charts/market-price?timespan=1year&start=2017-10-01&format=csv&sampled=false`,
retrieved 2026-11-01 and cut to 2017-10-01 – 2018-09-30 (365 days). Used only to date market phases (peak, troughs,
rebounds are computed from this series, not typed in) and to align Reddit activity with price movements.
It is reference context, not a trading dataset; no claim about causation in either direction is made from it.

Cross-check (2026-11-01): the same 365 days from Coin Metrics community data (`coinmetrics/data`, `PriceUSD`) correlate at
r = 0.984 with a median absolute difference of 2.5 %; the peak falls on 16 Dec 2017 ($19,641) in Coin Metrics and on
17 Dec 2017 ($19,280) in Blockchain.com, a one-day reference-time difference. Dates derived from the series are therefore
quoted to the day with that caveat.
