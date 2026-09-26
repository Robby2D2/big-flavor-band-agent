import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Finish a chunked upload and start the scan.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ sessionId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { sessionId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/${sessionId}/complete`,
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
        { error: data.detail || 'Could not start the scan' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Session complete error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
