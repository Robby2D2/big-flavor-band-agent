import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Set a take aside, or bring it back. Detection is fallible — a stretch of
// talking can read as a song — so discarding is a flag, never a delete.
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ takeId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { takeId } = await params;
    const body = await request.json();

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/takes/${takeId}`,
      {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
        body: JSON.stringify(body),
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Could not update the take' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Session take update error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
