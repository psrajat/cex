import Editor from '@monaco-editor/react'
import type { Symbol } from '../types'

interface Props {
  symbol: Symbol | null
}

// Map our language strings to Monaco language IDs.
const LANG_MAP: Record<string, string> = {
  python:     'python',
  javascript: 'javascript',
  typescript: 'typescript',
  go:         'go',
  rust:       'rust',
  java:       'java',
  cpp:        'cpp',
  c:          'c',
}

export default function CodePanel({ symbol }: Props) {
  if (!symbol) {
    return (
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg-base)',
        color: 'var(--text-muted)',
        gap: 10,
      }}>
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none" opacity={0.3}>
          <rect x="6" y="6" width="36" height="36" rx="3" stroke="currentColor" strokeWidth="2" />
          <path d="M14 18h8M14 24h16M14 30h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <span style={{ fontSize: 13 }}>Select a symbol from the file tree</span>
      </div>
    )
  }

  const language = LANG_MAP[symbol.metadata?.language as string] ?? 'plaintext'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg-base)' }}>
      {/* File + location breadcrumb */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '5px 12px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-panel)',
        flexShrink: 0,
        fontSize: 12,
        color: 'var(--text-dim)',
        overflow: 'hidden',
      }}>
        <span style={{ fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {symbol.file_id}
        </span>
        <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>·</span>
        <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>
          lines {symbol.start_line}–{symbol.end_line}
        </span>
        <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>·</span>
        <span style={{ color: 'var(--text-dim)', flexShrink: 0, fontFamily: 'monospace' }}>
          {symbol.type}
        </span>
      </div>

      {/* Monaco editor */}
      <div style={{ flex: 1, overflow: 'hidden' }}>
        <Editor
          height="100%"
          language={language}
          value={symbol.code_body}
          theme="vs-dark"
          options={{
            readOnly: true,
            fontSize: 13,
            fontFamily: '"Cascadia Code", "Fira Code", "Consolas", monospace',
            fontLigatures: true,
            lineNumbers: 'on',
            lineNumbersMinChars: 3,
            minimap: { enabled: false },
            scrollBeyondLastLine: false,
            wordWrap: 'on',
            renderLineHighlight: 'line',
            scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
            padding: { top: 12, bottom: 12 },
            contextmenu: false,
            folding: true,
            renderWhitespace: 'none',
            guides: { indentation: true },
          }}
        />
      </div>
    </div>
  )
}
