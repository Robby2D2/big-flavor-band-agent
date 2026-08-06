import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/server-auth';
import { backendAuthHeaders } from '@/lib/backend';

const AGENT_API_URL = process.env.AGENT_API_URL || 'http://localhost:8000';

// The waveform drawing envelope for one stem — a few KB of min/max pairs that
// replace downloading and decoding the stem's whole (uncompressed, ~44MB) audio
// just to paint a waveform.
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ stemId: string }> }
) {
  try {
    await requireAuth(UserRole.EDITOR);
    const { stemId } = await params;

    const response = await fetch(
      `${AGENT_API_URL}/api/produce/stems/${stemId}/peaks`,
      {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          ...backendAuthHeaders('editor'),
        },
      }
    );

    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      return NextResponse.json(
        { error: data.error?.message || 'Failed to load waveform' },
        { status: response.status }
      );
    }

    return NextResponse.json(data, {
      // A stem id's audio never changes — a re-separation creates new stem
      // rows — so the envelope for one is safe to cache indefinitely.
      headers: { 'Cache-Control': 'private, max-age=31536000, immutable' },
    });
  } catch (error: any) {
    console.error('Stem peaks error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: error.message?.includes('Forbidden') ? 403 : 500 }
    );
  }
}
