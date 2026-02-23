import { useCallback, useEffect, useRef, useState } from 'react'
import { getCardSearch } from '../api'

const DEBOUNCE_MS = 300
const MIN_QUERY_LEN = 2

export interface CardSearchInputProps {
  value: string
  onChange: (cardName: string) => void
  placeholder?: string
  id?: string
  'aria-label'?: string
  disabled?: boolean
}

export default function CardSearchInput({
  value,
  onChange,
  placeholder = 'Search card...',
  id,
  'aria-label': ariaLabel,
  disabled = false,
}: CardSearchInputProps) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [options, setOptions] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [highlightedIndex, setHighlightedIndex] = useState(0)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const displayValue = open ? query : value

  const fetchOptions = useCallback(async (q: string) => {
    if (q.length < MIN_QUERY_LEN) {
      setOptions([])
      return
    }
    setLoading(true)
    try {
      const res = await getCardSearch(q)
      setOptions(res.data || [])
      setHighlightedIndex(0)
    } catch {
      setOptions([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (!open) return
    debounceRef.current = setTimeout(() => fetchOptions(query), DEBOUNCE_MS)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query, open, fetchOptions])

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    if (open) document.addEventListener('click', handler)
    return () => document.removeEventListener('click', handler)
  }, [open])

  useEffect(() => {
    if (!open || highlightedIndex < 0) return
    const el = listRef.current?.children[highlightedIndex] as HTMLElement | undefined
    el?.scrollIntoView({ block: 'nearest' })
  }, [open, highlightedIndex])

  const select = (cardName: string) => {
    onChange(cardName)
    setQuery('')
    setOpen(false)
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.value
    if (value) onChange('')
    setQuery(v)
    setOpen(true)
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!open) {
      if (e.key === 'ArrowDown' && query.length >= MIN_QUERY_LEN && options.length > 0) setOpen(true)
      if (e.key === 'Backspace' && value) {
        e.preventDefault()
        onChange('')
      }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIndex((i) => (i < options.length - 1 ? i + 1 : 0))
      return
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIndex((i) => (i > 0 ? i - 1 : options.length - 1))
      return
    }
    if (e.key === 'Enter') {
      e.preventDefault()
      const card = options[highlightedIndex]
      if (card) select(card)
      return
    }
    if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
    }
  }

  const showMinChars = query.length > 0 && query.length < MIN_QUERY_LEN
  const showEmpty = open && !loading && query.length >= MIN_QUERY_LEN && options.length === 0

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <input
        type="text"
        id={id}
        aria-label={ariaLabel}
        aria-expanded={open}
        aria-autocomplete="list"
        aria-controls={open ? `${id ?? 'card-search'}-listbox` : undefined}
        aria-activedescendant={
          open && options[highlightedIndex] ? `${id ?? 'card-search'}-opt-${highlightedIndex}` : undefined
        }
        role="combobox"
        value={displayValue}
        onChange={handleInputChange}
        onFocus={() => query.length >= MIN_QUERY_LEN && setOpen(true)}
        onKeyDown={handleKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        style={{
          width: '100%',
          minWidth: 140,
          padding: '0.4rem 1.6rem 0.4rem 0.5rem',
          boxSizing: 'border-box',
        }}
      />
      {value && (
        <button
          type="button"
          aria-label="Clear selection"
          onClick={() => {
            onChange('')
            setQuery('')
            setOpen(false)
          }}
          style={{
            position: 'absolute',
            right: 6,
            top: '50%',
            transform: 'translateY(-50%)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            padding: 0,
            fontSize: '1rem',
            lineHeight: 1,
            color: 'var(--text-muted)',
          }}
        >
          ×
        </button>
      )}
      {open && (
        <ul
          id={`${id ?? 'card-search'}-listbox`}
          ref={listRef}
          role="listbox"
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: '100%',
            margin: 0,
            marginTop: 2,
            padding: 0,
            listStyle: 'none',
            maxHeight: 240,
            overflowY: 'auto',
            background: 'var(--bg)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            zIndex: 1000,
          }}
        >
          {loading && (
            <li style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Searching…
            </li>
          )}
          {showMinChars && !loading && (
            <li style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              Type at least {MIN_QUERY_LEN} characters
            </li>
          )}
          {showEmpty && !loading && (
            <li style={{ padding: '0.5rem 0.75rem', color: 'var(--text-muted)', fontSize: '0.9rem' }}>
              No cards found
            </li>
          )}
          {!loading &&
            options.map((name, i) => (
              <li
                key={name}
                id={`${id ?? 'card-search'}-opt-${i}`}
                role="option"
                aria-selected={i === highlightedIndex}
                onMouseEnter={() => setHighlightedIndex(i)}
                onClick={() => select(name)}
                style={{
                  padding: '0.4rem 0.75rem',
                  cursor: 'pointer',
                  background: i === highlightedIndex ? 'var(--accent-subtle, rgba(0,120,200,0.15))' : 'transparent',
                }}
              >
                {name}
              </li>
            ))}
        </ul>
      )}
    </div>
  )
}
