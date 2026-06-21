# Product OKRs — Big Flavor Band Agent

**Mission (north star):** Make it effortless to **discover, play, and produce** music from the Big
Flavor Band's ~1,300-song catalog — using AI search, an AI DJ, and audio-production tools.

These OKRs are the rubric the **CPO agent** uses to decide whether an incoming issue is worth fixing
at all. An issue earns a greenlight when resolving it would plausibly advance at least one Key Result
below. They are also the reference the product-manager agent uses when writing success metrics.

> Keep these stable. If the product strategy genuinely shifts, update this file in a dedicated commit
> so the change is auditable — the agents treat it as the source of truth.

---

## O1 — Finding the right song from the catalog is fast and accurate
*The core job. A listener or producer can surface exactly what they want from 1,300+ songs.*

- **KR1.1** A natural-language, lyric, or "sounds-like" search returns relevant results in ≤3 seconds.
- **KR1.2** The top result is the intended song for a clearly-specified query (title, lyric snippet,
  or mood) the large majority of the time.
- **KR1.3** Every song in the catalog is fully indexed — metadata, lyrics, and audio embeddings — so
  no song is unfindable.

## O2 — The AI DJ / agent produces a great listen with little effort
*Ask in plain language; get a playable set or a useful answer.*

- **KR2.1** A DJ/playlist request ("an upbeat 30-minute set," "songs like X") returns a coherent,
  playable queue in one ask.
- **KR2.2** Agent responses ground their song picks in the actual catalog (no hallucinated songs).
- **KR2.3** The chosen LLM (local Ollama or hosted Claude) is swappable by config with no change in
  user-facing behavior.

## O3 — The radio stream is reliable and always-on
*Listeners should hear continuous music, never dead air.*

- **KR3.1** The stream never falls back to silence/`blank()` while playable songs are queued.
- **KR3.2** Queue actions (add / skip / remove / play / pause) are reflected in the live stream
  within a few seconds.
- **KR3.3** Radio survives backend restarts without manual intervention to recover the stream.

## O4 — The catalog stays trustworthy and the system stays operable
*Good data and a deployable, observable stack underpin everything above.*

- **KR4.1** Scraping/ingest keeps the catalog complete and duplicate-free; re-runs can process only
  missing data.
- **KR4.2** Search results are never wrong because of stale or corrupt indexes (lyrics/audio/text
  stay in sync with the songs).
- **KR4.3** The stack deploys to production from a documented, repeatable process, with logs that
  make a failure diagnosable.

## O5 — Production & editing tools give real creative leverage
*The catalog isn't just searchable — it's workable.*

- **KR5.1** Audio analysis (tempo, key, beats) on a catalog song returns correct, usable values.
- **KR5.2** A producer can tempo-match or build a beat-matched transition between two songs without
  pitch artifacts.
- **KR5.3** Editing a song's metadata/lyrics is safe and persists correctly without breaking its
  indexes.

---

### How to read these for triage

- An issue does **not** need to name an OKR to qualify — it needs a believable line from "we fixed
  this" to "a Key Result moved." A search returning the wrong song serves **O1**; the stream cutting
  to silence serves **O3**; a scraper missing songs serves **O4**; a broken tempo-match serves **O5**.
- "Nice idea, but it doesn't move any KR and adds surface area" is a decline.
- "Hard or large" is **not** a decline — cost is the PM's and developer's problem, not a strategic
  gate.
