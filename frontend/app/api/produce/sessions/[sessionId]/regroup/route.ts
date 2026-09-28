import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Guess the session's song groups again from what was transcribed. It reads no
// audio, so a session scanned before grouping existed can be grouped without
// re-uploading it — and it discards the names and keepers already set, which is
// why only an explicit request triggers it.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { sessionId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/${sessionId}/regroup`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: backendErrorMessage(data) || 'Could not group the takes' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Session regroup error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
