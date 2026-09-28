import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Pull a take out of the group it was guessed into. The take is untouched
// otherwise — it keeps its audio, its channels and its discard state.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ takeId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { takeId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/takes/${takeId}/separate`,
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
        { error: backendErrorMessage(data) || 'Could not separate the take' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Session take separate error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
