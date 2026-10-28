# Five-minute demo script

Start `python atlas/serve.py` (opens http://127.0.0.1:8000) before presenting. Each step lists the view, what to say, and the figure on screen; all figures come from the current build.

| Time | Do | Say |
|---|---|---|
| 0:00 | **Discoveries** page. Click **Raw overlap** on the hero map, then **Adjusted**. | "We took 210,325,806 Reddit comments from 170 subreddits. If you link communities whenever they share a commenter, 99.99% of pairs are linked: a hairball. When we keep only pairs that share far more commenters than size and activity predict, 13.9% remain, and topics appear." |
| 0:45 | **Atlas**. Search **personalfinance**. | "By raw overlap its neighbours are hubs like r/AskReddit and r/pics. Adjusted, they are r/financialindependence (2.11×) and r/RealEstate. The number is observed ÷ expected shared commenters." |
| 1:30 | **Stories → Unexpected neighbours** (step 1). | "r/CanadaPolitics and r/PersonalFinanceCanada share 1,536 commenters where 249 were expected, at least 7.07× in every quarter. The UK pair is next: nationality, not topic, organises these audiences." |
| 2:15 | **Stories → When crowds arrive and leave**: timeline, then steps 2–3, then the Marvel step. | "Crypto commenters fell 81% after Bitcoin's December 2017 peak while the frame grew. The remaining Bitcoin and CryptoCurrency audiences went from 3.37× to 9.8×. The Infinity War crowd did the opposite: Marvel affinity dropped to 3.94× in April. This is association, not causation." |
| 3:15 | **Methods & data**: scroll through the pipeline and "How we checked it". | "Fetch, salted hashing and cleaning, then the BiCM null model and a 1% false discovery rate. Our implementation matches the published `bicm` package link-for-link, and automated tests recompute every story number from the published data." |
| 4:00 | **Methods → How the project evolved**, then **Compare → Two periods**. | "We set out to test whether bridge positions outlast their occupants. The first network was 99.85% dense with only 6 possible bridges, so we changed the measurement lens. Links are stable (0.82–0.85 quarter to quarter), and the remaining changes are visible here." |
| 4:40 | Back to **Atlas**; hover a connector such as r/Frugal. | "Limits: one sample of 170 subreddits, 12 months, comments only, no text. Everything is aggregate and reproducible with one command." |

**If something fails live:** every view is a URL, and `docs/screenshots/` holds a capture of each step.
