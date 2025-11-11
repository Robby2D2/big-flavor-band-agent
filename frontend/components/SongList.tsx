'use client';

interface Song {
  id: number;
  title: string;
  genre?: string;
  tempo_bpm?: number;
  key?: string;
  duration_seconds?: number;
  mood?: string;
  energy?: string;
  recording_date?: string;
  similarity?: number;
  score?: number;
}

interface SongListProps {
  songs: Song[];
  onPlay: (song: Song) => void;
}

export default function SongList({ songs, onPlay }: SongListProps) {
  const formatDuration = (seconds?: number) => {
    if (!seconds) return 'Unknown';
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}:${secs.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-3">
      {songs.map((song) => (
        <div
          key={song.id}
          className="bg-white dark:bg-gray-800 p-4 rounded-lg shadow hover:shadow-lg transition-shadow"
        >
          <div className="flex items-start justify-between">
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                {song.title}
              </h3>
              <div className="mt-2 flex flex-wrap gap-2 text-sm text-gray-600 dark:text-gray-400">
                {song.genre && (
                  <span className="px-2 py-1 bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-200 rounded">
                    {song.genre}
                  </span>
                )}
                {song.mood && (
                  <span className="px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-700 dark:text-blue-200 rounded">
                    {song.mood}
                  </span>
                )}
                {song.energy && (
                  <span className="px-2 py-1 bg-orange-100 dark:bg-orange-900 text-orange-700 dark:text-orange-200 rounded">
                    {song.energy}
                  </span>
                )}
              </div>
              <div className="mt-2 text-sm text-gray-600 dark:text-gray-400">
                {song.tempo_bpm && <span>Tempo: {song.tempo_bpm} BPM</span>}
                {song.key && <span className="ml-4">Key: {song.key}</span>}
                {song.duration_seconds && (
                  <span className="ml-4">Duration: {formatDuration(song.duration_seconds)}</span>
                )}
              </div>
              {(song.similarity || song.score) && (
                <div className="mt-2 text-xs text-gray-500 dark:text-gray-500">
                  Match: {((song.similarity || song.score || 0) * 100).toFixed(1)}%
                </div>
              )}
            </div>
            <button
              onClick={() => onPlay(song)}
              className="ml-4 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 flex items-center gap-2"
            >
              <svg
                className="w-5 h-5"
                fill="currentColor"
                viewBox="0 0 20 20"
              >
                <path d="M6.3 2.841A1.5 1.5 0 004 4.11V15.89a1.5 1.5 0 002.3 1.269l9.344-5.89a1.5 1.5 0 000-2.538L6.3 2.84z" />
              </svg>
              Play
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
