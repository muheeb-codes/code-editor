import React, { useState, useEffect, useRef } from 'react';
import { Play, Code2, Layout, Download, RefreshCw, Copy, Check, Lightbulb, Settings, Type, Upload, Image } from 'lucide-react';
import CodeMirror from '@uiw/react-codemirror';
import { javascript } from '@codemirror/lang-javascript';
import { python } from '@codemirror/lang-python';
import { html } from '@codemirror/lang-html';
import { css } from '@codemirror/lang-css';
import { oneDark } from '@codemirror/theme-one-dark';
import { vscodeDark } from '@uiw/codemirror-theme-vscode';
import { githubDark, githubLight } from '@uiw/codemirror-theme-github';
import { dracula } from '@uiw/codemirror-theme-dracula';
import { tokyoNight } from '@uiw/codemirror-theme-tokyo-night';

const DEFAULT_HTML = `<!DOCTYPE html>
<html>
<head>
  <title>My Web Page</title>
</head>
<body>
  <div class="container">
    <h1>Welcome!</h1>
    <p>This is a sample web page.</p>
    <button onclick="showMessage()">Click me!</button>
  </div>
</body>
</html>`;

const DEFAULT_CSS = `body {
  font-family: 'Segoe UI', sans-serif;
  margin: 0;
  padding: 20px;
  background: #f0f2f5;
}

.container {
  max-width: 800px;
  margin: 0 auto;
  padding: 20px;
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

h1 {
  color: #1a73e8;
}

button {
  background: #1a73e8;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.3s;
}

button:hover {
  background: #1557b0;
}`;

const DEFAULT_JS = `function showMessage() {
  alert('Hello from JavaScript!');
}

// Add some interactivity
document.addEventListener('DOMContentLoaded', () => {
  const h1 = document.querySelector('h1');
  h1.style.cursor = 'pointer';
  
  h1.addEventListener('click', () => {
    h1.style.color = getRandomColor();
  });
});

function getRandomColor() {
  const letters = '0123456789ABCDEF';
  let color = '#';
  for (let i = 0; i < 6; i++) {
    color += letters[Math.floor(Math.random() * 16)];
  }
  return color;
}`;

const DEFAULT_PY_CODE = `# Python code example
def fibonacci(n):
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    
    sequence = [0, 1]
    while len(sequence) < n:
        sequence.append(sequence[-1] + sequence[-2])
    
    return sequence

# Generate first 10 Fibonacci numbers
result = fibonacci(10)
print(f"First 10 Fibonacci numbers: {result}")

# Calculate sum
total = sum(result)
print(f"Sum of the sequence: {total}")`;

type Language = 'html' | 'css' | 'javascript' | 'python';

interface EditorTab {
  id: Language;
  label: string;
  icon: React.ReactNode;
  extension: any;
  defaultCode: string;
}

function App() {
  const [activeTab, setActiveTab] = useState<Language>('html');
  const [codes, setCodes] = useState({
    html: DEFAULT_HTML,
    css: DEFAULT_CSS,
    javascript: DEFAULT_JS,
    python: DEFAULT_PY_CODE
  });
  const [output, setOutput] = useState<string[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const [showPreview, setShowPreview] = useState(true);
  const [copied, setCopied] = useState(false);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const [showSettings, setShowSettings] = useState(false);
  const [editorTheme, setEditorTheme] = useState('oneDark');
  const [fontSize, setFontSize] = useState(14);
  const [showImportModal, setShowImportModal] = useState(false);
  const [importType, setImportType] = useState<'project' | 'image'>('project');
  const fileInputRef = useRef<HTMLInputElement>(null);

  const themes = {
    oneDark,
    vscodeDark,
    githubDark,
    githubLight,
    dracula,
    tokyoNight
  };

  const tabs: EditorTab[] = [
    { id: 'html', label: 'HTML', icon: <Code2 size={16} />, extension: html(), defaultCode: DEFAULT_HTML },
    { id: 'css', label: 'CSS', icon: <Layout size={16} />, extension: css(), defaultCode: DEFAULT_CSS },
    { id: 'javascript', label: 'JavaScript', icon: <Play size={16} />, extension: javascript(), defaultCode: DEFAULT_JS },
    { id: 'python', label: 'Python', icon: <Code2 size={16} />, extension: python(), defaultCode: DEFAULT_PY_CODE }
  ];

  useEffect(() => {
    updatePreview();
  }, [codes.html, codes.css, codes.javascript]);

  const updatePreview = () => {
    const previewFrame = document.getElementById('preview') as HTMLIFrameElement;
    if (previewFrame) {
      const doc = previewFrame.contentDocument || previewFrame.contentWindow?.document;
      if (doc) {
        doc.open();
        doc.write(`
          <!DOCTYPE html>
          <html>
          <head>
            <meta charset="UTF-8">
            <style>${codes.css}</style>
          </head>
          <body>
            ${codes.html}
            <script>
              // Override alert to show in the output
              const originalAlert = window.alert;
              window.alert = function(message) {
                const output = document.createElement('div');
                output.style.position = 'fixed';
                output.style.top = '10px';
                output.style.left = '50%';
                output.style.transform = 'translateX(-50%)';
                output.style.padding = '10px 20px';
                output.style.background = 'rgba(0, 0, 0, 0.8)';
                output.style.color = 'white';
                output.style.borderRadius = '4px';
                output.style.zIndex = '9999';
                output.textContent = message;
                document.body.appendChild(output);
                setTimeout(() => output.remove(), 3000);
              };
              ${codes.javascript}
            </script>
          </body>
          </html>
        `);
        doc.close();
      }
    }
  };

  const handleCodeChange = (value: string) => {
    setCodes(prev => ({ ...prev, [activeTab]: value }));
    generateSuggestions(value);
  };

  const generateSuggestions = (code: string) => {
    // Simple code suggestions based on content
    const suggestions: string[] = [];

    if (activeTab === 'html' && !code.includes('viewport')) {
      suggestions.push('Add viewport meta tag for better mobile responsiveness');
    }
    if (activeTab === 'css' && !code.includes('media')) {
      suggestions.push('Consider adding media queries for responsive design');
    }
    if (activeTab === 'javascript' && !code.includes('addEventListener')) {
      suggestions.push('Use event listeners for better interaction handling');
    }

    setSuggestions(suggestions);
  };

  const runCode = async () => {
    setIsRunning(true);
    setOutput([]);

    try {
      if (activeTab === 'python') {
        setOutput(['Python execution is simulated in this demo']);
        await new Promise(resolve => setTimeout(resolve, 500));
        // Execute the Python code and capture its output
        const pythonCode = codes.python;
        const lines = pythonCode.split('\n');
        const output: string[] = [];

        // Simple Python interpreter simulation
        const variables: Record<string, number> = {};

        // Helper function to evaluate expressions
        const evaluateExpr = (expr: string): number => {
          // Replace variable names with their values
          const exprWithValues = expr.replace(/[a-zA-Z_][a-zA-Z0-9_]*/g, (match) => {
            return variables[match]?.toString() || match;
          });
          return eval(exprWithValues);
        };

        for (const line of lines) {
          if (line.trim()) {
            if (line.includes('print(')) {
              // Extract the expression inside print()
              const expr = line.match(/print\((.*)\)/)?.[1];
              if (expr) {
                try {
                  // Evaluate the expression
                  const result = evaluateExpr(expr);
                  output.push(result.toString());
                } catch (e: any) {
                  output.push(`Error: ${e?.message || 'Unknown error'}`);
                }
              }
            } else if (line.includes('=')) {
              // Handle variable assignments
              const [varName, expr] = line.split('=').map(s => s.trim());
              try {
                variables[varName] = evaluateExpr(expr);
              } catch (e: any) {
                output.push(`Error: ${e?.message || 'Unknown error'}`);
              }
            }
          }
        }
        setOutput(prev => [...prev, ...output]);
      } else {
        updatePreview();
      }
    } catch (error: any) {
      setOutput([`Error: ${error?.message || 'An unknown error occurred'}`]);
    } finally {
      setIsRunning(false);
    }
  };

  const copyCode = () => {
    navigator.clipboard.writeText(codes[activeTab]);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleFileImport = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    if (importType === 'project') {
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const content = e.target?.result as string;
          // Try to detect file type based on content
          if (content.includes('<!DOCTYPE html>') || content.includes('<html')) {
            setCodes(prev => ({ ...prev, html: content }));
            setActiveTab('html');
          } else if (content.includes('function') || content.includes('const ')) {
            setCodes(prev => ({ ...prev, javascript: content }));
            setActiveTab('javascript');
          } else if (content.includes('{') && content.includes('}')) {
            setCodes(prev => ({ ...prev, css: content }));
            setActiveTab('css');
          } else if (content.includes('def ') || content.includes('import ')) {
            setCodes(prev => ({ ...prev, python: content }));
            setActiveTab('python');
          }
        } catch (error) {
          console.error('Error reading file:', error);
        }
      };
      reader.readAsText(file);
    } else if (importType === 'image') {
      const reader = new FileReader();
      reader.onload = (e) => {
        const imageUrl = e.target?.result as string;
        // Insert image into HTML
        const imageTag = `<img src="${imageUrl}" alt="Imported image" style="max-width: 100%; height: auto;" />`;
        setCodes(prev => ({
          ...prev,
          html: prev.html.replace('</body>', `${imageTag}\n</body>`)
        }));
        setActiveTab('html');
      };
      reader.readAsDataURL(file);
    }
    setShowImportModal(false);
  };

  return (
    <div className="min-h-screen bg-gray-900 text-white">
      <header className="bg-gray-800 border-b border-gray-700 p-4">
        <div className="container mx-auto flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Code2 className="text-blue-400" size={24} />
            <h1 className="text-xl font-bold">Enhanced Code Editor</h1>
          </div>
          <div className="flex items-center space-x-4">
            <button
              onClick={() => {
                setShowImportModal(true);
                setImportType('project');
              }}
              className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
              title="Import Project"
            >
              <Upload size={16} />
            </button>
            <button
              onClick={() => {
                setShowImportModal(true);
                setImportType('image');
              }}
              className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
              title="Import Image"
            >
              <Image size={16} />
            </button>
            <button
              onClick={() => setShowSettings(!showSettings)}
              className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
            >
              <Settings size={16} />
            </button>
            <button
              onClick={() => setShowPreview(!showPreview)}
              className="px-3 py-1 bg-gray-700 hover:bg-gray-600 rounded transition-colors"
            >
              {showPreview ? 'Hide Preview' : 'Show Preview'}
            </button>
            <button
              onClick={runCode}
              disabled={isRunning}
              className="flex items-center space-x-2 px-4 py-2 bg-green-600 hover:bg-green-700 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isRunning ? <RefreshCw className="animate-spin" size={16} /> : <Play size={16} />}
              <span>{isRunning ? 'Running...' : 'Run'}</span>
            </button>
          </div>
        </div>
      </header>

      {showSettings && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 p-6 rounded-lg w-96">
            <h2 className="text-xl font-bold mb-4">Editor Settings</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium mb-2">Theme</label>
                <select
                  value={editorTheme}
                  onChange={(e) => setEditorTheme(e.target.value)}
                  className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2"
                >
                  <option value="oneDark">One Dark</option>
                  <option value="vscodeDark">VS Code Dark</option>
                  <option value="githubDark">GitHub Dark</option>
                  <option value="githubLight">GitHub Light</option>
                  <option value="dracula">Dracula</option>
                  <option value="tokyoNight">Tokyo Night</option>
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium mb-2">Font Size</label>
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setFontSize(prev => Math.max(8, prev - 1))}
                    className="px-2 py-1 bg-gray-700 rounded"
                  >
                    -
                  </button>
                  <span className="w-12 text-center">{fontSize}px</span>
                  <button
                    onClick={() => setFontSize(prev => Math.min(24, prev + 1))}
                    className="px-2 py-1 bg-gray-700 rounded"
                  >
                    +
                  </button>
                </div>
              </div>
              <button
                onClick={() => setShowSettings(false)}
                className="w-full bg-blue-600 hover:bg-blue-700 text-white py-2 rounded"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {showImportModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-gray-800 p-6 rounded-lg w-96">
            <h2 className="text-xl font-bold mb-4">
              Import {importType === 'project' ? 'Project' : 'Image'}
            </h2>
            <div className="space-y-4">
              <p className="text-sm text-gray-300">
                {importType === 'project'
                  ? 'Select a file to import (HTML, CSS, JavaScript, or Python)'
                  : 'Select an image to add to your project'}
              </p>
              <input
                type="file"
                ref={fileInputRef}
                onChange={handleFileImport}
                accept={importType === 'project'
                  ? '.html,.css,.js,.py,.txt'
                  : 'image/*'}
                className="hidden"
              />
              <div className="flex justify-end space-x-2">
                <button
                  onClick={() => setShowImportModal(false)}
                  className="px-4 py-2 bg-gray-700 hover:bg-gray-600 rounded"
                >
                  Cancel
                </button>
                <button
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded"
                >
                  Select File
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <main className="container mx-auto p-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="space-y-4">
          <div className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700">
            <div className="bg-gray-700 px-4 py-2 flex items-center space-x-2 overflow-x-auto">
              {tabs.map(tab => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`flex items-center space-x-2 px-3 py-1 rounded transition-colors ${activeTab === tab.id ? 'bg-blue-600' : 'hover:bg-gray-600'
                    }`}
                >
                  {tab.icon}
                  <span>{tab.label}</span>
                </button>
              ))}
            </div>
            <div className="flex items-center justify-end space-x-2 p-2 bg-gray-750">
              <button
                onClick={copyCode}
                className="p-1 hover:text-blue-400 transition-colors"
                title="Copy Code"
              >
                {copied ? <Check size={16} /> : <Copy size={16} />}
              </button>
              <button
                onClick={() => setCodes(prev => ({ ...prev, [activeTab]: tabs.find(t => t.id === activeTab)?.defaultCode || '' }))}
                className="p-1 hover:text-blue-400 transition-colors"
                title="Reset Code"
              >
                <RefreshCw size={16} />
              </button>
              <button
                onClick={() => {
                  const blob = new Blob([codes[activeTab]], { type: 'text/plain' });
                  const url = URL.createObjectURL(blob);
                  const a = document.createElement('a');
                  a.href = url;
                  a.download = `code.${activeTab}`;
                  a.click();
                  URL.revokeObjectURL(url);
                }}
                className="p-1 hover:text-blue-400 transition-colors"
                title="Download Code"
              >
                <Download size={16} />
              </button>
            </div>
            <CodeMirror
              value={codes[activeTab]}
              height="500px"
              theme={themes[editorTheme as keyof typeof themes]}
              extensions={[tabs.find(t => t.id === activeTab)?.extension || javascript()]}
              onChange={handleCodeChange}
              className="text-sm"
              style={{ fontSize: `${fontSize}px` }}
            />
          </div>

          {suggestions.length > 0 && (
            <div className="bg-gray-800 rounded-lg p-4 border border-gray-700">
              <div className="flex items-center space-x-2 mb-2">
                <Lightbulb size={16} className="text-yellow-400" />
                <h3 className="font-medium">Suggestions</h3>
              </div>
              <ul className="space-y-2 text-sm text-gray-300">
                {suggestions.map((suggestion, index) => (
                  <li key={index} className="flex items-center space-x-2">
                    <span>•</span>
                    <span>{suggestion}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="space-y-4">
          {showPreview ? (
            <div className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700 h-[600px]">
              <div className="bg-gray-700 px-4 py-2">
                <span className="font-medium">Preview</span>
              </div>
              <iframe
                id="preview"
                className="w-full h-[calc(100%-40px)] bg-white"
                sandbox="allow-scripts allow-same-origin"
              />
            </div>
          ) : (
            <div className="bg-gray-800 rounded-lg overflow-hidden border border-gray-700">
              <div className="bg-gray-700 px-4 py-2">
                <span className="font-medium">Output</span>
              </div>
              <div className="p-4 font-mono text-sm h-[500px] overflow-auto">
                {output.length > 0 ? (
                  output.map((line, i) => (
                    <div key={i} className="whitespace-pre-wrap mb-1">
                      {line}
                    </div>
                  ))
                ) : (
                  <div className="text-gray-500 italic">
                    Run your code to see the output here
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}

export default App;