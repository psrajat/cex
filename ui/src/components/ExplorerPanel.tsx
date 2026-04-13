import Editor, { type OnMount } from '@monaco-editor/react'
import { useEffect, useRef, useState } from 'react'
import { fetchFileContent, fetchSymbols } from '../api'
import type { FileContent, FileInfo, Symbol } from '../types'
import type * as Monaco from 'monaco-editor'

interface Props {
  selectedFile: FileInfo | null
  fileLoadKey: number
  selectedSymbol: Symbol | null
  onSelectSymbol: (sym: Symbol) => void
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

// Per-type decoration colours.
const TYPE_BG: Record<string, string> = {
  function: 'rgba(86,156,214,0.07)',
  class:    'rgba(78,201,176,0.07)',
  method:   'rgba(220,220,170,0.07)',
  endpoint: 'rgba(206,145,120,0.07)',
  model:    'rgba(197,134,192,0.07)',
}
const TYPE_BORDER: Record<string, string> = {
  function: 'rgba(86,156,214,0.6)',
  class:    'rgba(78,201,176,0.6)',
  method:   'rgba(220,220,170,0.5)',
  endpoint: 'rgba(206,145,120,0.6)',
  model:    'rgba(197,134,192,0.6)',
}

// Inject decoration CSS once.
const STYLE_ID = 'cex-decoration-styles'
function ensureDecorationStyles() {
  if (document.getElementById(STYLE_ID)) return
  const types = ['function', 'class', 'method', 'endpoint', 'model']
  const rules = types.flatMap((t) => [
    `.cex-sym-${t} { background: ${TYPE_BG[t] ?? 'rgba(120,120,120,0.06)'}; }`,
    `.cex-sym-${t}-glyph::before { content:''; display:block; width:2px; height:100%; background:${TYPE_BORDER[t] ?? '#555'}; }`,
  ])
  const style = document.createElement('style')
  style.id = STYLE_ID
  style.textContent = rules.join('\n')
  document.head.appendChild(style)
}

// ── Tooltip ───────────────────────────────────────────────────────────────────
interface TooltipState { visible: boolean; x: number; y: number; symbol: Symbol | null }

function SymbolTooltip({ state }: { state: TooltipState }) {
  if (!state.visible || !state.symbol) return null
  const typeColor: Record<string, string> = {
    function: 'var(--c-function)', class: 'var(--c-class)', method: 'var(--c-method)',
    endpoint: 'var(--c-endpoint)', model: 'var(--c-model)',
  }
  const color = typeColor[state.symbol.type] ?? 'var(--c-default)'
  return (
    <div style={{
      position: 'fixed', left: state.x + 14, top: state.y - 6,
      zIndex: 9999, background: 'var(--bg-panel)', border: '1px solid var(--border)',
      borderRadius: 4, padding: '5px 10px', fontSize: 12, color: 'var(--text)',
      pointerEvents: 'none', boxShadow: '0 2px 8px rgba(0,0,0,0.4)',
      maxWidth: 420, whiteSpace: 'nowrap',
    }}>
      <span style={{ color, fontFamily: 'monospace', fontWeight: 600 }}>{state.symbol.type}</span>
      <span style={{ color: 'var(--text-muted)', margin: '0 5px' }}>·</span>
      <span style={{ fontFamily: 'monospace' }}>{state.symbol.name}</span>
      {state.symbol.signature !== state.symbol.name && (
        <div style={{ color: 'var(--text-dim)', fontSize: 11, marginTop: 2, fontFamily: 'monospace' }}>
          {state.symbol.signature}
        </div>
      )}
      <div style={{ color: 'var(--accent)', fontSize: 10, marginTop: 3 }}>click to explain</div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function ExplorerPanel({ selectedFile, fileLoadKey, selectedSymbol, onSelectSymbol }: Props) {
  const [fileContent, setFileContent] = useState<FileContent | null>(null)
  const [symbols, setSymbols] = useState<Symbol[]>([])
  const [loading, setLoading] = useState(false)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [tooltip, setTooltip] = useState<TooltipState>({ visible: false, x: 0, y: 0, symbol: null })

  const [cmdId, setCmdId] = useState<string | null>(null)
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null)
  const monacoRef = useRef<typeof Monaco | null>(null)
  const decorationsRef = useRef<Monaco.editor.IEditorDecorationsCollection | null>(null)
  const codeLensDisposableRef = useRef<Monaco.IDisposable | null>(null)

  // ── Refs kept in sync with latest state/props so stale closures always read
  // the current value without being re-registered. ─────────────────────────
  const symbolsRef = useRef<Symbol[]>([])
  const onSelectRef = useRef(onSelectSymbol)
  useEffect(() => { symbolsRef.current = symbols }, [symbols])
  useEffect(() => { onSelectRef.current = onSelectSymbol }, [onSelectSymbol])

  // ── Load file content + symbols when the selected file changes (or fileLoadKey bumps) ──
  useEffect(() => {
    if (!selectedFile) { setFileContent(null); setSymbols([]); setLoadError(null); return }
    let cancelled = false
    setLoading(true)
    setFileContent(null)
    setSymbols([])
    setLoadError(null)
    Promise.all([fetchFileContent(selectedFile.id), fetchSymbols(selectedFile.id)])
      .then(([fc, syms]) => {
        if (cancelled) return
        setFileContent(fc)
        setSymbols(syms)
      })
      .catch((err: unknown) => {
        if (cancelled) return
        setLoadError(err instanceof Error ? err.message : 'Failed to load file')
      })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  // fileLoadKey intentionally included so clicking the same file re-fetches
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedFile, fileLoadKey])

  // ── Rebuild decorations + CodeLens provider whenever symbols/file change ──
  useEffect(() => {
    const editor = editorRef.current
    const monaco = monacoRef.current
    if (!editor || !monaco || !fileContent) return

    ensureDecorationStyles()

    // Decorations (background highlight + glyph margin stripe).
    const decorations: Monaco.editor.IModelDeltaDecoration[] = symbols.map((sym) => ({
      range: new monaco.Range(sym.start_line, 1, sym.end_line, 1),
      options: {
        isWholeLine: true,
        className: `cex-sym-${sym.type}`,
        glyphMarginClassName: `cex-sym-${sym.type}-glyph`,
        overviewRuler: {
          color: TYPE_BORDER[sym.type] ?? '#555',
          position: monaco.editor.OverviewRulerLane.Left,
        },
      },
    }))
    if (decorationsRef.current) {
      decorationsRef.current.set(decorations)
    } else {
      decorationsRef.current = editor.createDecorationsCollection(decorations)
    }

    // CodeLens provider — dispose old one, register fresh one with current symbols.
    // The lenses call the single stable command registered at mount time.
    if (!cmdId || symbols.length === 0) return

    codeLensDisposableRef.current?.dispose()
    const lang = LANG_MAP[fileContent.language] ?? 'plaintext'
    codeLensDisposableRef.current = monaco.languages.registerCodeLensProvider(lang, {
      provideCodeLenses() {
        return {
          lenses: symbols.map((sym) => ({
            range: new monaco.Range(sym.start_line, 1, sym.start_line, 1),
            command: {
              id: cmdId,
              title: `✦ explain  ${sym.name}`,
              arguments: [sym.qualified_name],
            },
          })),
          dispose() {},
        }
      },
      resolveCodeLens(_model, codeLens) { return codeLens },
    })
  }, [symbols, fileContent, cmdId])

  // ── Dispose CodeLens on unmount ───────────────────────────────────────────
  useEffect(() => () => { codeLensDisposableRef.current?.dispose() }, [])

  // ── Scroll to symbol when it changes externally (e.g. FileTree click) ────
  useEffect(() => {
    if (!editorRef.current || !selectedSymbol || selectedSymbol.file_id !== selectedFile?.id) return
    editorRef.current.revealLineInCenter(selectedSymbol.start_line)
  }, [selectedSymbol, selectedFile])

  // ── Editor mount — register command once, wire mouse handlers ────────────
  const handleEditorMount: OnMount = (editor, monaco) => {
    editorRef.current = editor
    monacoRef.current = monaco
    ensureDecorationStyles()

    // Register a single stable command. All CodeLens items reference this ID.
    // The handler reads from symbolsRef so it never goes stale.
    // Monaco's command service prepends a service accessor as the first argument,
    // so the CodeLens `arguments[0]` value arrives as the second parameter.
    const rawId = editor.addCommand(0, (_accessor: unknown, qualifiedName: string) => {
      const sym = symbolsRef.current.find((s) => s.qualified_name === qualifiedName)
      if (sym) onSelectRef.current(sym)
    })
    if (rawId) setCmdId(rawId)

    // symAtLine reads from symbolsRef — no stale closure.
    function symAtLine(line: number): Symbol | null {
      return symbolsRef.current.find((s) => line >= s.start_line && line <= s.end_line) ?? null
    }

    // Click anywhere in the editor content → select the symbol at that line.
    editor.onMouseDown((e) => {
      if (
        e.target.type !== monaco.editor.MouseTargetType.CONTENT_TEXT &&
        e.target.type !== monaco.editor.MouseTargetType.CONTENT_EMPTY
      ) return
      const line = e.target.position?.lineNumber
      if (!line) return
      const sym = symAtLine(line)
      if (sym) onSelectRef.current(sym)
    })

    // Mouse move → show tooltip with type + name.
    editor.onMouseMove((e) => {
      const line = e.target.position?.lineNumber
      if (!line) { setTooltip((t) => ({ ...t, visible: false })); return }
      const sym = symAtLine(line)
      if (sym) {
        setTooltip({ visible: true, x: e.event.posx, y: e.event.posy, symbol: sym })
      } else {
        setTooltip((t) => ({ ...t, visible: false }))
      }
    })

    editor.onMouseLeave(() => setTooltip((t) => ({ ...t, visible: false })))
  }

  // ── Render ────────────────────────────────────────────────────────────────
  if (!selectedFile) {
    return (
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        background: 'var(--bg-base)', color: 'var(--text-muted)', gap: 10,
      }}>
        <svg width="48" height="48" viewBox="0 0 48 48" fill="none" opacity={0.3}>
          <rect x="6" y="6" width="36" height="36" rx="3" stroke="currentColor" strokeWidth="2" />
          <path d="M14 18h8M14 24h16M14 30h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
        </svg>
        <span style={{ fontSize: 13 }}>Select a file from the tree</span>
      </div>
    )
  }

  const language = LANG_MAP[fileContent?.language ?? ''] ?? 'plaintext'

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', position: 'relative' }}>
      {/* Breadcrumb */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 8,
        padding: '5px 12px', borderBottom: '1px solid var(--border)',
        background: 'var(--bg-panel)', flexShrink: 0, fontSize: 12,
        color: 'var(--text-dim)', overflow: 'hidden',
      }}>
        <span style={{ fontFamily: 'monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1 }}>
          {selectedFile.id}
        </span>
        <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>
          {symbols.length} symbol{symbols.length !== 1 ? 's' : ''}
        </span>
        {loading && <div className="spinner" style={{ width: 12, height: 12, borderWidth: 1.5 }} />}
      </div>

      {/* Monaco editor */}
      <div style={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
        {/* Loading overlay — covers the editor while fetching */}
        {loading && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 10,
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            background: 'var(--bg-base)', gap: 12,
          }}>
            <div className="editor-skeleton" aria-hidden="true">
              {Array.from({ length: 9 }).map((_, i) => (
                <div
                  key={i}
                  className="editor-skeleton-line"
                  style={{ width: `${88 - (i % 4) * 12}%` }}
                />
              ))}
            </div>
            <div className="spinner" style={{ width: 28, height: 28, borderWidth: 3 }} />
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Loading {selectedFile.id.split('/').pop()}…</span>
          </div>
        )}
        {/* Error overlay */}
        {!loading && loadError && (
          <div style={{
            position: 'absolute', inset: 0, zIndex: 10,
            display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
            background: 'var(--bg-base)', gap: 10,
          }}>
            <svg width="32" height="32" viewBox="0 0 32 32" fill="none" opacity={0.4}>
              <circle cx="16" cy="16" r="14" stroke="#ef5350" strokeWidth="2" />
              <path d="M16 9v9M16 22v1" stroke="#ef5350" strokeWidth="2" strokeLinecap="round" />
            </svg>
            <span style={{ fontSize: 12, color: '#ef5350', maxWidth: 260, textAlign: 'center', lineHeight: 1.5 }}>
              {loadError}
            </span>
            <button
              onClick={() => {
                // retry by re-running the effect
                setLoadError(null)
                setLoading(true)
                Promise.all([fetchFileContent(selectedFile.id), fetchSymbols(selectedFile.id)])
                  .then(([fc, syms]) => { setFileContent(fc); setSymbols(syms) })
                  .catch((err: unknown) => setLoadError(err instanceof Error ? err.message : 'Failed to load file'))
                  .finally(() => setLoading(false))
              }}
              style={{
                padding: '5px 14px', background: 'rgba(239,83,80,0.15)',
                border: '1px solid rgba(239,83,80,0.4)', borderRadius: 4,
                color: '#ef5350', fontSize: 12, cursor: 'pointer',
              }}
            >
              Retry
            </button>
          </div>
        )}
        <Editor
          height="100%"
          language={language}
          value={fileContent?.content ?? ''}
          theme="vs-dark"
          onMount={handleEditorMount}
          options={{
            readOnly: true,
            codeLens: true,
            fontSize: 13,
            fontFamily: '"Cascadia Code", "Fira Code", "Consolas", monospace',
            fontLigatures: true,
            lineNumbers: 'on',
            lineNumbersMinChars: 3,
            glyphMargin: true,
            minimap: { enabled: true, scale: 1 },
            scrollBeyondLastLine: false,
            wordWrap: 'off',
            renderLineHighlight: 'line',
            scrollbar: { verticalScrollbarSize: 8, horizontalScrollbarSize: 8 },
            padding: { top: 8, bottom: 12 },
            contextmenu: false,
            overviewRulerBorder: false,
          }}
        />
      </div>

      {/* Floating tooltip */}
      <SymbolTooltip state={tooltip} />
    </div>
  )
}
