import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// A compressed (Opus) copy of one stem, for browser playback only — roughly 15x
// smaller than the uncompressed Demucs WAV the console used to download for
// every stem. `/audio` still serves the real file for the A/B fidelity check.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ stemId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { stemId } = await params;

    const headers: HeadersInit = { ...backendAuthHeaders('editor') };
    const range = request.headers.get('range');
    if (range) {
      headers['Range'] = range;
    }

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/stems/${stemId}/preview`,
      { method: 'GET', headers }
    );

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: errorText || 'Stem preview not found' },
        { status: response.status }
      );
    }

    const responseHeaders = new Headers();
    const contentType = response.headers.get('content-type');
    if (contentType) responseHeaders.set('Content-Type', contentType);
    const contentLength = response.headers.get('content-length');
    if (contentLength) responseHeaders.set('Content-Length', contentLength);
    const contentRange = response.headers.get('content-range');
    if (contentRange) responseHeaders.set('Content-Range', contentRange);
    const acceptRanges = response.headers.get('accept-ranges');
    if (acceptRanges) responseHeaders.set('Accept-Ranges', acceptRanges);
    // Same reasoning as the stem audio route: a stem id's audio never changes,
    // so its preview is safe to cache indefinitely.
    responseHeaders.set('Cache-Control', 'private, max-age=31536000, immutable');

    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error: any) {
    console.error('Stem preview streaming error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
