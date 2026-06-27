import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { songId } = await params;

    const response = await fetch(`${AGENT_API_URL}/api/produce/songs/${songId}`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('editor'),
      },
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to load song' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Produce song error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
