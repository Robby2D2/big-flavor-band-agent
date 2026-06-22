import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

export async function POST(request: NextRequest) {
  try {
    await requireAuth(UserRole.EDITOR);
    const body = await request.json();

    const response = await fetch(`${AGENT_API_URL}/api/produce/approve`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('editor'),
      },
      body: JSON.stringify(body),
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    console.error('Produce approve error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
