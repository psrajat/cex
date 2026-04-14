import { useState } from 'react'
import Editor, { DiffEditor } from '@monaco-editor/react'
import type { Symbol, PatchResult } from '../types'

interface Props {
  symbol: Symbol | null
  patch?: PatchResult | null
  mode?: 'symbol' | 'patch'
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

export default function CodePanel({ symbol, patch, mode = 'symbol' }: Props) {
  const [patchTab, setPatchTab] = useState<'unified' | 'split' | 'explanation'>('unified')
  const [selectedFileIdx, setSelectedFileIdx] = useState(0)

  if (mode === 'patch' && patch) {
    const currentFile = patch.file_patches?.[selectedFileIdx]

    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', background: 'var(--bg-base)' }}>
        <div style={{
          padding: '5px 12px',
          borderBottom: '1px solid var(--border)',
          background: 'var(--bg-panel)',
          fontSize: 12,
          color: 'var(--text-dim)',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <span>Patch: {patch.recommendation_id}</span>
          <div style={{ display: 'flex', gap: 12 }}>
            {patch.file_patches?.length > 1 && patchTab === 'split' && (
              <select 
                value={selectedFileIdx}
                onChange={e => setSelectedFileIdx(parseInt(e.target.value))}
                style={{ background: 'var(--bg-base)', color: 'var(--text)', border: '1px solid var(--border)', fontSize: 11 }}
              >
                {patch.file_patches.map((fp, i) => (
                  <option key={fp.path} value={i}>{fp.path}</option>
                ))}
              </select>
            )}
            <span>{patch.files.join(', ')}</span>
          </div>
        </div>
        
        {/* Tab bar */}
        <div style={{ display: 'flex', background: 'var(--bg-base)', borderBottom: '1px solid var(--border)' }}>
          {(['unified', 'split', 'explanation'] as const).map(t => (
            <button 
              key={t}
              onClick={() => setPatchTab(t)}
              style={{ 
                padding: '10px 16px', 
                background: patchTab === t ? 'var(--bg-panel)' : 'transparent', 
                border: 'none', 
                borderBottom: patchTab === t ? '2px solid var(--accent)' : '2px solid transparent',
                color: patchTab === t ? 'var(--text)' : 'var(--text-muted)',
                cursor: 'pointer', fontSize: 12, fontWeight: patchTab === t ? 600 : 400,
                textTransform: 'capitalize'
              }}
            >
              {t === 'unified' ? 'Unified Diff' : t === 'split' ? 'Split Diff' : 'Explanation'}
            </button>
          ))}
        </div>

        <div style={{ flex: 1, overflow: 'hidden' }}>
          {patchTab === 'explanation' ? (
            <div style={{ padding: 20, overflowY: 'auto', height: '100%', color: 'var(--text)', fontSize: 14, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
               {patch.explained_diff_text || 'No explanation provided.'}
            </div>
          ) : patchTab === 'split' ? (
            <DiffEditor
              height="100%"
              original={currentFile?.old || ''} 
              modified={currentFile?.new || ''}
              language={LANG_MAP[currentFile?.path.split('.').pop() || ''] || 'plaintext'}
              theme="vs-dark"
              options={{
                readOnly: true,
                fontSize: 13,
                fontFamily: '"Cascadia Code", "Fira Code", "Consolas", monospace',
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                renderSideBySide: true,
              }}
            />
          ) : (
            <Editor
              height="100%"
              value={patch.diff_text}
              language="diff"
              theme="vs-dark"
              options={{
                readOnly: true,
                fontSize: 13,
                fontFamily: '"Cascadia Code", "Fira Code", "Consolas", monospace',
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                wordWrap: 'on',
                renderWhitespace: 'none',
                scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
                padding: { top: 12, bottom: 12 },
              }}
            />
          )}
        </div>
      </div>
    )
  }

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
