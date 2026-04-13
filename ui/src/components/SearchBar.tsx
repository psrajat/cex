import { useRef, useState } from 'react'

interface Props {
  onSearch: (query: string) => void
  onClear: () => void
}

export default function SearchBar({ onSearch, onClear }: Props) {
  const [value, setValue] = useState('')
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const q = e.target.value
    setValue(q)

    // Debounce — wait 350 ms after the user stops typing before searching.
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (q.trim()) {
      debounceRef.current = setTimeout(() => onSearch(q.trim()), 350)
    } else {
      onClear()
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === 'Escape') {
      setValue('')
      onClear()
    } else if (e.key === 'Enter') {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      if (value.trim()) onSearch(value.trim())
    }
  }

  return (
    <div style={{ position: 'relative' }}>
      {/* Search icon */}
      <svg
        width="13" height="13" viewBox="0 0 16 16"
        fill="none"
        style={{
          position: 'absolute',
          left: 10,
          top: '50%',
          transform: 'translateY(-50%)',
          color: 'var(--text-muted)',
          pointerEvents: 'none',
        }}
      >
        <circle cx="6.5" cy="6.5" r="4.5" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 10l3.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </svg>

      <input
        className="search-input"
        type="text"
        placeholder="Search symbols… (semantic + keyword)"
        value={value}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        spellCheck={false}
        autoComplete="off"
      />

      {/* Clear button */}
      {value && (
        <button
          onClick={() => { setValue(''); onClear() }}
          style={{
            position: 'absolute',
            right: 8,
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'none',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer',
            padding: 2,
            lineHeight: 1,
            fontSize: 14,
          }}
          title="Clear search"
        >
          ✕
        </button>
      )}
    </div>
  )
}
