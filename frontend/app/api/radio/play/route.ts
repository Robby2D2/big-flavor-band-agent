import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders, backendErrorMessage } from '@/lib/backend';

export async function POST(request: NextRequest) {
  try {
    // Require editor role
    await requireAuth(UserRole.EDITOR);

    const response = await fetch(`${process.env.AGENT_API_URL}/api/radio/play`, {
      method: 'POST',
      headers: backendAuthHeaders('editor'),
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
