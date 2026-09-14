// Running a batch of requests a few at a time.
//
// The produce API's audio work is CPU-bound on the server, so firing every job
// at once doesn't finish the batch sooner — it just makes each individual
// request take as long as all of them together, which is how a render ends up
// past the reverse proxy's read timeout.

/**
 * Map over `items` with at most `limit` calls in flight, returning results in
 * input order.
 */
export async function mapWithConcurrency<T, R>(
  items: T[],
  limit: number,
  fn: (item: T) => Promise<R>
): Promise<R[]> {
  const results = new Array<R>(items.length);
  let cursor = 0;
  const worker = async () => {
    while (cursor < items.length) {
      const index = cursor++;
      results[index] = await fn(items[index]);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}
