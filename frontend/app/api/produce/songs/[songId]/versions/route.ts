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

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/songs/${songId}/versions`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
      }
    );

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    return NextResponse.json(await response.json());
  } catch (error: any) {
    console.error('Produce versions error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
