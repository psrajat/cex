// api.ts — All HTTP calls to the FastAPI backend.
// All endpoints are relative so the Vite proxy forwards them in dev,
// and FastAPI serves them directly in production.

import type { ExplanationResult, FileContent, FileInfo, Symbol, Recommendation, PatchResult } from './types'

const BASE = '/api'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`)
  if (!res.ok) {
    const detail = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${detail}`)
  }
  return res.json() as Promise<T>
}

// ── Files ─────────────────────────────────────────────────────────────────────

// ── File System Picker ───────────────────────────────────────────────────────

export async function listDirectories(path: string): Promise<string[]> {
  const res = await fetch(`${BASE}/fs/ls?path=${encodeURIComponent(path)}`)
  if (!res.ok) throw new Error('Failed to list directories')
  const data = await res.json()
  return data.directories
}

export function fetchFiles(): Promise<FileInfo[]> {
  return get<FileInfo[]>('/files')
}

export function fetchFileContent(fileId: string): Promise<FileContent> {
  return get<FileContent>(`/file-content?file=${encodeURIComponent(fileId)}`)
}

// ── Ingestion ────────────────────────────────────────────────────────────────

export async function ingestRepo(
  payload: { repo_dir: string, force: boolean }
): Promise<{ ok: boolean, message: string }> {
  const res = await fetch(`${BASE}/ingest`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${text}`)
  }
  return res.json()
}

// ── Symbols ──────────────────────────────────────────────────────────────────

export function fetchSymbols(fileId?: string): Promise<Symbol[]> {
  const qs = fileId ? `?file=${encodeURIComponent(fileId)}` : ''
  return get<Symbol[]>(`/symbols${qs}`)
}

export function fetchSymbol(symbolId: string): Promise<Symbol> {
  return get<Symbol>(`/symbol?id=${encodeURIComponent(symbolId)}`)
}

export function fetchCallers(symbolId: string): Promise<Symbol[]> {
  return get<Symbol[]>(`/callers?id=${encodeURIComponent(symbolId)}`)
}

export function fetchCallees(symbolId: string): Promise<Symbol[]> {
  return get<Symbol[]>(`/callees?id=${encodeURIComponent(symbolId)}`)
}

export function fetchParent(symbolId: string): Promise<Symbol | null> {
  return get<Symbol | null>(`/parent?id=${encodeURIComponent(symbolId)}`)
}

// ── Explanation ───────────────────────────────────────────────────────────────

export function fetchExplanation(symbolId: string): Promise<ExplanationResult> {
  return get<ExplanationResult>(`/explanation?id=${encodeURIComponent(symbolId)}`)
}

/** POST /api/explain — generate silently (no streaming).  Use for background
 *  pre-generation; prefer streamExplanation() for interactive use. */
export async function generateExplanation(symbolId: string): Promise<string> {
  const res = await fetch(`${BASE}/explain?id=${encodeURIComponent(symbolId)}`, {
    method: 'POST',
  })
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`)
  }
  const data = (await res.json()) as ExplanationResult
  return data.text ?? ''
}

/**
 * Open an SSE connection to stream explanation tokens as they are generated.
 *
 * Returns a cleanup function that closes the EventSource when called.
 * Tokens arrive via onToken; completion (or error) via onDone.
 */
export function streamExplanation(
  symbolId: string,
  onToken: (token: string) => void,
  onDone: (error?: string) => void,
): () => void {
  const url = `${BASE}/explain/stream?id=${encodeURIComponent(symbolId)}`
  const es = new EventSource(url)

  es.onmessage = (event) => {
    if (event.data === '[DONE]') {
      es.close()
      onDone()
      return
    }
    // Server escapes newlines as "\\n" so one logical token fits on one SSE data line.
    const token = event.data.replace(/\\n/g, '\n')
    onToken(token)
  }

  es.onerror = () => {
    es.close()
    onDone('Connection error — is the cex server running?')
  }

  return () => es.close()
}

// ── Search ────────────────────────────────────────────────────────────────────

export function searchSymbols(query: string): Promise<Symbol[]> {
  return get<Symbol[]>(`/search?q=${encodeURIComponent(query)}`)
}

// ── Recommendation ────────────────────────────────────────────────────────────

export function fetchRecommendations(): Promise<Recommendation[]> {
  return get<Recommendation[]>('/recommendations')
}

export async function refreshRecommendations(): Promise<{ ok: boolean, count: number }> {
  const res = await fetch(`${BASE}/recommendations/refresh`, {
    method: 'POST',
  })
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`)
  }
  return res.json() as Promise<{ ok: boolean, count: number }>
}

export function fetchRecommendationPatch(id: string): Promise<PatchResult> {
  return get<PatchResult>(`/recommendations/patch?id=${encodeURIComponent(id)}`)
}
