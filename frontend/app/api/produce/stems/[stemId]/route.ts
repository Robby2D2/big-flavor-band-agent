import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Relabel a stem — Demucs can only call a banjo "other", so a producer names it.
export async function PATCH(
  request: NextRequest,
  { params }: { params: Promise<{ stemId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { stemId } = await params;
    const body = await request.json();

    const response = await fetch(`${AGENT_API_URL}/api/produce/stems/${stemId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', ...backendAuthHeaders('editor') },
      body: JSON.stringify(body),
    });

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    console.error('Stem rename error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
