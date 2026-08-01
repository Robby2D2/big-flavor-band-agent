import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Run one tool's analyze pass — findings + recommended params, no processing.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ tool: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { tool } = await params;
    const body = await request.json();
    if (body?.song_id == null) {
      return NextResponse.json({ error: 'song_id is required' }, { status: 400 });
    }

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/tools/${encodeURIComponent(tool)}/analyze`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
        body: JSON.stringify({
          song_id: body.song_id,
          source_version_id: body.source_version_id ?? null,
          stem_id: body.stem_id ?? null,
          start_s: body.start_s ?? null,
          end_s: body.end_s ?? null,
          params: body.params ?? {},
        }),
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Analyze failed' },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Tool analyze error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
