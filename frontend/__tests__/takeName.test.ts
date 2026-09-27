/**
 * How a detected take is named (issue #108, SESS-12).
 *
 * The transcript is a paragraph of whatever the band sang over the take, so the
 * cases that matter are: it is cut to six words, it is cut on a word boundary,
 * the cut is visible as an excerpt, a short take keeps its whole line, and a take
 * that sang nothing is labelled rather than titled (CAT-03).
 */
import { describe, it, expect } from 'vitest';

import { MAX_NAME_WORDS, WORDLESS_NAME, takeName } from '@/lib/takeName';

const wordCount = (text: string) => text.split(/\s+/).filter(Boolean).length;

describe('takeName', () => {
  it('cuts a long transcript to six words', () => {
    const result = takeName(
      "gardening at night is never where i want to be and the fences are all down"
    );

    expect(result.text).toBe('gardening at night is never where');
    expect(wordCount(result.text)).toBe(MAX_NAME_WORDS);
    expect(result.shortened).toBe(true);
    expect(result.wordless).toBe(false);
  });

  it('never cuts mid-word', () => {
    // 70 characters — the old rule's limit — falls inside "extraordinary".
    const result = takeName('an unmistakably long and extraordinarily wordy opening line here');

    expect(result.shortened).toBe(true);
    expect('an unmistakably long and extraordinarily wordy opening line here').toContain(
      `${result.text} `
    );
  });

  it('leaves a name that is already short enough whole and unmarked', () => {
    const result = takeName('so tired of waiting');

    expect(result.text).toBe('so tired of waiting');
    expect(result.shortened).toBe(false);
    expect(result.wordless).toBe(false);
  });

  it('keeps exactly six words without marking them as an excerpt', () => {
    const result = takeName('one two three four five six');

    expect(result.text).toBe('one two three four five six');
    expect(result.shortened).toBe(false);
  });

  it('collapses the transcript whitespace, including line breaks', () => {
    const result = takeName('  here   comes\na big\tsolo  ');

    expect(result.text).toBe('here comes a big solo');
    expect(result.shortened).toBe(false);
  });

  it('drops punctuation left dangling at the cut', () => {
    const result = takeName('we are going to try that again, from the top');

    expect(result.text).toBe('we are going to try that');
    expect(result.shortened).toBe(true);
  });

  it('labels a take with no words rather than inventing a title', () => {
    for (const transcript of [null, undefined, '', '   ', '...', '- , -']) {
      const result = takeName(transcript);

      expect(result.text).toBe(WORDLESS_NAME);
      expect(result.wordless).toBe(true);
      expect(result.shortened).toBe(false);
    }
  });

  it('names the same take the same way every time', () => {
    const transcript = 'she said the rain would come before the harvest was in';

    expect(takeName(transcript)).toEqual(takeName(transcript));
  });

  it('never exceeds six words, whatever the transcript', () => {
    const transcripts = [
      'a',
      'a b c d e f g h i j k l',
      'hello hello tv listeners this is big flavor coming at you live',
      '1 2 3 4 5 6 7',
    ];

    for (const transcript of transcripts) {
      expect(wordCount(takeName(transcript).text)).toBeLessThanOrEqual(MAX_NAME_WORDS);
    }
  });
});
