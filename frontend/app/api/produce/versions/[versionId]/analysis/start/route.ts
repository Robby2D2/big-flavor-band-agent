import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Start analysis: separates if needed and measures, whether or not the page stays open.
// `?then_save=true` is Analyze & save: the fixes it finds are saved as a new version too.
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ versionId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { versionId } = await params;
    const thenSave = request.nextUrl.searchParams.get('then_save') === 'true';

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/versions/${encodeURIComponent(versionId)}/analysis/start` +
        (thenSave ? '?then_save=true' : ''),
      { method: 'POST', headers: backendAuthHeaders('editor') }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: backendErrorMessage(data) || 'Could not start the analysis' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Analysis start error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
