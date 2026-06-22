import { NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

export async function GET() {
  try {
    await requireAuth(UserRole.EDITOR);

    const response = await fetch(`${AGENT_API_URL}/api/produce/batch/status`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('editor'),
      },
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    console.error('Produce batch status error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
