import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';

export async function POST(request: NextRequest) {
  try {
    // Require editor role
    await requireAuth(UserRole.EDITOR);

    const response = await fetch(`${process.env.AGENT_API_URL}/api/radio/skip`, {
      method: 'POST',
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Skip song error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
