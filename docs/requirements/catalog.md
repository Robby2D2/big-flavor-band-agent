# Catalog & Data — Functional Requirements

Prefix **CAT**. See [README.md](README.md) for how to read, cite, and change these.

Everything else in the product is a view onto the catalog. If the catalog is incomplete, stale, or
duplicated, search lies and the DJ hallucinates.

---

## Completeness

**CAT-01** — Every song in the catalog MUST be findable. A song that exists but cannot be surfaced by
any search mode is a defect (OKR **KR1.3**).

**CAT-02** — A song MUST carry, at minimum, a stable identity and a title. Everything else —
genre, tempo, key, duration, mood, energy, recording date — is optional and MUST degrade gracefully
when absent.

**CAT-03** — Missing data MUST be shown as missing. The product MUST NOT invent, infer-and-present,
or silently zero-fill a value the catalog does not have.

**CAT-04** — The catalog MUST be free of duplicate songs (OKR **KR4.1**). Re-running ingest MUST NOT
create a second copy of a song already present.

---

## Indexes stay in sync

**CAT-05** — A song's searchable representations — metadata, lyrics, audio embeddings — MUST stay
consistent with the song itself (OKR **KR4.2**). A search result MUST NOT be wrong because an index
is stale.

**CAT-06** — Editing a song's metadata or lyrics MUST update whatever indexes depend on them, or the
edit is not complete (OKR **KR5.3**).

**CAT-07** — Deleting or replacing a song's audio MUST NOT leave orphaned embeddings that can still
be returned by search.

---

## Ingest

**CAT-08** — Ingest MUST support an **incremental** run that processes only what is missing, without
reprocessing the whole catalog.
*Why:* full re-indexing is expensive and is the usual cause of a long outage in search quality.

**CAT-09** — An ingest run that fails partway MUST be safe to re-run. It MUST NOT leave half-written
songs that look complete.

**CAT-10** — Ingest MUST NOT overwrite a human edit with scraped data without that being the
explicit intent of the run.
