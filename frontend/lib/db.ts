import { Pool, PoolClient } from 'pg';

let pool: Pool | null = null;

export function getPool(): Pool {
  if (!pool) {
    pool = new Pool({
      host: process.env.DB_HOST,
      port: parseInt(process.env.DB_PORT || '5432'),
      database: process.env.DB_NAME,
      user: process.env.DB_USER,
      password: process.env.DB_PASSWORD,
      max: 20,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 2000,
    });

    pool.on('error', (err) => {
      console.error('Unexpected error on idle client', err);
    });
  }

  return pool;
}

export async function query<T = any>(text: string, params?: any[]): Promise<T[]> {
  const pool = getPool();
  const result = await pool.query(text, params);
  return result.rows;
}

export async function getClient(): Promise<PoolClient> {
  const pool = getPool();
  return await pool.connect();
}

export interface Song {
  id: number;
  title: string;
  genre: string;
  tempo_bpm: number;
  key: string;
  duration_seconds: number;
  energy: string;
  mood: string;
  recording_date: Date;
  audio_quality: string;
  audio_url: string;
  rating: number;
  session: string;
  uploaded_on: Date;
  recorded_on: Date;
  is_original: boolean;
  track_number: number;
}

export interface SearchResult {
  song: Song;
  similarity?: number;
  score?: number;
}

export async function saveUser(user: {
  id: string;
  email: string;
  name: string;
  picture?: string;
}) {
  const result = await query(
    `INSERT INTO users (id, email, name, picture, role)
     VALUES ($1, $2, $3, $4, 'listener')
     ON CONFLICT (id) DO UPDATE
     SET email = $2, name = $3, picture = $4, updated_at = CURRENT_TIMESTAMP
     RETURNING *`,
    [user.id, user.email, user.name, user.picture]
  );
  return result[0];
}

export async function getUser(userId: string) {
  const result = await query(
    'SELECT * FROM users WHERE id = $1',
    [userId]
  );
  return result[0] || null;
}
