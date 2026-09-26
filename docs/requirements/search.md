# Search & Discovery — Functional Requirements

Prefix **SRCH**. See [README.md](README.md) for how to read, cite, and change these.

Finding the right song from 1,300+ is the core job. Search is the surface a listener reaches for
first, and everything it returns must be something they can act on.

---

## Finding songs

**SRCH-01** — Search MUST accept a plain-language query and return songs from the catalog. The user
is never required to know a title, a field name, or a search syntax.

**SRCH-02** — Search MUST support these modes, and a query MUST be answerable without the user
choosing one by hand:
- **natural language** — "something upbeat for a drive"
- **text** — title and metadata
- **lyric** — a remembered line or phrase
- **audio similarity** — "songs that sound like this one"
- **tempo** — a BPM or a BPM range
- **hybrid** — a combination of the above

**SRCH-03** — Search MUST return **song results** — actual catalog songs with their identity and
metadata — and not only prose about them. A search that answers in text alone has failed.

**SRCH-04** — Every result MUST be **playable directly from the result list**, without navigating
away from the results or losing them.
*Why:* finding the song is half the job; hearing it is the point.

**SRCH-05** — A result MUST carry enough metadata to tell songs apart at a glance — at minimum title,
plus what's known of genre, tempo, key, duration, and mood.

**SRCH-06** — A search that matches nothing MUST say so plainly. It MUST NOT show an empty screen, a
spinner that never resolves, or invented songs.

**SRCH-07** — Search results MUST only contain songs that exist in the catalog. A song the user
cannot then play or open is never a valid result.

**SRCH-08** — A search MUST return within a few seconds, or show the user that it is still working.
The interactive path targets ≤3s (OKR **KR1.1**).

---

## Acting on a result

**SRCH-09** — From a result the user MUST be able to: play it, add it to the radio queue, and view
its lyrics where lyrics exist.

**SRCH-10** — From a result the user MUST be able to ask for **more songs like this one**, and get
back a fresh result list in the same place.

**SRCH-11** — Playback started from a search result MUST NOT interrupt or hijack the live radio
stream; the two are separate listening contexts.

**SRCH-12** — A user MUST be able to ask **why** a given result matched, and get an explanation in
terms of the query.

---

## In-depth search

**SRCH-13** — The user MUST be able to opt into a slower, in-depth search that reasons over the
catalog in several steps.

**SRCH-14** — While an in-depth search runs, its progress MUST stay visible — the steps it has taken
so far, not just a spinner.
*Why:* the reasoning is most of the value of waiting for it.

**SRCH-15** — An in-depth search that fails MUST say what went wrong and leave the user able to
search again. It MUST NOT strand the page in a loading state.

---

## Lyrics

**SRCH-16** — A song's lyrics MUST be viewable without leaving the search results.

**SRCH-17** — Where a song has time-aligned lyrics, they MUST be followable in sync with playback.

**SRCH-18** — A song with no lyrics indexed MUST say so. Absent lyrics MUST NOT be presented as empty
lyrics or block the rest of the result's actions.
