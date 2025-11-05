/**
 * Song Library Manager
 * Handles storage and retrieval of Big Flavor's song collection
 */

export interface Song {
  id: string;
  title: string;
  artist: string;
  genre: string;
  duration: number; // in seconds
  bpm?: number;
  key?: string;
  mood: string[];
  tags: string[];
  audioUrl?: string;
  releaseDate?: string;
  lyrics?: string;
  metadata?: {
    recordedDate?: string;
    location?: string;
    equipment?: string[];
  };
}

export interface AlbumSuggestion {
  title: string;
  theme: string;
  songs: Song[];
  totalDuration: number;
  reasoning: string;
}

export class SongLibrary {
  private songs: Song[] = [];

  constructor() {
    // Initialize with sample data (in production, this would load from database)
    this.initializeSampleData();
  }

  private initializeSampleData() {
    // Sample songs for Big Flavor Band
    this.songs = [
      {
        id: '1',
        title: 'Weekend Warriors',
        artist: 'Big Flavor',
        genre: 'Rock',
        duration: 245,
        bpm: 120,
        key: 'E',
        mood: ['upbeat', 'energetic'],
        tags: ['dad-rock', 'garage-band', 'weekend'],
        releaseDate: '2024-06-15',
      },
      {
        id: '2',
        title: 'Suburban Dreams',
        artist: 'Big Flavor',
        genre: 'Alternative',
        duration: 198,
        bpm: 95,
        key: 'G',
        mood: ['mellow', 'nostalgic'],
        tags: ['acoustic', 'storytelling'],
        releaseDate: '2024-07-22',
      },
      {
        id: '3',
        title: 'Garage Jam Session',
        artist: 'Big Flavor',
        genre: 'Blues Rock',
        duration: 312,
        bpm: 110,
        key: 'A',
        mood: ['groovy', 'relaxed'],
        tags: ['jam', 'instrumental', 'blues'],
        releaseDate: '2024-08-10',
      },
      {
        id: '4',
        title: 'Dad Jokes in D Minor',
        artist: 'Big Flavor',
        genre: 'Comedy Rock',
        duration: 167,
        bpm: 135,
        key: 'D',
        mood: ['funny', 'upbeat'],
        tags: ['comedy', 'parody', 'dad-humor'],
        releaseDate: '2024-09-05',
      },
      {
        id: '5',
        title: 'Midnight Riffs',
        artist: 'Big Flavor',
        genre: 'Rock',
        duration: 278,
        bpm: 128,
        key: 'C',
        mood: ['energetic', 'raw'],
        tags: ['electric', 'heavy', 'loud'],
        releaseDate: '2024-10-01',
      },
    ];
  }

  async getAllSongs(): Promise<Song[]> {
    return this.songs;
  }

  async getSongs(genre?: string, limit?: number): Promise<Song[]> {
    let filtered = this.songs;

    if (genre) {
      filtered = filtered.filter(
        (song) => song.genre.toLowerCase() === genre.toLowerCase()
      );
    }

    if (limit && limit > 0) {
      filtered = filtered.slice(0, limit);
    }

    return filtered;
  }

  async getSongDetails(songId: string): Promise<Song | null> {
    return this.songs.find((song) => song.id === songId) || null;
  }

  async recommendSongs(
    seedSongId?: string,
    mood?: string,
    count: number = 5
  ): Promise<Song[]> {
    let recommendations: Song[] = [];

    if (seedSongId) {
      const seedSong = await this.getSongDetails(seedSongId);
      if (seedSong) {
        // Find similar songs based on genre, mood, or BPM
        recommendations = this.songs.filter((song) => {
          if (song.id === seedSongId) return false;

          const genreMatch = song.genre === seedSong.genre;
          const moodMatch = song.mood.some((m) => seedSong.mood.includes(m));
          const bpmSimilar =
            song.bpm &&
            seedSong.bpm &&
            Math.abs(song.bpm - seedSong.bpm) < 20;

          return genreMatch || moodMatch || bpmSimilar;
        });
      }
    }

    if (mood) {
      recommendations = this.songs.filter((song) =>
        song.mood.some((m) => m.toLowerCase().includes(mood.toLowerCase()))
      );
    }

    // If no specific criteria, return random songs
    if (recommendations.length === 0) {
      recommendations = [...this.songs].sort(() => Math.random() - 0.5);
    }

    return recommendations.slice(0, count);
  }

  async createAlbum(
    theme?: string,
    songCount: number = 10
  ): Promise<AlbumSuggestion> {
    let selectedSongs: Song[] = [];
    let albumTitle = 'Big Flavor Collection';
    let reasoning = 'A diverse collection showcasing the band\'s range.';

    if (theme) {
      // Try to match songs to the theme
      const themeWords = theme.toLowerCase().split(' ');
      selectedSongs = this.songs.filter((song) => {
        const songText = `${song.title} ${song.genre} ${song.mood.join(' ')} ${song.tags.join(' ')}`.toLowerCase();
        return themeWords.some((word) => songText.includes(word));
      });

      albumTitle = `Big Flavor: ${theme}`;
      reasoning = `Songs selected to match the theme "${theme}".`;
    }

    // If not enough songs match the theme, add more
    if (selectedSongs.length < songCount) {
      const remaining = this.songs.filter(
        (song) => !selectedSongs.find((s) => s.id === song.id)
      );
      selectedSongs = [
        ...selectedSongs,
        ...remaining.slice(0, songCount - selectedSongs.length),
      ];
    } else {
      selectedSongs = selectedSongs.slice(0, songCount);
    }

    // Sort by mood flow (upbeat -> mellow -> energetic)
    selectedSongs.sort((a, b) => {
      const moodOrder = ['upbeat', 'energetic', 'groovy', 'mellow', 'relaxed'];
      const aIndex = Math.min(
        ...a.mood.map((m) => moodOrder.indexOf(m)).filter((i) => i !== -1)
      );
      const bIndex = Math.min(
        ...b.mood.map((m) => moodOrder.indexOf(m)).filter((i) => i !== -1)
      );
      return aIndex - bIndex;
    });

    const totalDuration = selectedSongs.reduce(
      (sum, song) => sum + song.duration,
      0
    );

    return {
      title: albumTitle,
      theme: theme || 'Various',
      songs: selectedSongs,
      totalDuration,
      reasoning,
    };
  }

  async getStatistics() {
    const totalSongs = this.songs.length;
    const totalDuration = this.songs.reduce(
      (sum, song) => sum + song.duration,
      0
    );
    const genres = [...new Set(this.songs.map((song) => song.genre))];
    const avgDuration = totalDuration / totalSongs;

    return {
      totalSongs,
      totalDuration,
      totalDurationFormatted: `${Math.floor(totalDuration / 60)} minutes`,
      genres,
      avgDuration: Math.round(avgDuration),
      mostCommonGenre:
        genres.reduce((prev, curr) => {
          const prevCount = this.songs.filter(
            (s) => s.genre === prev
          ).length;
          const currCount = this.songs.filter(
            (s) => s.genre === curr
          ).length;
          return currCount > prevCount ? curr : prev;
        }, genres[0]),
    };
  }
}
