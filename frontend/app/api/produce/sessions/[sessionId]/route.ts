import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// One session with its channels and the takes found in it. Polled while a scan
// runs, which is why the response must never be cached.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { sessionId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/${sessionId}`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
        cache: 'no-store',
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to load the session' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Session load error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}

// Delete a session and everything unpacked or rendered for it.
export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { sessionId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/${sessionId}`,
      {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to delete the session' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Session delete error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
