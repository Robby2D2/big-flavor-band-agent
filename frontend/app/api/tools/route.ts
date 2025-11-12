import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';

export async function GET(request: NextRequest) {
  try {
    // Require editor role
    await requireAuth(UserRole.EDITOR);

    // Call Python backend API
    const response = await fetch(`${process.env.AGENT_API_URL}/api/tools/list`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
      },
    });

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Tools list error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    // Require editor role
    await requireAuth(UserRole.EDITOR);

    const body = await request.json();
    const { tool_name, parameters } = body;

    if (!tool_name) {
      return NextResponse.json(
        { error: 'tool_name is required' },
        { status: 400 }
      );
    }

    // Call Python backend API
    const response = await fetch(
      `${process.env.AGENT_API_URL}/api/tools/execute?tool_name=${encodeURIComponent(tool_name)}`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(parameters || {}),
      }
    );

    if (!response.ok) {
      throw new Error(`Backend API error: ${response.statusText}`);
    }

    const data = await response.json();
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('Tool execution error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
