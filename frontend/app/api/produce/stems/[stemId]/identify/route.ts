import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// Detect which instruments are audible in one stem. Model inference, so this is
// slow enough that the client fans it out per stem rather than blocking on a set.
export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ stemId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { stemId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/stems/${stemId}/identify`,
      { method: 'POST', headers: backendAuthHeaders('editor') }
    );

    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error: any) {
    console.error('Stem instrument identification error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
