import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// A producer's corrections to a guessed group: its name, and which of its takes
// is the keeper. Grouping is a guess, so overruling it has to be one request.
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ groupId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { groupId } = await params;
    const body = await request.json();

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/groups/${groupId}`,
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
        { error: backendErrorMessage(data) || 'Could not update the group' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Session group update error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
