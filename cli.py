"""
Interactive CLI for Big Flavor Band AI Agent
Provides a menu-driven interface for exploring agent features.
"""

import asyncio
import json
from agent import BigFlavorAgent


class BigFlavorCLI:
    """Command-line interface for the Big Flavor Band Agent."""
    
    def __init__(self):
        self.agent = None
        self.running = True
    
    async def initialize(self):
        """Initialize the agent."""
        print("\n🎸 Initializing Big Flavor Agent...")
        self.agent = BigFlavorAgent()
        await self.agent.initialize()
        print(f"✓ Loaded {len(self.agent.song_library)} songs\n")
    
    def display_menu(self):
        """Display the main menu."""
        print("\n" + "="*60)
        print("🎸 BIG FLAVOR BAND AI AGENT")
        print("="*60)
        print("\n1. Get song recommendation")
        print("2. Find similar songs")
        print("3. Create album suggestion")
        print("4. Analyze album flow")
        print("5. Get audio engineering suggestions")
        print("6. Compare song quality")
        print("7. Generate setlist")
        print("8. List all songs")
        print("9. Exit")
        print("\n" + "-"*60)
    
    async def get_recommendation(self):
        """Get next song recommendation."""
        print("\n--- Song Recommendation ---\n")
        
        # Show available songs
        print("Available songs:")
        for i, song in enumerate(self.agent.song_library, 1):
            print(f"  {i}. {song['title']} ({song['genre']}, {song['mood']})")
        
        choice = input("\nEnter song number for context (or press Enter for any): ").strip()
        
        current_song_id = None
        if choice and choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(self.agent.song_library):
                current_song_id = self.agent.song_library[idx]['id']
        
        mood = input("Desired mood (upbeat/melancholic/relaxed/energetic/fun or Enter for any): ").strip() or None
        energy = input("Desired energy (low/medium/high or Enter for any): ").strip() or None
        
        print("\n🎵 Generating recommendation...")
        result = await self.agent.suggest_next_song(
            current_song_id=current_song_id,
            mood=mood,
            energy=energy
        )
        
        print(f"\n✨ Recommended: {result['recommended_song']['title']}")
        print(f"   Genre: {result['recommended_song']['genre']}")
        print(f"   Mood: {result['recommended_song']['mood']}")
        print(f"   Tempo: {result['recommended_song']['tempo_bpm']} BPM")
        print(f"   Confidence: {result['confidence_score']}/100")
        print("\n   Why this song?")
        for reason in result['reasons']:
            print(f"   • {reason}")
        
        input("\nPress Enter to continue...")
    
    async def find_similar(self):
        """Find similar songs."""
        print("\n--- Find Similar Songs ---\n")
        
        print("Available songs:")
        for i, song in enumerate(self.agent.song_library, 1):
            print(f"  {i}. {song['title']}")
        
        choice = input("\nEnter song number: ").strip()
        
        if not choice.isdigit():
            print("Invalid choice")
            return
        
        idx = int(choice) - 1
        if not (0 <= idx < len(self.agent.song_library)):
            print("Invalid choice")
            return
        
        song_id = self.agent.song_library[idx]['id']
        
        print("\n🔍 Finding similar songs...")
        result = await self.agent.suggest_similar_songs(song_id, limit=5)
        
        print(f"\nSongs similar to '{result['reference_song']['title']}':")
        for i, song in enumerate(result['similar_songs'], 1):
            print(f"\n{i}. {song['title']}")
            print(f"   Genre: {song['genre']}")
            print(f"   Similarity: {song['similarity_score']}%")
            print(f"   Matching: {', '.join(song['matching_attributes'])}")
        
        input("\nPress Enter to continue...")
    
    async def create_album(self):
        """Create album suggestion."""
        print("\n--- Create Album ---\n")
        
        theme = input("Album theme (e.g., 'upbeat rock', 'blues' or Enter for mixed): ").strip() or None
        duration = input("Target duration in minutes (default 45): ").strip()
        duration = int(duration) if duration.isdigit() else 45
        
        print("\n💿 Creating album...")
        result = await self.agent.create_album_suggestion(
            theme=theme,
            target_duration_minutes=duration
        )
        
        print(f"\n✨ Album: {result['album_name']}")
        print(f"   Theme: {result['theme']}")
        print(f"   Duration: {result['total_duration_minutes']} minutes")
        print(f"   Tracks: {result['track_count']}")
        
        print("\n   Track Listing:")
        for track in result['tracks']:
            mins = track['duration_seconds'] // 60
            secs = track['duration_seconds'] % 60
            print(f"   {track['track_number']}. {track['title']} ({mins}:{secs:02d})")
            print(f"      {track['genre']} • {track['mood']} • {track['tempo_bpm']} BPM")
        
        print("\n   Curation Notes:")
        for note in result['curation_notes']:
            print(f"   • {note}")
        
        input("\nPress Enter to continue...")
    
    async def analyze_flow(self):
        """Analyze album flow."""
        print("\n--- Analyze Album Flow ---\n")
        
        print("Available songs:")
        for i, song in enumerate(self.agent.song_library, 1):
            print(f"  {i}. {song['title']}")
        
        choices = input("\nEnter song numbers separated by commas: ").strip()
        
        try:
            indices = [int(x.strip()) - 1 for x in choices.split(',')]
            song_ids = [self.agent.song_library[i]['id'] for i in indices if 0 <= i < len(self.agent.song_library)]
            
            if len(song_ids) < 2:
                print("Need at least 2 songs to analyze flow")
                return
            
            print("\n📊 Analyzing flow...")
            result = await self.agent.analyze_album_flow(song_ids)
            
            print(f"\n✨ Flow Analysis")
            print(f"   Overall Rating: {result['flow_rating'].upper()}")
            print(f"   Score: {result['overall_flow_score']}/100")
            
            print("\n   Track Order:")
            for track in result['track_order']:
                print(f"   {track['position']}. {track['title']}")
            
            if result['improvement_suggestions']:
                print("\n   Suggestions for Improvement:")
                for suggestion in result['improvement_suggestions']:
                    print(f"   • {suggestion}")
            
        except (ValueError, IndexError):
            print("Invalid input")
        
        input("\nPress Enter to continue...")
    
    async def audio_suggestions(self):
        """Get audio engineering suggestions."""
        print("\n--- Audio Engineering Suggestions ---\n")
        
        print("Available songs:")
        for i, song in enumerate(self.agent.song_library, 1):
            print(f"  {i}. {song['title']} ({song.get('audio_quality', 'unknown')} quality)")
        
        choice = input("\nEnter song number: ").strip()
        
        if not choice.isdigit():
            print("Invalid choice")
            return
        
        idx = int(choice) - 1
        if not (0 <= idx < len(self.agent.song_library)):
            print("Invalid choice")
            return
        
        song_id = self.agent.song_library[idx]['id']
        
        print("\n🎚️ Analyzing audio...")
        result = await self.agent.get_audio_engineering_suggestions(song_id)
        
        print(f"\n✨ Audio Analysis: {result['song_title']}")
        print(f"   Current Quality: {result['current_quality']}")
        print(f"   Improvement Potential: {result['estimated_improvement_potential']['percentage']}%")
        
        print("\n   Priority Actions:")
        for action in result['priority_actions']:
            print(f"   {action}")
        
        print("\n   Mixing Suggestions:")
        for tip in result['improvement_suggestions']['mixing'][:5]:
            print(f"   • {tip}")
        
        input("\nPress Enter to continue...")
    
    async def compare_quality(self):
        """Compare song quality."""
        print("\n--- Compare Song Quality ---\n")
        
        print("Available songs:")
        for i, song in enumerate(self.agent.song_library, 1):
            print(f"  {i}. {song['title']} ({song.get('audio_quality', 'unknown')})")
        
        choices = input("\nEnter song numbers separated by commas (or Enter for all): ").strip()
        
        if not choices:
            song_ids = [s['id'] for s in self.agent.song_library]
        else:
            try:
                indices = [int(x.strip()) - 1 for x in choices.split(',')]
                song_ids = [self.agent.song_library[i]['id'] for i in indices if 0 <= i < len(self.agent.song_library)]
            except (ValueError, IndexError):
                print("Invalid input")
                return
        
        print("\n📊 Comparing quality...")
        result = await self.agent.compare_song_quality(song_ids)
        
        print(f"\n✨ Quality Comparison")
        print(f"   Average Score: {result['average_quality_score']}/100")
        
        print("\n   Quality Rankings:")
        for i, song in enumerate(result['quality_ranking'], 1):
            print(f"   {i}. {song['title']}")
            print(f"      Quality: {song['quality']} ({song['quality_score']}/100)")
        
        if result['recommendations']:
            print("\n   Recommendations:")
            for rec in result['recommendations']:
                print(f"   • {rec}")
        
        input("\nPress Enter to continue...")
    
    async def generate_setlist(self):
        """Generate performance setlist."""
        print("\n--- Generate Setlist ---\n")
        
        duration = input("Target duration in minutes (default 60): ").strip()
        duration = int(duration) if duration.isdigit() else 60
        
        print("\nEnergy flow options:")
        print("  1. Varied (mix energy levels)")
        print("  2. Building (start low, end high)")
        print("  3. Consistent (maintain steady energy)")
        
        flow_choice = input("Choose energy flow (1-3): ").strip()
        flow_map = {'1': 'varied', '2': 'building', '3': 'consistent'}
        energy_flow = flow_map.get(flow_choice, 'varied')
        
        print("\n🎤 Generating setlist...")
        result = await self.agent.suggest_setlist(
            duration_minutes=duration,
            energy_flow=energy_flow
        )
        
        print(f"\n✨ Setlist: {result['setlist_name']}")
        print(f"   Duration: {result['duration_minutes']} minutes")
        print(f"   Energy Flow: {result['energy_flow']}")
        
        print("\n   Songs:")
        for song in result['songs']:
            print(f"\n   {song['position']}. {song['title']}")
            print(f"      Duration: {song['duration_minutes']} min | Energy: {song['energy']}")
            print(f"      Note: {song['performance_notes']}")
        
        print("\n   Performance Notes:")
        for note in result['setlist_notes']:
            print(f"   • {note}")
        
        input("\nPress Enter to continue...")
    
    def list_songs(self):
        """List all songs in library."""
        print("\n--- Song Library ---\n")
        
        for i, song in enumerate(self.agent.song_library, 1):
            print(f"{i}. {song['title']}")
            print(f"   Genre: {song['genre']} | Mood: {song['mood']} | Energy: {song['energy']}")
            print(f"   Tempo: {song['tempo_bpm']} BPM | Key: {song['key']}")
            print(f"   Quality: {song.get('audio_quality', 'unknown')}")
            print()
        
        input("Press Enter to continue...")
    
    async def run(self):
        """Run the CLI."""
        await self.initialize()
        
        menu_actions = {
            '1': self.get_recommendation,
            '2': self.find_similar,
            '3': self.create_album,
            '4': self.analyze_flow,
            '5': self.audio_suggestions,
            '6': self.compare_quality,
            '7': self.generate_setlist,
            '8': lambda: self.list_songs(),
            '9': self.exit_cli
        }
        
        while self.running:
            self.display_menu()
            choice = input("Enter your choice (1-9): ").strip()
            
            action = menu_actions.get(choice)
            if action:
                if asyncio.iscoroutinefunction(action):
                    await action()
                else:
                    action()
            else:
                print("\n❌ Invalid choice. Please try again.")
                await asyncio.sleep(1)
    
    def exit_cli(self):
        """Exit the CLI."""
        print("\n🎸 Thanks for using Big Flavor Band AI Agent!")
        print("Rock on! 🤘\n")
        self.running = False


async def main():
    """Main entry point."""
    cli = BigFlavorCLI()
    try:
        await cli.run()
    except KeyboardInterrupt:
        print("\n\n🎸 Interrupted. Rock on! 🤘\n")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print("Make sure dependencies are installed: pip install -r requirements.txt\n")


if __name__ == "__main__":
    asyncio.run(main())
