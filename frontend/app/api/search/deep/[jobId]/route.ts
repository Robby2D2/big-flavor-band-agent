import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// An in-depth search's steps so far, and its answer once it has one.
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ jobId: string }> }
) {
  try {
    await requireAuth(UserRole.LISTENER);

    const { jobId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/search/deep/${encodeURIComponent(jobId)}`,
      { headers: backendAuthHeaders('listener') }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Could not read that search' },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Deep search status error:', error);
    if (error.message?.startsWith('Unauthorized')) {
      return NextResponse.json({ error: 'Please log in to search.' }, { status: 401 });
    }
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.startsWith('Forbidden') ? 403 : 500 }
    );
  }
}
