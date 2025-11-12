'use client';

import { useState, useEffect } from 'react';
import Header from '@/components/Header';

interface Tool {
  name: string;
  description: string;
  parameters: any;
}

export default function AdminPage() {
  const [tools, setTools] = useState<Tool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedTool, setSelectedTool] = useState<Tool | null>(null);
  const [toolParams, setToolParams] = useState<Record<string, any>>({});
  const [executionResult, setExecutionResult] = useState<any>(null);
  const [executing, setExecuting] = useState(false);

  useEffect(() => {
    loadTools();
  }, []);

  const loadTools = async () => {
    try {
      const response = await fetch('/api/tools');

      if (response.status === 403) {
        setError('Access denied. Editor role required.');
        setLoading(false);
        return;
      }

      if (!response.ok) {
        throw new Error('Failed to load tools');
      }

      const data = await response.json();
      setTools(data.tools || []);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteTool = async () => {
    if (!selectedTool) return;

    setExecuting(true);
    setExecutionResult(null);

    try {
      const response = await fetch('/api/tools', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          tool_name: selectedTool.name,
          parameters: toolParams,
        }),
      });

      if (!response.ok) {
        throw new Error('Tool execution failed');
      }

      const data = await response.json();
      setExecutionResult(data.result);
    } catch (err: any) {
      setExecutionResult({ error: err.message });
    } finally {
      setExecuting(false);
    }
  };

  const handleParamChange = (paramName: string, value: any) => {
    setToolParams((prev) => ({
      ...prev,
      [paramName]: value,
    }));
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
          <p className="mt-4 text-gray-600 dark:text-gray-400">Loading tools...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="max-w-md w-full bg-white dark:bg-gray-800 rounded-lg shadow-lg p-8">
          <div className="text-red-600 dark:text-red-400 text-center">
            <svg className="w-16 h-16 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
            <h2 className="text-2xl font-bold mb-2">Access Denied</h2>
            <p className="text-gray-600 dark:text-gray-400">{error}</p>
            <a
              href="/"
              className="mt-6 inline-block px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
            >
              Back to Home
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <Header
        title="Admin Tools"
        subtitle="MCP Tools for audio processing and management"
      />

      <main className="container mx-auto px-4 py-8">
        <div className="grid md:grid-cols-3 gap-6">
          {/* Tools List */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              Available Tools
            </h2>
            <div className="space-y-2">
              {tools.length === 0 ? (
                <p className="text-gray-500 dark:text-gray-400">
                  No tools available
                </p>
              ) : (
                tools.map((tool) => (
                  <button
                    key={tool.name}
                    onClick={() => {
                      setSelectedTool(tool);
                      setToolParams({});
                      setExecutionResult(null);
                    }}
                    className={`w-full text-left p-3 rounded-lg transition ${
                      selectedTool?.name === tool.name
                        ? 'bg-blue-100 dark:bg-blue-900 text-blue-900 dark:text-blue-100'
                        : 'bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 text-gray-900 dark:text-white'
                    }`}
                  >
                    <p className="font-medium">{tool.name}</p>
                    <p className="text-sm opacity-75">{tool.description}</p>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Tool Parameters */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              Tool Parameters
            </h2>
            {!selectedTool ? (
              <p className="text-gray-500 dark:text-gray-400">
                Select a tool to configure parameters
              </p>
            ) : (
              <div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                  {selectedTool.description}
                </p>
                <div className="space-y-4">
                  {selectedTool.parameters &&
                    Object.entries(selectedTool.parameters).map(
                      ([paramName, paramInfo]: [string, any]) => (
                        <div key={paramName}>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                            {paramName}
                            {paramInfo.required && (
                              <span className="text-red-500 ml-1">*</span>
                            )}
                          </label>
                          <input
                            type={paramInfo.type === 'number' ? 'number' : 'text'}
                            value={toolParams[paramName] || ''}
                            onChange={(e) =>
                              handleParamChange(
                                paramName,
                                paramInfo.type === 'number'
                                  ? parseFloat(e.target.value)
                                  : e.target.value
                              )
                            }
                            placeholder={paramInfo.description}
                            className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:border-blue-500 dark:bg-gray-700 dark:text-white"
                          />
                          {paramInfo.description && (
                            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                              {paramInfo.description}
                            </p>
                          )}
                        </div>
                      )
                    )}
                </div>
                <button
                  onClick={handleExecuteTool}
                  disabled={executing}
                  className="w-full mt-6 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
                >
                  {executing ? 'Executing...' : 'Execute Tool'}
                </button>
              </div>
            )}
          </div>

          {/* Execution Result */}
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-4">
              Result
            </h2>
            {!executionResult ? (
              <p className="text-gray-500 dark:text-gray-400">
                No execution result yet
              </p>
            ) : (
              <div>
                {executionResult.error ? (
                  <div className="p-4 bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 rounded-lg">
                    <p className="font-semibold">Error:</p>
                    <p className="mt-2">{executionResult.error}</p>
                  </div>
                ) : (
                  <div className="p-4 bg-green-100 dark:bg-green-900 text-green-700 dark:text-green-200 rounded-lg">
                    <p className="font-semibold">Success!</p>
                    <pre className="mt-2 text-sm overflow-auto max-h-96">
                      {JSON.stringify(executionResult, null, 2)}
                    </pre>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
