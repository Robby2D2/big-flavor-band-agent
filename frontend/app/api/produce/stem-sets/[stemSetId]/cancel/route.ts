import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Cancel a separation. The page is freed at once; Demucs cannot be stopped
// mid-pass, so the server discards its output when that pass ends.
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ stemSetId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { stemSetId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/stem-sets/${encodeURIComponent(stemSetId)}/cancel`,
      { method: 'POST', headers: backendAuthHeaders('editor') }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: backendErrorMessage(data) || 'Could not cancel the separation' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Stem separation cancel error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
