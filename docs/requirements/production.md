# Production & Editing — Functional Requirements

Prefix **PROD**. See [README.md](README.md) for how to read, cite, and change these.

The catalog isn't just searchable, it's workable. Production tools change real audio, so the
governing promise here is that **nothing destroys the original**.

Access: the produce and edit surfaces are editor-gated — see [accounts.md](accounts.md).

---

## Nothing is destroyed

**PROD-01** — A production operation MUST NOT overwrite or destroy a song's original audio. Output is
always a new version alongside the original.

**PROD-02** — A producer MUST be able to **hear a change before committing it**. Every operation that
alters audio has a preview or audition path.

**PROD-03** — A producer MUST be able to **discard** a proposed change and be left exactly where they
started.

**PROD-04** — A song MUST be able to hold multiple versions, and the producer MUST be able to see
them, name them, audition them, choose which is the default, and delete one.

**PROD-05** — Changing which version is the default MUST NOT delete or hide the others.

---

## Analysis

**PROD-06** — Audio analysis MUST return correct, usable values for tempo, key, and beats on a
catalog song (OKR **KR5.1**).

**PROD-07** — Analysis that cannot produce a confident value MUST report that, not a plausible guess.

**PROD-08** — A producer MUST be able to see what analysis found before acting on it — the recommended
fixes, not just an "improve" button.

---

## Applying fixes

**PROD-09** — A fix that does **less than it claimed** MUST report that to the producer. A tool that
silently fell back to a weaker operation, or did nothing, MUST NOT be reported as applied.
*Why:* a silent partial success is worse than a visible failure — the producer moves on believing
the problem is fixed.

**PROD-10** — Batch operations over many songs MUST report per-song outcomes, and a failure on one
song MUST NOT abort the rest.

**PROD-11** — A long-running operation MUST show progress and MUST survive a page reload — reopening
the page picks the work back up rather than losing it.

---

## Stems

**PROD-12** — A producer MUST be able to separate a song into stems, see each stem on its own, and
audition stems individually and together.

**PROD-13** — Stem waveforms MUST be visible, and playback position MUST be visible against them.

**PROD-14** — A producer MUST be able to adjust a stem and hear the result before rendering a mix.

**PROD-15** — Rendering a mix from stems MUST produce a new version (**PROD-01**), never a
replacement of the source.

---

## Lyrics editing

**PROD-16** — An editor MUST be able to view and correct a song's lyrics, and the correction MUST
persist (OKR **KR5.3**).

**PROD-17** — A lyric edit MUST NOT break the song's searchability — lyric search MUST reflect the
corrected text (**CAT-06**).

**PROD-18** — Automatic lyric extraction MUST be offered as a starting point a human can correct,
never as a final answer that overwrites a human's edit without asking.
