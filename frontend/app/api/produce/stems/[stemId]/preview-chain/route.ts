import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Render one stem through its currently-enabled fix chain, for audition —
// non-destructive, no version, no DB write.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ stemId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { stemId } = await params;
    const body = await request.json().catch(() => ({}));

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/stems/${encodeURIComponent(stemId)}/preview-chain`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
        body: JSON.stringify({ fixes: body?.fixes ?? [] }),
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Preview chain failed' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Stem preview-chain error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
