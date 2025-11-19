import { NextResponse } from 'next/server';

/**
 * Health check endpoint for Docker container monitoring
 */
export async function GET() {
  return NextResponse.json(
    {
      status: 'healthy',
      timestamp: new Date().toISOString(),
      service: 'bigflavor-frontend'
    },
    { status: 200 }
  );
}
