'use client';

import { useState, useRef, useEffect } from 'react';
import AudioPlayer from '@/components/AudioPlayer';

interface Message {
  role: 'user' | 'agent';
  content: string;
  timestamp: Date;
}

export default function RadioPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      role: 'agent',
      content: "Hey there! I'm your BigFlavor DJ. Tell me what kind of music you're in the mood for, or request a specific song!",
      timestamp: new Date(),
    },
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [loading, setLoading] = useState(false);
  const [currentSong, setCurrentSong] = useState<any>(null);
  const [playlist, setPlaylist] = useState<any[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSendMessage = async () => {
    if (!inputMessage.trim() || loading) return;

    const userMessage: Message = {
      role: 'user',
      content: inputMessage,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage('');
    setLoading(true);

    try {
      const response = await fetch('/api/agent/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          message: inputMessage,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get response from agent');
      }

      const data = await response.json();

      const agentMessage: Message = {
        role: 'agent',
        content: data.response,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, agentMessage]);

      // If the agent returned songs, add them to playlist
      if (data.songs && data.songs.length > 0) {
        setPlaylist((prev) => [...prev, ...data.songs]);

        // If no song is currently playing, start playing the first one
        if (!currentSong && data.songs[0]) {
          setCurrentSong(data.songs[0]);
        }
      }
    } catch (error: any) {
      const errorMessage: Message = {
        role: 'agent',
        content: `Sorry, I encountered an error: ${error.message}`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const quickRequests = [
    'Play something upbeat',
    'I want a slow ballad',
    'Something with a guitar solo',
    'Play your favorite song',
    'Create a chill playlist',
  ];

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex flex-col">
      <header className="bg-gradient-to-r from-purple-600 to-blue-600 text-white shadow-lg">
        <div className="container mx-auto px-4 py-6">
          <div className="flex justify-between items-center">
            <div>
              <h1 className="text-3xl font-bold">BigFlavor Radio</h1>
              <p className="text-purple-100 mt-1">
                Your AI DJ - Chat to request songs and create playlists
              </p>
            </div>
            <a
              href="/"
              className="text-white hover:text-purple-100 underline"
            >
              Back to Home
            </a>
          </div>
        </div>
      </header>

      <main className="flex-1 container mx-auto px-4 py-6 flex gap-6">
        {/* Chat Interface */}
        <div className="flex-1 bg-white dark:bg-gray-800 rounded-lg shadow-lg flex flex-col">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Chat with DJ
            </h2>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {messages.map((message, index) => (
              <div
                key={index}
                className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
              >
                <div
                  className={`max-w-[70%] rounded-lg p-3 ${
                    message.role === 'user'
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-200 dark:bg-gray-700 text-gray-900 dark:text-white'
                  }`}
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>
                  <p className="text-xs mt-1 opacity-70">
                    {message.timestamp.toLocaleTimeString()}
                  </p>
                </div>
              </div>
            ))}
            {loading && (
              <div className="flex justify-start">
                <div className="bg-gray-200 dark:bg-gray-700 rounded-lg p-3">
                  <div className="flex space-x-2">
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.2s' }}></div>
                    <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: '0.4s' }}></div>
                  </div>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          <div className="p-4 border-t border-gray-200 dark:border-gray-700">
            <div className="flex gap-2 mb-2 flex-wrap">
              {quickRequests.map((request, index) => (
                <button
                  key={index}
                  onClick={() => {
                    setInputMessage(request);
                  }}
                  className="px-3 py-1 text-sm bg-purple-100 dark:bg-purple-900 text-purple-700 dark:text-purple-200 rounded-full hover:bg-purple-200 dark:hover:bg-purple-800"
                  disabled={loading}
                >
                  {request}
                </button>
              ))}
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Request a song or ask for recommendations..."
                className="flex-1 px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:border-purple-500 dark:bg-gray-700 dark:text-white"
                disabled={loading}
              />
              <button
                onClick={handleSendMessage}
                disabled={loading || !inputMessage.trim()}
                className="px-6 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                Send
              </button>
            </div>
          </div>
        </div>

        {/* Playlist Sidebar */}
        <div className="w-80 bg-white dark:bg-gray-800 rounded-lg shadow-lg">
          <div className="p-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
              Playlist
            </h2>
          </div>
          <div className="p-4">
            {playlist.length === 0 ? (
              <p className="text-gray-500 dark:text-gray-400 text-center py-8">
                No songs in playlist yet. Request some songs!
              </p>
            ) : (
              <div className="space-y-2">
                {playlist.map((song, index) => (
                  <div
                    key={index}
                    className={`p-3 rounded-lg cursor-pointer transition ${
                      currentSong?.id === song.id
                        ? 'bg-purple-100 dark:bg-purple-900'
                        : 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                    onClick={() => setCurrentSong(song)}
                  >
                    <p className="font-medium text-gray-900 dark:text-white">
                      {song.title}
                    </p>
                    {song.genre && (
                      <p className="text-sm text-gray-600 dark:text-gray-400">
                        {song.genre}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </main>

      {currentSong && (
        <AudioPlayer
          song={currentSong}
          onClose={() => setCurrentSong(null)}
        />
      )}
    </div>
  );
}
