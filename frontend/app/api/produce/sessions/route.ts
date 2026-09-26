import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Every uploaded recording session, newest first.
export async function GET() {
  try {
    await requireAuth(UserRole.EDITOR);

    const response = await fetch(`${AGENT_API_URL}/api/produce/sessions`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('editor'),
      },
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to load sessions' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Sessions list error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}

// Open a session, which is where the chunked upload then sends its pieces.
export async function POST(request: NextRequest) {
  try {
    await requireAuth(UserRole.EDITOR);
    const body = await request.json();

    const response = await fetch(`${AGENT_API_URL}/api/produce/sessions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('editor'),
      },
      body: JSON.stringify(body),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to start an upload' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Session create error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
