import { useCallback, useEffect, useState } from 'react'
import { fetchFiles, fetchExplanation, searchSymbols, streamExplanation } from './api'
import type { FileInfo, ParsedExplanation, Symbol } from './types'
import FileTree from './components/FileTree'
import CodePanel from './components/CodePanel'
import ExplorerPanel from './components/ExplorerPanel'
import ExplanationPanel from './components/ExplanationPanel'
import SearchBar from './components/SearchBar'

type Tab = 'explorer' | 'symbol'

export default function App() {
  // ── Data state ─────────────────────────────────────────────────────────────
  const [files, setFiles] = useState<FileInfo[]>([])
  const [selectedFile, setSelectedFile] = useState<FileInfo | null>(null)
  const [fileLoadKey, setFileLoadKey] = useState(0)   // incremented on every file click to force re-fetch
  const [selectedSymbol, setSelectedSymbol] = useState<Symbol | null>(null)
  const [searchResults, setSearchResults] = useState<Symbol[] | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('explorer')

  // ── Explanation state ──────────────────────────────────────────────────────
  const [explanation, setExplanation] = useState<ParsedExplanation | null>(null)
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamError, setStreamError] = useState<string | null>(null)

  // ── Load file list on mount ────────────────────────────────────────────────
  useEffect(() => {
    fetchFiles()
      .then(setFiles)
      .catch(() => {/* server not running yet — FileTree shows empty state */})
  }, [])

  // ── When a symbol is selected from FileTree, switch to Symbol tab if file view
  // is not the right file; otherwise just scroll in Explorer.
  function handleSelectSymbol(sym: Symbol) {
    setSelectedSymbol(sym)
    // If a different file is open in Explorer, switch to Symbol tab so the user
    // immediately sees the isolated code body without a full file reload.
    if (activeTab === 'explorer' && selectedFile?.id !== sym.file_id) {
      setActiveTab('symbol')
    }
  }

  // ── File selection from tree — auto-switch to Explorer tab ─────────────────
  function handleSelectFile(file: FileInfo) {
    setSelectedFile(file)
    setFileLoadKey((k) => k + 1)   // always increment so clicking the same file re-fetches
    setActiveTab('explorer')
  }

  // ── When a symbol is selected, load its cached explanation ─────────────────
  useEffect(() => {
    if (!selectedSymbol) {
      setExplanation(null)
      setStreamError(null)
      return
    }
    setExplanation(null)
    setStreamError(null)
    setIsStreaming(false)

    fetchExplanation(selectedSymbol.qualified_name)
      .then((res) => {
        if (res.text) setExplanation(parseExplanation(res.text))
      })
      .catch(() => {})
  }, [selectedSymbol])

  // ── Stream a new explanation from the LLM ──────────────────────────────────
  const handleGenerate = useCallback(() => {
    if (!selectedSymbol || isStreaming) return

    setExplanation(null)
    setStreamError(null)
    setIsStreaming(true)

    let raw = ''
    const cleanup = streamExplanation(
      selectedSymbol.qualified_name,
      (token) => {
        raw += token
        setExplanation(parseExplanation(raw))
      },
      (err) => {
        setIsStreaming(false)
        if (err) setStreamError(err)
        else setExplanation(parseExplanation(raw))
      },
    )

    return cleanup
  }, [selectedSymbol, isStreaming])

  // ── Search ─────────────────────────────────────────────────────────────────
  const handleSearch = useCallback((query: string) => {
    if (!query.trim()) {
      setSearchResults(null)
      return
    }
    searchSymbols(query)
      .then(setSearchResults)
      .catch(() => setSearchResults([]))
  }, [])

  const handleClearSearch = useCallback(() => {
    setSearchResults(null)
  }, [])

  // ── Layout ─────────────────────────────────────────────────────────────────
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', background: 'var(--bg-base)' }}>
      {/* Header */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        height: 36,
        background: 'var(--accent)',
        flexShrink: 0,
      }}>
        <span style={{ fontWeight: 700, fontSize: 13, color: '#fff', letterSpacing: '0.03em' }}>
          cex — Code EXplainer
        </span>
        {selectedSymbol && (
          <span style={{ fontSize: 11, color: 'rgba(255,255,255,0.75)' }}>
            {selectedFile && activeTab === 'explorer' ? selectedFile.id : selectedSymbol.qualified_name}
          </span>
        )}
      </header>

      {/* Search bar */}
      <div style={{
        padding: '6px 10px',
        borderBottom: '1px solid var(--border)',
        background: 'var(--bg-sidebar)',
        flexShrink: 0,
      }}>
        <SearchBar onSearch={handleSearch} onClear={handleClearSearch} />
      </div>

      {/* Three-column main area */}
      <div style={{ display: 'flex', flex: 1, overflow: 'hidden' }}>
        {/* Left: file tree (or search results) */}
        <aside style={{
          width: 260,
          flexShrink: 0,
          borderRight: '1px solid var(--border)',
          background: 'var(--bg-sidebar)',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <FileTree
            files={files}
            searchResults={searchResults}
            selectedSymbol={selectedSymbol}
            selectedFileId={selectedFile?.id ?? null}
            onSelectSymbol={handleSelectSymbol}
            onSelectFile={handleSelectFile}
          />
        </aside>

        {/* Centre: tabbed code view */}
        <main style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {/* Tab bar */}
          <div style={{
            display: 'flex',
            borderBottom: '1px solid var(--border)',
            background: 'var(--bg-panel)',
            flexShrink: 0,
          }}>
            {(['explorer', 'symbol'] as Tab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                style={{
                  padding: '6px 16px',
                  background: 'none',
                  border: 'none',
                  borderBottom: activeTab === tab ? '2px solid var(--accent)' : '2px solid transparent',
                  color: activeTab === tab ? 'var(--text)' : 'var(--text-muted)',
                  fontSize: 12,
                  fontWeight: activeTab === tab ? 600 : 400,
                  cursor: 'pointer',
                  textTransform: 'capitalize',
                  letterSpacing: '0.02em',
                  transition: 'color 0.1s',
                }}
              >
                {tab === 'explorer' ? 'Explorer' : 'Symbol'}
              </button>
            ))}
          </div>

          {/* Panel content */}
          {activeTab === 'explorer' ? (
            <ExplorerPanel
              selectedFile={selectedFile}
              fileLoadKey={fileLoadKey}
              selectedSymbol={selectedSymbol}
              onSelectSymbol={handleSelectSymbol}
            />
          ) : (
            <CodePanel symbol={selectedSymbol} />
          )}
        </main>

        {/* Right: explanation panel */}
        <aside style={{
          width: 380,
          flexShrink: 0,
          borderLeft: '1px solid var(--border)',
          background: 'var(--bg-sidebar)',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
        }}>
          <ExplanationPanel
            symbol={selectedSymbol}
            explanation={explanation}
            isStreaming={isStreaming}
            streamError={streamError}
            onGenerate={handleGenerate}
          />
        </aside>
      </div>
    </div>
  )
}

// ── Explanation text parser ───────────────────────────────────────────────────

function parseExplanation(text: string): ParsedExplanation {
  const result: ParsedExplanation = { raw: text }

  const sections: Array<{ key: keyof ParsedExplanation; header: RegExp }> = [
    { key: 'summary',    header: /^SUMMARY\s*:?\s*/im },
    { key: 'purpose',    header: /^PURPOSE\s*:?\s*/im },
    { key: 'howItWorks', header: /^HOW IT WORKS\s*:?\s*/im },
    { key: 'notable',    header: /^NOTABLE\s*:?\s*/im },
  ]

  // Find the position of each section header so we can extract the text between them.
  const positions: Array<{ key: keyof ParsedExplanation; start: number; end: number }> = []
  for (const { key, header } of sections) {
    const m = text.match(header)
    if (m && m.index !== undefined) {
      positions.push({ key, start: m.index + m[0].length, end: text.length })
    }
  }
  positions.sort((a, b) => a.start - b.start)
  for (let i = 0; i < positions.length; i++) {
    if (i + 1 < positions.length) {
      // The end of this section is the start of the next header (back up to remove the header itself)
      const nextHeaderStart = positions[i + 1].start
      const candidate = text.lastIndexOf('\n', nextHeaderStart - 2)
      positions[i].end = candidate > positions[i].start ? candidate : nextHeaderStart
    }
    const sectionText = text.slice(positions[i].start, positions[i].end).trim()
    if (sectionText) {
      // TypeScript union key assignment requires a cast here
      (result as unknown as Record<string, string>)[positions[i].key as string] = sectionText
    }
  }

  return result
}
