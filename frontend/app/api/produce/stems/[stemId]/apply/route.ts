import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Stem mixer "Save mix as new version": remix a completed stem set (per-stem
// gain/mute) into a new unpublished candidate version, entering the existing
// audition/approve/publish flow (issue #70). The route param is the stem SET id.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ stemId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { stemId: setId } = await params;

    const body = await request.json().catch(() => ({}));

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/stems/${setId}/apply`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
        body: JSON.stringify({ adjustments: body?.adjustments ?? {} }),
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to save stem mix' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Stem apply error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
