/**
 * The name a detected session take is headed by.
 *
 * A take has no title of its own — it is a stretch of a rehearsal the scan
 * thought was a song — so its name is derived from the words the band actually
 * sang. That derivation is pure logic and lives here rather than inside the card,
 * so the rule can be tested directly (SESS-12).
 *
 * Two things the rule must never do: run long (the transcript is a whole
 * paragraph of sung lines, and a producer telling nine attempts apart is
 * scanning, not reading), and invent a title for a take that sang nothing
 * (CAT-03).
 */

/** The most words a generated name may carry (SESS-12). */
export const MAX_NAME_WORDS = 6;

/** What a take with no words of its own is called. */
export const WORDLESS_NAME = 'Instrumental';

export interface TakeName {
  /** The headline to show. Either an excerpt of the take's own words, or `WORDLESS_NAME`. */
  text: string;
  /** Words were dropped, so the display must mark the name as an excerpt. */
  shortened: boolean;
  /** The take sang nothing, so `text` is an honest label rather than a title. */
  wordless: boolean;
}

/** A "word" needs at least one letter or digit — stray punctuation is not a name. */
const hasSubstance = (word: string): boolean => /[\p{L}\p{N}]/u.test(word);

export function takeName(transcript: string | null | undefined): TakeName {
  const words = (transcript ?? '').split(/\s+/).filter(hasSubstance);

  if (words.length === 0) {
    return { text: WORDLESS_NAME, shortened: false, wordless: true };
  }

  const kept = words.slice(0, MAX_NAME_WORDS);
  const shortened = words.length > kept.length;

  // Trailing punctuation left where the cut fell would read as "again,…", so it
  // goes — the words themselves are untouched.
  const text = shortened
    ? kept.join(' ').replace(/[,;:.!?\-–—]+$/u, '')
    : kept.join(' ');

  return { text, shortened, wordless: false };
}
