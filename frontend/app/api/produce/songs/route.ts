import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

export async function GET() {
  try {
    await requireAuth(UserRole.EDITOR);

    const response = await fetch(`${AGENT_API_URL}/api/produce/songs`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('editor'),
      },
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    return NextResponse.json(await response.json());
  } catch (error: any) {
    console.error('Produce songs error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
