import Header from '@/components/Header';

export default function Home() {
  return (
    <div className="min-h-screen flex flex-col">
      <Header />

      <main className="flex-1 container mx-auto p-8">
        <div className="grid md:grid-cols-2 gap-8">
          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 className="text-2xl font-bold mb-4">Search Songs</h2>
            <p className="text-gray-600 dark:text-gray-300 mb-4">
              Use natural language to find songs by mood, tempo, genre, or lyrics.
            </p>
            <a
              href="/search"
              className="inline-block bg-blue-600 text-white px-6 py-2 rounded hover:bg-blue-700"
            >
              Start Searching
            </a>
          </div>

          <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-lg">
            <h2 className="text-2xl font-bold mb-4">BigFlavor Radio</h2>
            <p className="text-gray-600 dark:text-gray-300 mb-4">
              Let our AI DJ create a personalized music experience for you.
            </p>
            <a
              href="/radio"
              className="inline-block bg-purple-600 text-white px-6 py-2 rounded hover:bg-purple-700"
            >
              Listen Now
            </a>
          </div>
        </div>
      </main>

      <footer className="bg-gray-900 text-white text-center p-4">
        <p>BigFlavor Band Agent - Powered by Claude AI</p>
      </footer>
    </div>
  );
}
