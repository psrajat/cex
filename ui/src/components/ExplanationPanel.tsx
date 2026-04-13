import { useState } from 'react'
import type { ParsedExplanation, Symbol } from '../types'

interface Props {
  symbol: Symbol | null
  explanation: ParsedExplanation | null
  isStreaming: boolean
  streamError: string | null
  onGenerate: () => void
}

// ── Render helpers ────────────────────────────────────────────────────────────

function renderParagraph(text: string, streaming: boolean) {
  return (
    <p className={streaming ? 'cursor-blink' : ''} style={{ whiteSpace: 'pre-wrap', lineHeight: 1.65, margin: 0 }}>
      {text}
    </p>
  )
}

function renderNumberedList(text: string, streaming: boolean) {
  const items = text.split(/\n(?=\d+\.)/).map((s) => s.replace(/^\d+\.\s*/, '').trim()).filter(Boolean)
  if (items.length <= 1) return renderParagraph(text, streaming)
  return (
    <ol style={{ paddingLeft: 16, lineHeight: 1.7, margin: 0 }} className={streaming ? 'cursor-blink' : ''}>
      {items.map((item, i) => (
        <li key={i} style={{ marginBottom: 4, whiteSpace: 'pre-wrap' }}>{item}</li>
      ))}
    </ol>
  )
}

// ── Detail section definitions (Summary is handled separately) ────────────────

interface SectionDef {
  key: keyof ParsedExplanation
  label: string
  render: (text: string, streaming: boolean) => React.ReactNode
}

const DETAIL_SECTIONS: SectionDef[] = [
  { key: 'purpose',    label: 'Purpose',      render: renderParagraph },
  { key: 'howItWorks', label: 'How It Works', render: renderNumberedList },
  { key: 'notable',    label: 'Notable',      render: renderParagraph },
]

// ── Collapsible detail section ────────────────────────────────────────────────

function DetailSection({ def, text, streaming }: { def: SectionDef; text: string; streaming: boolean }) {
  const [open, setOpen] = useState(false)
  return (
    <div style={{ borderTop: '1px solid var(--border)' }}>
      <button
        onClick={() => setOpen((v) => !v)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '8px 12px', background: 'none', border: 'none', cursor: 'pointer',
          color: 'var(--text-dim)', fontSize: 11, fontWeight: 700,
          textTransform: 'uppercase', letterSpacing: '0.08em', userSelect: 'none',
        }}
      >
        <span>{def.label}</span>
        <svg
          width="10" height="10" viewBox="0 0 10 10" fill="currentColor"
          style={{
            flexShrink: 0, color: 'var(--text-muted)',
            transform: open ? 'rotate(90deg)' : 'none',
            transition: 'transform 0.15s',
          }}
        >
          <path d="M3 2l4 3-4 3V2z" />
        </svg>
      </button>
      {open && (
        <div style={{ padding: '0 12px 12px', fontSize: 13, color: 'var(--text)' }}>
          {def.render(text, streaming)}
        </div>
      )}
    </div>
  )
}

// ── Streaming raw view (before any sections parse) ────────────────────────────

function StreamingView({ text }: { text: string }) {
  return (
    <div style={{ padding: '12px 14px' }}>
      <p className="cursor-blink" style={{ whiteSpace: 'pre-wrap', lineHeight: 1.65, fontSize: 13, color: 'var(--text)', margin: 0 }}>
        {text || <span style={{ color: 'var(--text-muted)' }}>Generating…</span>}
      </p>
    </div>
  )
}

// ── Symbol metadata bar ───────────────────────────────────────────────────────

function SymbolMeta({ symbol }: { symbol: Symbol }) {
  const typeColor: Record<string, string> = {
    function: 'var(--c-function)',
    class:    'var(--c-class)',
    method:   'var(--c-method)',
    endpoint: 'var(--c-endpoint)',
    model:    'var(--c-model)',
  }
  const color = typeColor[symbol.type] ?? 'var(--c-default)'

  return (
    <div style={{
      padding: '10px 12px 8px',
      borderBottom: '1px solid var(--border)',
      flexShrink: 0,
    }}>
      <div style={{
        fontFamily: 'monospace',
        fontSize: 13,
        fontWeight: 600,
        color,
        overflow: 'hidden',
        textOverflow: 'ellipsis',
        whiteSpace: 'nowrap',
        marginBottom: 4,
      }}>
        {symbol.name}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {symbol.file_id}&nbsp;·&nbsp;lines {symbol.start_line}–{symbol.end_line}
      </div>
      {symbol.signature && symbol.signature !== symbol.name && (
        <div style={{
          marginTop: 6,
          fontFamily: 'monospace',
          fontSize: 11,
          color: 'var(--text-dim)',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
          whiteSpace: 'nowrap',
          padding: '3px 6px',
          background: 'var(--bg-panel)',
          borderRadius: 3,
        }}>
          {symbol.signature}
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ExplanationPanel({ symbol, explanation, isStreaming, streamError, onGenerate }: Props) {
  // Empty state.
  if (!symbol) {
    return (
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
        <div className="panel-header">Explanation</div>
        <div style={{
          flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: 'var(--text-muted)', fontSize: 12, padding: 16, textAlign: 'center', lineHeight: 1.6,
        }}>
          Select a symbol to see its explanation.
        </div>
      </div>
    )
  }

  const hasSummary = Boolean(explanation?.summary)
  const hasAnyContent = Boolean(
    explanation && (explanation.summary || explanation.purpose || explanation.howItWorks || explanation.notable)
  )
  const availableDetails = DETAIL_SECTIONS.filter((s) => Boolean(explanation?.[s.key]))

  // Show raw streaming text until the LLM output starts being parsed into sections.
  const showStreamView = isStreaming && !hasAnyContent

  // The streaming cursor belongs on the last visible detail section once one exists,
  // otherwise it belongs on the summary.
  const lastDetailIdx = availableDetails.length - 1

  return (
    <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      <div className="panel-header">Explanation</div>

      <SymbolMeta symbol={symbol} />

      <div style={{ flex: 1, overflowY: 'auto' }}>
        {/* Error banner */}
        {streamError && (
          <div style={{
            margin: 10, padding: '8px 12px', borderRadius: 4,
            background: 'rgba(244,67,54,0.12)', border: '1px solid rgba(244,67,54,0.3)',
            color: '#ef5350', fontSize: 12, lineHeight: 1.5,
          }}>
            {streamError}
          </div>
        )}

        {/* Raw streaming view — before any sections have been parsed */}
        {showStreamView && <StreamingView text={explanation?.raw ?? ''} />}

        {/* Summary — always visible, no toggle */}
        {hasSummary && (
          <div style={{ padding: '12px 12px 10px' }}>
            <p
              className={isStreaming && availableDetails.length === 0 ? 'cursor-blink' : ''}
              style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.7, whiteSpace: 'pre-wrap', margin: 0 }}
            >
              {explanation!.summary}
            </p>
          </div>
        )}

        {/* Collapsible detail sections — only rendered once content exists */}
        {availableDetails.map((sec, i) => (
          <DetailSection
            key={sec.key}
            def={sec}
            text={explanation![sec.key] as string}
            streaming={isStreaming && i === lastDetailIdx}
          />
        ))}

        {/* Spinner while streaming and some content is already showing */}
        {isStreaming && hasAnyContent && (
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 12px', borderTop: '1px solid var(--border)',
            color: 'var(--text-muted)', fontSize: 11,
          }}>
            <div className="spinner" style={{ width: 12, height: 12, borderWidth: 1.5 }} />
            Generating…
          </div>
        )}

        {/* Generate button — shown when no explanation and not streaming */}
        {!isStreaming && !hasAnyContent && !streamError && (
          <div style={{ padding: '20px 14px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 12, color: 'var(--text-muted)', textAlign: 'center', lineHeight: 1.5 }}>
              No explanation cached yet.
            </span>
            <button
              onClick={onGenerate}
              style={{
                padding: '7px 18px', background: 'var(--accent)', color: '#fff',
                border: 'none', borderRadius: 4, cursor: 'pointer',
                fontSize: 13, fontWeight: 600, letterSpacing: '0.02em', transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => { (e.target as HTMLButtonElement).style.background = 'var(--accent-hover)' }}
              onMouseLeave={(e) => { (e.target as HTMLButtonElement).style.background = 'var(--accent)' }}
            >
              Generate Explanation
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
