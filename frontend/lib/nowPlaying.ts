/**
 * What the radio page should say is playing, derived from the radio state.
 *
 * The backend reconciles its state against the audio actually on the air (issue
 * #101) and reports three things this needs: whether it could ask the stream at
 * all, whether the song on air came from the queue or from the fallback source,
 * and the track length the stream reports for songs the catalog has no duration
 * for. Turning that into one of four display states is pure logic, so it lives
 * here and is unit-tested rather than tangled into the page.
 */

export interface NowPlayingSong {
  id: number;
  title: string;
  duration?: number | null;
}

export interface NowPlayingState {
  current_song: NowPlayingSong | null;
  stream_known?: boolean;
  current_song_source?: string | null;
  stream_duration?: number | null;
  position?: number;
}

/**
 * - `unknown` — the stream could not be asked. We do not name a song, because the
 *   last one we knew about may already be wrong (PLAT-07).
 * - `queued` — a song somebody queued is on the air.
 * - `fallback` — catalog music the stream picked itself, the queue being empty.
 * - `silent` — nothing nameable is on the air.
 */
export type NowPlayingKind = 'unknown' | 'queued' | 'fallback' | 'silent';

export interface NowPlaying {
  kind: NowPlayingKind;
  song: NowPlayingSong | null;
  position: number;
  /** Null when neither the catalog nor the stream knows how long the track is. */
  duration: number | null;
  /** 0..1, or null when there is no duration to measure against (CAT-02). */
  progress: number | null;
}

function positiveOrNull(value: number | null | undefined): number | null {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;
}

export function describeNowPlaying(state: NowPlayingState | null | undefined): NowPlaying {
  const unknown: NowPlaying = {
    kind: 'unknown',
    song: null,
    position: 0,
    duration: null,
    progress: null,
  };

  // Fail closed: a payload that does not say the stream was reached is treated as
  // not reached, rather than as a song we can vouch for.
  if (!state || state.stream_known !== true) return unknown;

  const position = positiveOrNull(state.position) ?? 0;

  if (!state.current_song) {
    return { kind: 'silent', song: null, position, duration: null, progress: null };
  }

  // The stream's own length is the fallback, so a catalog row with no duration
  // still shows progress instead of sitting at 0:00 (CAT-02).
  const duration =
    positiveOrNull(state.current_song.duration) ?? positiveOrNull(state.stream_duration);

  return {
    kind: state.current_song_source === 'fallback' ? 'fallback' : 'queued',
    song: state.current_song,
    position,
    duration,
    progress: duration === null ? null : Math.min(1, Math.max(0, position / duration)),
  };
}
