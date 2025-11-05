import * as readline from 'readline';
import { BigFlavorAgent } from './agent/index.js';
import { SongLibrary } from './mcp-server/song-library.js';

/**
 * Interactive CLI for the Big Flavor AI Agent
 */
class InteractiveCLI {
  private agent: BigFlavorAgent;
  private songLibrary: SongLibrary;
  private rl: readline.Interface;

  constructor() {
    this.agent = new BigFlavorAgent();
    this.songLibrary = new SongLibrary();
    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
    });
  }

  async start() {
    console.log('\n🎸 Welcome to Big Flavor AI Agent! 🎸\n');
    console.log('I can help you with:');
    console.log('  - Song recommendations');
    console.log('  - Album creation');
    console.log('  - Audio analysis and improvement suggestions');
    console.log('  - General music advice\n');
    console.log('Commands:');
    console.log('  /songs    - List all songs');
    console.log('  /stats    - Show library statistics');
    console.log('  /analyze [id] - Analyze a specific song');
    console.log('  /recommend - Get song recommendations');
    console.log('  /album    - Create an album suggestion');
    console.log('  /reset    - Reset conversation');
    console.log('  /help     - Show this help');
    console.log('  /quit     - Exit\n');
    console.log('Or just chat naturally! Ask me anything about your music.\n');

    this.promptUser();
  }

  private promptUser() {
    this.rl.question('You: ', async (input) => {
      const trimmed = input.trim();

      if (!trimmed) {
        this.promptUser();
        return;
      }

      await this.handleInput(trimmed);
    });
  }

  private async handleInput(input: string) {
    try {
      if (input.startsWith('/')) {
        await this.handleCommand(input);
      } else {
        const response = await this.agent.chat(input);
        console.log('\n🤖 Agent:', response, '\n');
      }
    } catch (error) {
      console.error('\n❌ Error:', error instanceof Error ? error.message : 'Unknown error', '\n');
    }

    this.promptUser();
  }

  private async handleCommand(command: string) {
    const parts = command.split(' ');
    const cmd = parts[0].toLowerCase();
    const args = parts.slice(1);

    switch (cmd) {
      case '/songs':
        await this.listSongs();
        break;

      case '/stats':
        await this.showStats();
        break;

      case '/analyze':
        if (args.length === 0) {
          console.log('\n❌ Please provide a song ID. Example: /analyze 1\n');
        } else {
          await this.analyzeSong(args[0]);
        }
        break;

      case '/recommend':
        await this.getRecommendations();
        break;

      case '/album':
        await this.createAlbum();
        break;

      case '/reset':
        this.agent.resetConversation();
        console.log('\n✅ Conversation reset!\n');
        break;

      case '/help':
        this.showHelp();
        break;

      case '/quit':
      case '/exit':
        console.log('\n👋 Thanks for rocking with Big Flavor! See you next time! 🎸\n');
        this.rl.close();
        process.exit(0);
        break;

      default:
        console.log('\n❌ Unknown command. Type /help for available commands.\n');
    }
  }

  private async listSongs() {
    const songs = await this.songLibrary.getAllSongs();
    console.log('\n📚 Big Flavor Song Library:\n');
    songs.forEach((song) => {
      console.log(`  [${song.id}] ${song.title}`);
      console.log(`      Genre: ${song.genre} | Duration: ${Math.floor(song.duration / 60)}:${(song.duration % 60).toString().padStart(2, '0')}`);
      console.log(`      Mood: ${song.mood.join(', ')}`);
      if (song.bpm) console.log(`      BPM: ${song.bpm} | Key: ${song.key}`);
      console.log();
    });
  }

  private async showStats() {
    const stats = await this.songLibrary.getStatistics();
    console.log('\n📊 Library Statistics:\n');
    console.log(`  Total Songs: ${stats.totalSongs}`);
    console.log(`  Total Duration: ${stats.totalDurationFormatted}`);
    console.log(`  Genres: ${stats.genres.join(', ')}`);
    console.log(`  Most Common Genre: ${stats.mostCommonGenre}`);
    console.log(`  Average Song Length: ${stats.avgDuration} seconds\n`);
  }

  private async analyzeSong(songId: string) {
    const song = await this.songLibrary.getSongDetails(songId);
    if (!song) {
      console.log(`\n❌ Song with ID "${songId}" not found.\n`);
      return;
    }

    console.log(`\n🔍 Analyzing "${song.title}"...\n`);
    const response = await this.agent.analyzeSong(songId);
    console.log('🤖 Agent:', response, '\n');
  }

  private async getRecommendations() {
    console.log('\n🎵 Getting recommendations...\n');
    const response = await this.agent.recommendSongs({ count: 5 });
    console.log('🤖 Agent:', response, '\n');
  }

  private async createAlbum() {
    console.log('\n💿 Creating album suggestion...\n');
    const response = await this.agent.suggestAlbum();
    console.log('🤖 Agent:', response, '\n');
  }

  private showHelp() {
    console.log('\n📖 Available Commands:\n');
    console.log('  /songs           - List all songs in the library');
    console.log('  /stats           - Show library statistics');
    console.log('  /analyze [id]    - Analyze a specific song (e.g., /analyze 1)');
    console.log('  /recommend       - Get song recommendations');
    console.log('  /album           - Create an album suggestion');
    console.log('  /reset           - Reset the conversation context');
    console.log('  /help            - Show this help message');
    console.log('  /quit or /exit   - Exit the program\n');
    console.log('💬 Natural Chat:\n');
    console.log('  You can also chat naturally! Try:');
    console.log('    - "What are your most upbeat songs?"');
    console.log('    - "Can you help me create a mellow album?"');
    console.log('    - "How can we improve our sound quality?"');
    console.log('    - "What songs would work well together?"\n');
  }
}

// Start the CLI
const cli = new InteractiveCLI();
cli.start().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
