import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Region editor "Preview": run one production tool over the selected region and
// return a produced file to audition A/B. Creates NO version (issue #70).
export async function POST(request: NextRequest) {
  try {
    await requireAuth(UserRole.EDITOR);

    const body = await request.json();
    if (body?.song_id == null || !body?.tool) {
      return NextResponse.json(
        { error: 'song_id and tool are required' },
        { status: 400 }
      );
    }

    const response = await fetch(`${AGENT_API_URL}/api/produce/region/preview`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('editor'),
      },
      body: JSON.stringify({
        song_id: body.song_id,
        source_version_id: body.source_version_id ?? null,
        tool: body.tool,
        start_s: body.start_s ?? null,
        end_s: body.end_s ?? null,
        strength: body.strength ?? 1.0,
        params: body.params ?? {},
      }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Preview failed' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Region preview error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
