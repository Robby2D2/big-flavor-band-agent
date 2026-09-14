import { describe, expect, it } from 'vitest';
import { readJson } from '@/lib/apiJson';

/** Minimal stand-in for a fetch Response — readJson only reads the body + status. */
function response(body: string, status = 200, statusText = ''): Response {
  return { status, statusText, text: async () => body } as Response;
}

/** What a reverse proxy hands back when it stops waiting for a long render. */
const NGINX_504 = '<html>\r\n<head><title>504 Gateway Time-out</title></head>\r\n</html>';

describe('readJson', () => {
  it('parses an app response', async () => {
    await expect(readJson(response('{"candidate_path": "a.wav"}'))).resolves.toEqual({
      candidate_path: 'a.wav',
    });
  });

  it('treats an empty body as an empty object', async () => {
    await expect(readJson(response('', 204))).resolves.toEqual({});
  });

  it('reports a proxy timeout instead of a JSON parse error', async () => {
    await expect(readJson(response(NGINX_504, 504, 'Gateway Time-out'))).rejects.toThrow(
      /still rendering when the proxy gave up \(504\)/
    );
  });

  it('names the status when some other non-JSON body comes back', async () => {
    await expect(readJson(response('<html> </html>', 413, 'Payload Too Large'))).rejects.toThrow(
      'The server returned 413 Payload Too Large instead of a result.'
    );
  });
});
