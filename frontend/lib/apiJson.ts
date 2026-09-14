// Reading JSON from the produce API when something between the browser and the
// app answers instead of the app.
//
// Every route handler under app/api/ answers in JSON — successes and errors
// alike — so a body that doesn't parse didn't come from the app at all. It came
// from the reverse proxy in front of it: a long render (a fix chain over six
// stems, or an accept-fixes pass over the whole song) can outlive the proxy's
// read timeout, and the browser is handed the proxy's own HTML error page.
// `res.json()` then throws "Unexpected token '<', "<html> <h"... is not valid
// JSON", which tells a producer nothing about what actually went wrong.

/** How a proxy timeout reads once it has been turned into a sentence. */
function gatewayMessage(res: Response): string {
  if (res.status === 502 || res.status === 503 || res.status === 504) {
    return `The server was still rendering when the proxy gave up (${res.status}). ` +
      'Long renders can outlast its timeout — try again with fewer fixes turned on.';
  }
  return `The server returned ${res.status}${res.statusText ? ` ${res.statusText}` : ''} ` +
    'instead of a result.';
}

/**
 * Parse a response body as JSON, reporting a non-JSON body as the gateway
 * failure it is. An empty body parses as `{}` so callers can read `.detail`
 * off it without a guard.
 */
export async function readJson(res: Response): Promise<any> {
  const text = await res.text();
  try {
    return text ? JSON.parse(text) : {};
  } catch {
    throw new Error(gatewayMessage(res));
  }
}
