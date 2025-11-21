import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    // Require authentication
    await requireAuth(UserRole.LISTENER);

    const { songId } = await params;

    // Proxy the request to the backend API
    const backendUrl = `${AGENT_API_URL}/api/audio/stream/${songId}`;

    // Forward range headers for streaming support
    const headers: HeadersInit = {};
    const range = request.headers.get('range');
    if (range) {
      headers['Range'] = range;
    }

    const response = await fetch(backendUrl, {
      method: 'GET',
      headers,
    });

    if (!response.ok) {
      const errorText = await response.text();
      return NextResponse.json(
        { error: errorText || 'Audio file not found' },
        { status: response.status }
      );
    }

    // Stream the response back to the client
    const responseHeaders = new Headers();

    // Copy relevant headers from backend response
    const contentType = response.headers.get('content-type');
    if (contentType) responseHeaders.set('Content-Type', contentType);

    const contentLength = response.headers.get('content-length');
    if (contentLength) responseHeaders.set('Content-Length', contentLength);

    const contentRange = response.headers.get('content-range');
    if (contentRange) responseHeaders.set('Content-Range', contentRange);

    const acceptRanges = response.headers.get('accept-ranges');
    if (acceptRanges) responseHeaders.set('Accept-Ranges', acceptRanges);

    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error: any) {
    console.error('Audio streaming error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: 500 }
    );
  }
}
