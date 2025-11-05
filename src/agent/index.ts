import OpenAI from 'openai';
import { config } from 'dotenv';

config();

/**
 * Big Flavor AI Agent
 * Interacts with the MCP server to provide intelligent music recommendations
 * and management capabilities
 */
class BigFlavorAgent {
  private openai: OpenAI;
  private conversationHistory: Array<{ role: string; content: string }> = [];

  constructor() {
    const apiKey = process.env.OPENAI_API_KEY;
    if (!apiKey) {
      throw new Error('OPENAI_API_KEY not found in environment variables');
    }

    this.openai = new OpenAI({ apiKey });

    // System prompt for the agent
    this.conversationHistory.push({
      role: 'system',
      content: `You are an AI assistant for Big Flavor, a dad band made up of friends who enjoy playing music together. 
Your role is to help manage their song library, provide recommendations, suggest album arrangements, and offer sound engineering advice.

The band members are dads who play music for fun - they're not professionals, so keep advice friendly, encouraging, and practical.
When suggesting improvements, be constructive and focus on achievable enhancements.

You have access to tools via an MCP server that can:
- Retrieve songs from their library
- Analyze audio characteristics
- Recommend songs based on preferences
- Suggest album arrangements
- Provide sound engineering improvements

Be enthusiastic about their music and help them make the most of their creative sessions!`,
    });
  }

  async chat(userMessage: string): Promise<string> {
    this.conversationHistory.push({
      role: 'user',
      content: userMessage,
    });

    try {
      const response = await this.openai.chat.completions.create({
        model: 'gpt-4-turbo-preview',
        messages: this.conversationHistory as any,
        temperature: 0.7,
        max_tokens: 1000,
      });

      const assistantMessage =
        response.choices[0]?.message?.content ||
        "I'm having trouble responding right now.";

      this.conversationHistory.push({
        role: 'assistant',
        content: assistantMessage,
      });

      return assistantMessage;
    } catch (error) {
      console.error('Error calling OpenAI:', error);
      return 'Sorry, I encountered an error. Please try again.';
    }
  }

  /**
   * Get song recommendations based on user preferences
   */
  async recommendSongs(criteria: {
    mood?: string;
    genre?: string;
    seedSongId?: string;
    count?: number;
  }): Promise<string> {
    const prompt = `Based on the following criteria, recommend some songs from Big Flavor's library:
${criteria.mood ? `- Mood: ${criteria.mood}` : ''}
${criteria.genre ? `- Genre: ${criteria.genre}` : ''}
${criteria.seedSongId ? `- Similar to song ID: ${criteria.seedSongId}` : ''}
${criteria.count ? `- Number of songs: ${criteria.count}` : ''}

Please explain why each recommendation would work well.`;

    return this.chat(prompt);
  }

  /**
   * Suggest an album arrangement
   */
  async suggestAlbum(theme?: string, songCount?: number): Promise<string> {
    const prompt = `Please create an album arrangement for Big Flavor with the following:
${theme ? `- Theme: ${theme}` : '- No specific theme, just a cohesive collection'}
${songCount ? `- Number of songs: ${songCount}` : '- 8-10 songs'}

Explain the song order and why these songs work well together.`;

    return this.chat(prompt);
  }

  /**
   * Analyze a song and suggest improvements
   */
  async analyzeSong(songId: string): Promise<string> {
    const prompt = `Please analyze song ID "${songId}" and provide:
1. Audio characteristics (tempo, key, loudness, etc.)
2. Specific sound engineering suggestions
3. Practical tips for improvement that dad musicians can implement

Remember to be encouraging and focus on achievable improvements!`;

    return this.chat(prompt);
  }

  /**
   * General music advice
   */
  async getMusicAdvice(question: string): Promise<string> {
    return this.chat(question);
  }

  /**
   * Reset conversation history
   */
  resetConversation(): void {
    this.conversationHistory = this.conversationHistory.slice(0, 1); // Keep system message
  }
}

// Example usage
async function main() {
  console.log('🎸 Big Flavor AI Agent 🎸\n');

  const agent = new BigFlavorAgent();

  // Example interactions
  console.log('=== Example 1: General Question ===');
  const response1 = await agent.chat(
    "What's in the Big Flavor song library?"
  );
  console.log(response1);
  console.log('\n');

  console.log('=== Example 2: Song Recommendations ===');
  const response2 = await agent.recommendSongs({
    mood: 'upbeat',
    count: 3,
  });
  console.log(response2);
  console.log('\n');

  console.log('=== Example 3: Album Suggestion ===');
  const response3 = await agent.suggestAlbum('Summer Vibes', 6);
  console.log(response3);
  console.log('\n');

  console.log('=== Example 4: Song Analysis ===');
  const response4 = await agent.analyzeSong('1');
  console.log(response4);
  console.log('\n');
}

// Only run main if this file is executed directly
if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch(console.error);
}

export { BigFlavorAgent };
