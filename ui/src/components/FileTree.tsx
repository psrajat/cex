import { useEffect, useMemo, useState } from 'react'
import { fetchSymbols } from '../api'
import type { FileInfo, Symbol, SymbolType } from '../types'

interface Props {
  files: FileInfo[]
  searchResults: Symbol[] | null   // non-null means we are in search mode
  selectedSymbol: Symbol | null
  selectedFileId: string | null
  onSelectSymbol: (sym: Symbol) => void
  onSelectFile: (file: FileInfo) => void
}

// ── Tree model ────────────────────────────────────────────────────────────────
interface DirNode  { type: 'dir';  name: string; path: string; children: TreeEntry[] }
interface FileNode { type: 'file'; name: string; path: string; file: FileInfo }
type TreeEntry = DirNode | FileNode

function buildTree(files: FileInfo[]): TreeEntry[] {
  const dirMap = new Map<string, DirNode>()
  const root: TreeEntry[] = []

  function ensureDir(parts: string[], depth: number): DirNode {
    const path = parts.slice(0, depth).join('/')
    if (dirMap.has(path)) return dirMap.get(path)!
    const node: DirNode = { type: 'dir', name: parts[depth - 1]!, path, children: [] }
    dirMap.set(path, node)
    if (depth === 1) root.push(node)
    else ensureDir(parts, depth - 1).children.push(node)
    return node
  }

  for (const file of files) {
    const parts = file.id.split('/')
    const fileNode: FileNode = { type: 'file', name: parts[parts.length - 1]!, path: file.id, file }
    if (parts.length === 1) root.push(fileNode)
    else ensureDir(parts, parts.length - 1).children.push(fileNode)
  }

  function sort(entries: TreeEntry[]): void {
    entries.sort((a, b) => {
      if (a.type !== b.type) return a.type === 'dir' ? -1 : 1
      return a.name.localeCompare(b.name)
    })
    for (const e of entries) if (e.type === 'dir') sort(e.children)
  }
  sort(root)
  return root
}

// ── Type badge ────────────────────────────────────────────────────────────────
const TYPE_LABEL: Record<string, string> = {
  function: 'fn', class: 'cls', method: 'fn', endpoint: 'ep', model: 'mdl',
}

function TypeBadge({ type }: { type: SymbolType }) {
  const cls = ['function', 'class', 'method', 'endpoint', 'model'].includes(type) ? type : 'default'
  return <span className={`type-badge ${cls}`}>{TYPE_LABEL[type] ?? type.slice(0, 3)}</span>
}

// ── Chevron icon ──────────────────────────────────────────────────────────────
function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      width="10" height="10" viewBox="0 0 10 10" fill="currentColor"
      style={{
        color: 'var(--text-muted)', flexShrink: 0,
        transform: open ? 'rotate(90deg)' : 'none',
        transition: 'transform 0.15s',
      }}
    >
      <path d="M3 2l4 3-4 3V2z" />
    </svg>
  )
}

// ── Shared props carried down the tree ────────────────────────────────────────
interface SharedProps {
  selectedFileId: string | null
  selectedSymbol: Symbol | null
  onSelectFile: (f: FileInfo) => void
  onSelectSymbol: (s: Symbol) => void
}

// ── Folder node ───────────────────────────────────────────────────────────────
function DirRow({ node, depth, ...shared }: { node: DirNode; depth: number } & SharedProps) {
  // Top-level dirs start open; deeper ones start collapsed.
  const [open, setOpen] = useState(depth === 0)

  // Auto-expand when the active file lives inside this directory.
  useEffect(() => {
    if (shared.selectedFileId?.startsWith(node.path + '/')) setOpen(true)
  }, [shared.selectedFileId, node.path])

  const indent = depth * 12 + 8

  return (
    <div>
      <div
        className="file-row"
        style={{ paddingLeft: indent }}
        onClick={() => setOpen((v) => !v)}
      >
        <Chevron open={open} />
        {/* Folder icon */}
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
          <path
            d="M1 5h5l2 2h7v7H1z"
            fill={open ? 'rgba(229,192,21,0.65)' : 'rgba(229,192,21,0.35)'}
            stroke="rgba(229,192,21,0.75)" strokeWidth="0.6"
          />
        </svg>
        <span style={{ fontSize: 12, color: 'var(--text)' }}>{node.name}</span>
      </div>
      {open && node.children.map((child) =>
        child.type === 'dir'
          ? <DirRow  key={child.path} node={child}  depth={depth + 1} {...shared} />
          : <FileRow key={child.path} node={child} depth={depth + 1} {...shared} />
      )}
    </div>
  )
}

// ── File node ─────────────────────────────────────────────────────────────────
function FileRow({ node, depth, ...shared }: { node: FileNode; depth: number } & SharedProps) {
  const [symOpen, setSymOpen] = useState(false)
  const [symbols, setSymbols] = useState<Symbol[]>([])
  const [loading, setLoading] = useState(false)

  const isActive = shared.selectedFileId === node.file.id
  const indent   = depth * 12 + 8

  function handleToggleSymbols(e: React.MouseEvent) {
    e.stopPropagation()
    if (!symOpen && symbols.length === 0) {
      setLoading(true)
      fetchSymbols(node.file.id)
        .then(setSymbols)
        .catch(() => setSymbols([]))
        .finally(() => setLoading(false))
    }
    setSymOpen((v) => !v)
  }

  return (
    <div>
      {/* File row */}
      <div
        className="file-row"
        style={{
          paddingLeft: indent,
          background: isActive ? 'var(--bg-hover)' : undefined,
          borderLeft: isActive ? '2px solid var(--accent)' : '2px solid transparent',
        }}
        onClick={() => shared.onSelectFile(node.file)}
        title={node.file.id}
      >
        {/* File icon */}
        <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
          <path d="M3 2h7l3 3v9H3V2z" stroke="rgba(150,175,210,0.55)" strokeWidth="1.2" fill="none" />
          <path d="M10 2v3h3"          stroke="rgba(150,175,210,0.55)" strokeWidth="1.2" fill="none" />
        </svg>
        <span style={{
          flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          fontSize: 12, color: isActive ? 'var(--text)' : 'var(--text-dim)',
          fontWeight: isActive ? 500 : 400,
        }}>
          {node.name}
        </span>
        {/* Symbol toggle — always visible, shows ≡ / ▾ */}
        <button
          onClick={handleToggleSymbols}
          title={symOpen ? 'Hide symbols' : 'Show symbols'}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            padding: '0 4px', lineHeight: 1, flexShrink: 0,
            color: symOpen ? 'var(--accent)' : 'var(--text-muted)',
            fontSize: 13, opacity: 0.75,
          }}
        >
          {symOpen ? '▾' : '≡'}
        </button>
      </div>

      {/* Symbol list — only when user has toggled it open */}
      {symOpen && (
        <div>
          {loading && (
            <div style={{ paddingLeft: indent + 20, paddingTop: 4, paddingBottom: 4, color: 'var(--text-muted)', fontSize: 11 }}>
              loading…
            </div>
          )}
          {symbols.map((sym) => (
            <div
              key={sym.qualified_name}
              className={`symbol-row ${shared.selectedSymbol?.qualified_name === sym.qualified_name ? 'active' : ''}`}
              style={{ paddingLeft: indent + 18 }}
              onClick={() => shared.onSelectSymbol(sym)}
              title={sym.signature}
            >
              <TypeBadge type={sym.type} />
              <span className="name" style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {sym.name}
              </span>
              <span style={{ fontSize: 10, color: 'var(--text-muted)', flexShrink: 0 }}>
                {sym.start_line}
              </span>
            </div>
          ))}
          {!loading && symbols.length === 0 && (
            <div style={{ paddingLeft: indent + 20, color: 'var(--text-muted)', fontSize: 11, paddingBottom: 4 }}>
              no symbols
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── FileTree ──────────────────────────────────────────────────────────────────
export default function FileTree({ files, searchResults, selectedSymbol, selectedFileId, onSelectSymbol, onSelectFile }: Props) {
  const tree = useMemo(() => buildTree(files), [files])

  // ── Search mode ───────────────────────────────────────────────────────────
  if (searchResults !== null) {
    return (
      <div style={{ flex: 1 }}>
        <div className="panel-header">Search Results ({searchResults.length})</div>
        {searchResults.length === 0 && (
          <div style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12 }}>
            No symbols found.
          </div>
        )}
        {searchResults.map((sym) => (
          <div
            key={sym.qualified_name}
            className={`symbol-row ${selectedSymbol?.qualified_name === sym.qualified_name ? 'active' : ''}`}
            style={{ paddingLeft: 12 }}
            onClick={() => onSelectSymbol(sym)}
            title={sym.file_id}
          >
            <TypeBadge type={sym.type} />
            <div style={{ overflow: 'hidden', minWidth: 0 }}>
              <div className="name" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {sym.name}
              </div>
              <div style={{ fontSize: 10, color: 'var(--text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {sym.file_id}
              </div>
            </div>
          </div>
        ))}
      </div>
    )
  }

  // ── File tree mode ────────────────────────────────────────────────────────
  const shared: SharedProps = { selectedFileId, selectedSymbol, onSelectFile, onSelectSymbol }
  return (
    <div style={{ flex: 1 }}>
      <div className="panel-header">Explorer</div>
      {files.length === 0 && (
        <div style={{ padding: '12px 16px', color: 'var(--text-muted)', fontSize: 12, lineHeight: 1.5 }}>
          No files ingested yet.<br />
          Run <code style={{ color: 'var(--c-function)' }}>cex ingest &lt;repo&gt;</code>
        </div>
      )}
      {tree.map((entry) =>
        entry.type === 'dir'
          ? <DirRow  key={entry.path} node={entry} depth={0} {...shared} />
          : <FileRow key={entry.path} node={entry} depth={0} {...shared} />
      )}
    </div>
  )
}
