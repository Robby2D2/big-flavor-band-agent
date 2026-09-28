import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Stop the song's running render at its next step, or (?save_only=true) only
// the save waiting on it. Refused once the version is being written.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { songId } = await params;
    const saveOnly = request.nextUrl.searchParams.get('save_only') === 'true';

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/songs/${encodeURIComponent(songId)}/accept-fixes/cancel?save_only=${saveOnly}`,
      { method: 'POST', headers: backendAuthHeaders('editor') }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: backendErrorMessage(data) || 'Could not cancel the render' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Accept-fixes cancel error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
