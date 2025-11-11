import { NextRequest, NextResponse } from 'next/server';
import { requireAuth, UserRole } from '@/lib/auth';
import fs from 'fs';
import path from 'path';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ songId: string }> }
) {
  try {
    // Require authentication
    await requireAuth(UserRole.LISTENER);

    const { songId } = await params;

    // Path to audio library
    const audioLibraryPath = path.join(process.cwd(), '..', 'audio_library');

    // Find the audio file matching the song ID
    const files = fs.readdirSync(audioLibraryPath);
    const audioFile = files.find(file => file.startsWith(`${songId}_`) && file.endsWith('.mp3'));

    if (!audioFile) {
      return NextResponse.json(
        { error: 'Audio file not found' },
        { status: 404 }
      );
    }

    const filePath = path.join(audioLibraryPath, audioFile);
    const stat = fs.statSync(filePath);
    const fileSize = stat.size;

    // Handle range requests for audio streaming
    const range = request.headers.get('range');

    if (range) {
      const parts = range.replace(/bytes=/, '').split('-');
      const start = parseInt(parts[0], 10);
      const end = parts[1] ? parseInt(parts[1], 10) : fileSize - 1;
      const chunksize = end - start + 1;
      const stream = fs.createReadStream(filePath, { start, end });

      return new NextResponse(stream as any, {
        status: 206,
        headers: {
          'Content-Range': `bytes ${start}-${end}/${fileSize}`,
          'Accept-Ranges': 'bytes',
          'Content-Length': chunksize.toString(),
          'Content-Type': 'audio/mpeg',
        },
      });
    } else {
      const stream = fs.createReadStream(filePath);

      return new NextResponse(stream as any, {
        status: 200,
        headers: {
          'Content-Length': fileSize.toString(),
          'Content-Type': 'audio/mpeg',
        },
      });
    }
  } catch (error: any) {
    console.error('Audio streaming error:', error);
    return NextResponse.json(
      { error: error.message || 'Internal server error' },
      { status: 500 }
    );
  }
}
