import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

export async function GET() {
  try {
    await requireAuth(UserRole.ADMIN);

    const response = await fetch(`${process.env.AGENT_API_URL}/api/admin/invites`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('admin'),
      },
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    return NextResponse.json(await response.json());
  } catch (error: any) {
    console.error('Invite list error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const admin = await requireAuth(UserRole.ADMIN);

    const { email, role } = await request.json();

    if (!email) {
      return NextResponse.json({ error: 'email is required' }, { status: 400 });
    }

    const response = await fetch(`${process.env.AGENT_API_URL}/api/admin/invites`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...backendAuthHeaders('admin'),
      },
      // created_by comes from the verified session, not from the browser.
      body: JSON.stringify({ email, role: role || 'editor', created_by: admin.sub }),
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to create invite' },
        { status: response.status }
      );
    }

    // Turn the one-time token into the link the admin actually sends. Built
    // from the request origin so it is correct in dev and behind nginx alike.
    const protocol = request.headers.get('x-forwarded-proto') || 'http';
    const host = request.headers.get('host') || 'localhost:3000';
    const { token, ...invite } = data;

    return NextResponse.json({
      ...invite,
      invite_url: `${protocol}://${host}/invite/${encodeURIComponent(token)}`,
    });
  } catch (error: any) {
    console.error('Invite create error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
