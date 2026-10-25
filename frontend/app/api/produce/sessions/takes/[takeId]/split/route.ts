import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Cut a take in two where the band ran one song into the next (SESS-22).
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ takeId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { takeId } = await params;
    const body = await request.json();

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/takes/${takeId}/split`,
      {
        method: 'POST',
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
        { error: backendErrorMessage(data) || 'Could not split the take' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: unknown) {
    const message = error instanceof Error ? error.message : 'Internal server error';
    console.error('Session take split error:', error);
    return NextResponse.json(
      { error: message },
      { status: message.includes('Forbidden') ? 403 : 500 }
    );
  }
}
