import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

export async function DELETE(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    await requireAuth(UserRole.ADMIN);

    const { id } = await params;

    const response = await fetch(
      `${process.env.AGENT_API_URL}/api/admin/invites/${encodeURIComponent(id)}`,
      {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('admin'),
        },
      }
    );

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail || 'Failed to revoke invite' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Invite revoke error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
