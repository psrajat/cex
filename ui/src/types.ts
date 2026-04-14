// types.ts — TypeScript interfaces mirroring the FastAPI Pydantic models.

export interface FileInfo {
  id: string          // file path (e.g. "httpie/core.py")
  extension: string   // ".py"
  language: string    // "python"
}

export type SymbolType = 'function' | 'class' | 'method' | 'endpoint' | 'model' | string

export interface Symbol {
  id: string
  file_id: string
  type: SymbolType
  name: string
  qualified_name: string
  signature: string
  code_body: string
  start_line: number
  end_line: number
  metadata: Record<string, unknown>
}

export interface ExplanationResult {
  id: string
  text: string | null
  cached: boolean
}

export interface ParsedExplanation {
  summary?: string
  purpose?: string
  howItWorks?: string
  notable?: string
  raw: string
}

export interface FileContent {
  file: string      // relative path
  content: string   // raw UTF-8 source text
  language: string  // e.g. 'python'
}

export interface Recommendation {
  id: string
  title: string
  level: 'Easy' | 'Medium' | 'Hard' | string
  description: string
  file: string
  files: string[]
  rationale?: string
  risks?: string[]
}

export interface PatchHunk {
  hunk_header: string
  explanation: string
  affected_lines_old: number[]
  affected_lines_new: number[]
}

export interface PatchResult {
  recommendation_id: string
  files: string[]
  diff_text: string
  explained_diff_text: string
  hunks: PatchHunk[]
  file_patches: Array<{ path: string, old: string, new: string }>
}
