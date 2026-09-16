import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Start an in-depth search. Several model calls and retrievals, so the backend
// answers with a job id straight away and the page follows its steps.
export async function POST(request: NextRequest) {
  try {
    await requireAuth(UserRole.LISTENER);

    const { query } = await request.json().catch(() => ({}));
    if (!query || !String(query).trim()) {
      return NextResponse.json({ error: 'A question is required' }, { status: 400 });
    }

    const response = await fetch(`${AGENT_API_URL}/api/search/deep/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...backendAuthHeaders('listener') },
      body: JSON.stringify({ query }),
    });

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Could not start the search' },
        { status: response.status }
      );
    }
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Deep search start error:', error);
    if (error.message?.startsWith('Unauthorized')) {
      return NextResponse.json({ error: 'Please log in to search.' }, { status: 401 });
    }
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.startsWith('Forbidden') ? 403 : 500 }
    );
  }
}
