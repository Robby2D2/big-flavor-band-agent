import { NextRequest, NextResponse } from 'next/server';
import { requireCaller, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

export async function POST(request: NextRequest) {
  try {
    // Any signed-in user may start a paused radio — it is what tuning in needs
    // (RAD-03). Stopping it stays editor+ (ACCT-15), which the pause route enforces.
    // The caller's real role is forwarded rather than a constant 'editor', so the
    // backend authorizes the person actually asking.
    const { user, role } = await requireCaller(UserRole.LISTENER);

    const response = await fetch(`${process.env.AGENT_API_URL}/api/radio/play`, {
      method: 'POST',
      headers: backendAuthHeaders(role, user.sub),
    });

    // Forward the backend's status and wording: a transport action that failed has to
    // be able to say why on the page (RAD-09).
    if (!response.ok) {
      const errorBody = await response.json().catch(() => null);
      return NextResponse.json(
        { error: backendErrorMessage(errorBody) || `Backend API error: ${response.statusText}` },
        { status: response.status }
      );
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Play radio error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
