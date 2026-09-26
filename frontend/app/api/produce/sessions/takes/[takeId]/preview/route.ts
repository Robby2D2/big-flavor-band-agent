import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// A compressed copy of one take's mix, for browser playback only. The 24-bit source is
// what the audio tools read; the browser never needs it to press play.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ takeId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { takeId } = await params;

    const headers: HeadersInit = { ...backendAuthHeaders('editor') };
    const range = request.headers.get('range');
    if (range) {
      headers['Range'] = range;
    }

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/takes/${takeId}/preview`,
      { method: 'GET', headers }
    );

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: errorText || 'Audio not found' },
        { status: response.status }
      );
    }

    const responseHeaders = new Headers();
    for (const header of [
      'content-type',
      'content-length',
      'content-range',
      'accept-ranges',
    ]) {
      const value = response.headers.get(header);
      if (value) responseHeaders.set(header, value);
    }
    // A take's audio never changes once rendered, so its preview is safe to
    // cache indefinitely — same reasoning as the stem preview route.
    responseHeaders.set('Cache-Control', 'private, max-age=31536000, immutable');

    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error: any) {
    console.error('Session takes preview error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
