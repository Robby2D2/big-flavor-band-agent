/**
 * Uploading a Reaper session zip, a chunk at a time.
 *
 * A session is multiple gigabytes — the band's sample was 2 GB — while nginx
 * caps a request body at 100 MB and gives it 60 seconds. So the file is sliced
 * and sent piece by piece: every request stays small, progress is real rather
 * than a spinner, and a failed piece is retried on its own instead of restarting
 * the whole upload.
 */

/** Bytes per request. Comfortably under the proxy's 100 MB body cap. */
export const CHUNK_BYTES = 25 * 1024 * 1024;

/** How many times one chunk is retried before the upload gives up. */
export const CHUNK_RETRIES = 3;

export interface UploadProgress {
  /** Bytes confirmed by the server. */
  uploaded: number;
  total: number;
  /** 0-100, for a progress bar. */
  percent: number;
}

export interface SessionSummary {
  id: number;
  name: string;
  recorded_on: string | null;
  status: string;
  stage: string | null;
  progress: number;
  error: string | null;
}

/** Byte ranges covering a file of this size, in order. */
export function chunkRanges(
  size: number,
  chunkBytes: number = CHUNK_BYTES
): { start: number; end: number }[] {
  const ranges: { start: number; end: number }[] = [];
  for (let start = 0; start < size; start += chunkBytes) {
    ranges.push({ start, end: Math.min(start + chunkBytes, size) });
  }
  return ranges;
}

export function progressFor(uploaded: number, total: number): UploadProgress {
  // A zero-length file would divide by zero; it also cannot be a session, but
  // the caller should get a sane number rather than NaN.
  const percent = total > 0 ? Math.min(100, Math.round((uploaded / total) * 100)) : 0;
  return { uploaded, total, percent };
}

async function readError(response: Response, fallback: string): Promise<string> {
  const body = await response.json().catch(() => null);
  return body?.error || fallback;
}

/**
 * Open a session, send the file in chunks, then start the scan.
 *
 * Resolves with the session once the scan has been *started* — the scan itself
 * takes tens of minutes and is followed by polling the session, not by this call.
 */
export async function uploadSession(
  file: File,
  options: {
    onProgress?: (progress: UploadProgress) => void;
    signal?: AbortSignal;
    chunkBytes?: number;
    fetchImpl?: typeof fetch;
  } = {}
): Promise<SessionSummary> {
  const {
    onProgress,
    signal,
    chunkBytes = CHUNK_BYTES,
    fetchImpl = fetch,
  } = options;

  const created = await fetchImpl('/api/produce/sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ filename: file.name }),
    signal,
  });
  if (!created.ok) {
    throw new Error(await readError(created, 'Could not start the upload'));
  }
  const session: SessionSummary = await created.json();

  onProgress?.(progressFor(0, file.size));

  for (const { start, end } of chunkRanges(file.size, chunkBytes)) {
    await sendChunk(file, session.id, start, end, { signal, fetchImpl });
    onProgress?.(progressFor(end, file.size));
  }

  const completed = await fetchImpl(
    `/api/produce/sessions/${session.id}/complete`,
    { method: 'POST', signal }
  );
  if (!completed.ok) {
    throw new Error(await readError(completed, 'Could not start the scan'));
  }
  return completed.json();
}

async function sendChunk(
  file: File,
  sessionId: number,
  start: number,
  end: number,
  { signal, fetchImpl }: { signal?: AbortSignal; fetchImpl: typeof fetch }
): Promise<void> {
  let lastError: unknown = null;

  for (let attempt = 0; attempt < CHUNK_RETRIES; attempt++) {
    if (signal?.aborted) {
      throw new DOMException('Upload cancelled', 'AbortError');
    }

    let response: Response;
    try {
      // `offset` is where these bytes belong, so a retry rewrites the same
      // range rather than appending a duplicate.
      response = await fetchImpl(
        `/api/produce/sessions/${sessionId}/chunk?offset=${start}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/octet-stream' },
          body: file.slice(start, end),
          signal,
        }
      );
    } catch (error) {
      // Only a transport failure lands here, and that is worth another try.
      if ((error as DOMException)?.name === 'AbortError') throw error;
      lastError = error;
      continue;
    }

    if (response.ok) return;

    const failure = new Error(await readError(response, 'Upload failed'));
    // A refusal of the session itself — wrong state, gone, not permitted — will
    // not improve on a retry. Raised here rather than inside the try above, so
    // this function's own error cannot be mistaken for a transport failure.
    if (response.status < 500) throw failure;
    lastError = failure;
  }

  throw lastError instanceof Error
    ? lastError
    : new Error('Upload failed after several attempts');
}
