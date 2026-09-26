import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

export async function POST(request: NextRequest) {
  try {
    // Require editor role
    await requireAuth(UserRole.EDITOR);

    const response = await fetch(`${process.env.AGENT_API_URL}/api/radio/skip`, {
      method: 'POST',
      headers: backendAuthHeaders('editor'),
    });

    // A skip now moves the audio on the stream, so it can fail for a real reason
    // (the stream is unreachable → 503). Forward the status and the backend's own
    // wording instead of flattening it to a generic 500, so the page can tell the
    // user what actually happened (RAD-09).
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      return NextResponse.json(
        { error: body?.detail || `Backend API error: ${response.statusText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Skip song error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
