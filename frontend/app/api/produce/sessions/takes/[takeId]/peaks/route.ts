import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// The drawing envelope for one take's mix — a few KB of quantised min/max pairs, so the
// page can draw a waveform without downloading minutes of 24-bit audio.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ takeId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { takeId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/sessions/takes/${takeId}/peaks`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Waveform not available' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Session takes peaks error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
