/**
 * Example usage of the Big Flavor AI Agent
 * This demonstrates how to interact with the agent programmatically
 */

import { BigFlavorAgent } from './agent/index.js';

async function runExamples() {
  console.log('🎸 Welcome to Big Flavor AI Agent Examples! 🎸\n');
  console.log('=' .repeat(60));

  const agent = new BigFlavorAgent();

  // Example 1: Ask about the library
  console.log('\n📚 Example 1: Asking about the song library');
  console.log('-'.repeat(60));
  try {
    const response = await agent.chat(
      "Can you tell me about the songs in Big Flavor's library?"
    );
    console.log('Agent:', response);
  } catch (error) {
    console.error('Error:', error);
  }

  // Example 2: Get recommendations for an upbeat playlist
  console.log('\n\n🎵 Example 2: Getting upbeat song recommendations');
  console.log('-'.repeat(60));
  try {
    const response = await agent.recommendSongs({
      mood: 'upbeat',
      count: 3,
    });
    console.log('Agent:', response);
  } catch (error) {
    console.error('Error:', error);
  }

  // Example 3: Create a themed album
  console.log('\n\n💿 Example 3: Creating a themed album');
  console.log('-'.repeat(60));
  try {
    const response = await agent.suggestAlbum('Weekend Jams', 5);
    console.log('Agent:', response);
  } catch (error) {
    console.error('Error:', error);
  }

  // Example 4: Analyze a specific song
  console.log('\n\n🔍 Example 4: Analyzing a song');
  console.log('-'.repeat(60));
  try {
    const response = await agent.analyzeSong('1');
    console.log('Agent:', response);
  } catch (error) {
    console.error('Error:', error);
  }

  // Example 5: Get general music advice
  console.log('\n\n💡 Example 5: Getting music advice');
  console.log('-'.repeat(60));
  try {
    const response = await agent.getMusicAdvice(
      "We want to improve our live performance. Any tips for dad musicians?"
    );
    console.log('Agent:', response);
  } catch (error) {
    console.error('Error:', error);
  }

  // Example 6: Interactive conversation
  console.log('\n\n💬 Example 6: Having a conversation');
  console.log('-'.repeat(60));
  try {
    const q1 = await agent.chat(
      "What genre does Big Flavor play most?"
    );
    console.log('Agent:', q1);

    const q2 = await agent.chat(
      "Can you recommend songs in that genre?"
    );
    console.log('Agent:', q2);
  } catch (error) {
    console.error('Error:', error);
  }

  console.log('\n' + '='.repeat(60));
  console.log('Examples complete! Rock on! 🤘\n');
}

// Run examples
runExamples().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
