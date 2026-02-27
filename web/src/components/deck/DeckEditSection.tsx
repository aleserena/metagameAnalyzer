import { useEffect, useMemo, useState } from 'react'
import { useBlocker } from 'react-router-dom'
import toast from 'react-hot-toast'
import { updateDeck, getCardLookup, importDeckFromMoxfield } from '../../api'
import { parseMoxfieldDeckList, formatMoxfieldDeckList } from '../../lib/deckListParser'
import { useAuth } from '../../contexts/AuthContext'
import type { Deck } from '../../types'
import CardSearchInput from '../CardSearchInput'
import Modal from '../Modal'
import { getEDHArchetype } from '../../lib/deckUtils'
import { reportError } from '../../utils'

export interface DeckEditSectionProps {
  deck: Deck | null
  onUpdate: (d: Deck) => void
  onCardsSaved?: () => void
}

export default function DeckEditSection({ deck, onUpdate, onCardsSaved }: DeckEditSectionProps) {
  const { user } = useAuth()
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [player, setPlayer] = useState('')
  const [rank, setRank] = useState('')
  const [archetype, setArchetype] = useState('')
  const [deckListText, setDeckListText] = useState('')
  const [saving, setSaving] = useState(false)
  const [invalidCards, setInvalidCards] = useState<string[] | null>(null)
  const [importingMoxfield, setImportingMoxfield] = useState(false)
  const [moxfieldUrl, setMoxfieldUrl] = useState('')
  const [commander1, setCommander1] = useState('')
  const [commander2, setCommander2] = useState('')

  const isEDH = (deck?.format_id || '').toUpperCase() === 'EDH' || (deck?.format_id || '').toLowerCase() === 'cedh'

  const originalDeckListText = useMemo(
    () => (deck ? formatMoxfieldDeckList(deck.commanders || [], deck.mainboard || [], deck.sideboard || []) : ''),
    [deck]
  )

  const hasUnsavedEdits = useMemo(() => {
    if (!editing || !deck) return false
    return (
      name !== (deck.name || '') ||
      player !== (deck.player || '') ||
      rank !== (deck.rank || '') ||
      archetype !== (deck.archetype || '') ||
      commander1 !== (deck.commanders?.[0] ?? '') ||
      commander2 !== (deck.commanders?.[1] ?? '') ||
      deckListText !== originalDeckListText
    )
  }, [editing, deck, name, player, rank, archetype, commander1, commander2, deckListText, originalDeckListText])

  const blocker = useBlocker(hasUnsavedEdits)

  useEffect(() => {
    if (!hasUnsavedEdits) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [hasUnsavedEdits])

  useEffect(() => {
    if (deck) {
      setName(deck.name || '')
      setPlayer(deck.player || '')
      setRank(deck.rank || '')
      setArchetype(deck.archetype || '')
      setDeckListText(formatMoxfieldDeckList(deck.commanders || [], deck.mainboard || [], deck.sideboard || []))
      const cmd = deck.commanders || []
      setCommander1(cmd[0] ?? '')
      setCommander2(cmd[1] ?? '')
    }
  }, [deck])

  if (user !== 'admin' || !deck) return null

  const startEdit = () => {
    setDeckListText(formatMoxfieldDeckList(deck.commanders || [], deck.mainboard || [], deck.sideboard || []))
    setCommander1(deck?.commanders?.[0] ?? '')
    setCommander2(deck?.commanders?.[1] ?? '')
    setInvalidCards(null)
    setMoxfieldUrl('')
    setEditing(true)
  }

  const applyCommandersToDeckList = (c1: string, c2: string) => {
    const parsed = parseMoxfieldDeckList(deckListText)
    const commanders = [c1, c2].filter(Boolean)
    setDeckListText(formatMoxfieldDeckList(commanders, parsed.mainboard, parsed.sideboard))
  }

  const handleImportMoxfield = () => {
    const url = moxfieldUrl.trim() || window.prompt('Paste Moxfield deck URL (e.g. https://www.moxfield.com/decks/...)')
    if (!url?.trim()) return
    setImportingMoxfield(true)
    importDeckFromMoxfield(url.trim())
      .then((res) => {
        setDeckListText(
          formatMoxfieldDeckList(res.commanders || [], res.mainboard || [], res.sideboard || [])
        )
        const importedEDH =
          (deck?.format_id || '').toLowerCase() === 'edh' ||
          (deck?.format_id || '').toLowerCase() === 'cedh' ||
          (res.format || '').toLowerCase() === 'commander' ||
          (res.format || '').toLowerCase() === 'edh'
        if (importedEDH && res.commanders?.length) {
          setCommander1(res.commanders[0] ?? '')
          setCommander2(res.commanders[1] ?? '')
        }
        if (!importedEDH && res.commanders?.length && !archetype.trim()) {
          setArchetype(res.commanders.join(', '))
        }
        if (res.name?.trim()) setName(res.name.trim())
        setMoxfieldUrl('')
        toast.success('Deck imported from Moxfield')
      })
      .catch((e) => toast.error(e?.message || 'Import failed'))
      .finally(() => setImportingMoxfield(false))
  }

  const save = async () => {
    const { commanders: commanderCards, mainboard, sideboard } = parseMoxfieldDeckList(deckListText)
    const commanders = commanderCards.flatMap((c) =>
      Array.from({ length: Math.max(1, c.qty) }, () => (c.card || '').trim())
    ).filter(Boolean)
    const uniqueNames = [
      ...new Set([
        ...commanders,
        ...mainboard.map((c) => c.card),
        ...sideboard.map((c) => c.card),
      ]),
    ].filter((n) => (n || '').trim())
    if (uniqueNames.length === 0) {
      setSaving(true)
      let effectiveArchetype: string | undefined = isEDH ? getEDHArchetype(commanders, null) : (archetype?.trim() || undefined)
      if (isEDH && commanders.length >= 2) {
        try {
          const lookup = await getCardLookup(commanders)
          effectiveArchetype = getEDHArchetype(commanders, lookup) ?? commanders.join(', ')
        } catch {
          effectiveArchetype = commanders.join(', ')
        }
      }
      const archetypeToSave = effectiveArchetype
      updateDeck(deck.deck_id, {
        name: name || undefined,
        player: player || undefined,
        rank: rank || undefined,
        archetype: archetypeToSave,
        commanders,
        mainboard,
        sideboard,
      })
        .then(() => {
          onUpdate({
            ...deck,
            name: name || deck.name,
            player: player || deck.player,
            rank: rank || deck.rank,
            archetype: archetypeToSave ?? deck.archetype ?? null,
            commanders,
            mainboard,
            sideboard,
          })
          setEditing(false)
          setInvalidCards(null)
          toast.success('Deck updated')
          onCardsSaved?.()
        })
        .catch((e) => toast.error(reportError(e)))
        .finally(() => setSaving(false))
      return
    }
    setSaving(true)
    setInvalidCards(null)
    try {
      const lookup = await getCardLookup(uniqueNames)
      const invalid = uniqueNames.filter((n) => !lookup[n] || (lookup[n] as { error?: string }).error)
      if (invalid.length > 0) {
        setInvalidCards(invalid)
        toast.error(`${invalid.length} card(s) not found. Please correct or remove them.`)
        setSaving(false)
        return
      }
      const effectiveArchetype = isEDH
        ? getEDHArchetype(commanders, lookup)
        : (archetype?.trim() || undefined)
      await updateDeck(deck.deck_id, {
        name: name || undefined,
        player: player || undefined,
        rank: rank || undefined,
        archetype: effectiveArchetype,
        commanders,
        mainboard,
        sideboard,
      })
      onUpdate({
        ...deck,
        name: name || deck.name,
        player: player || deck.player,
        rank: rank || deck.rank,
        archetype: effectiveArchetype ?? deck.archetype ?? null,
        commanders,
        mainboard,
        sideboard,
      })
      setEditing(false)
      setInvalidCards(null)
      toast.success('Deck updated')
      onCardsSaved?.()
    } catch (e) {
      toast.error(reportError(e))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="card" style={{ marginBottom: '1.5rem' }}>
      <h3 style={{ margin: '0 0 0.75rem' }}>Edit deck</h3>
      {editing ? (
        <>
          <div className="form-group">
            <label>Format (from event)</label>
            <div style={{ fontSize: '0.95rem', color: 'var(--text-muted)' }}>{deck.format_id || '—'}</div>
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
            <div className="form-group" style={{ marginBottom: 0, minWidth: 200 }}>
              <label htmlFor="deck-edit-name">Deck name</label>
              <input id="deck-edit-name" type="text" value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="form-group" style={{ marginBottom: 0, minWidth: 140 }}>
              <label htmlFor="deck-edit-player">Player</label>
              <input id="deck-edit-player" type="text" value={player} onChange={(e) => setPlayer(e.target.value)} />
            </div>
            <div className="form-group" style={{ marginBottom: 0, width: 80 }}>
              <label htmlFor="deck-edit-rank">Rank</label>
              <input id="deck-edit-rank" type="text" value={rank} onChange={(e) => setRank(e.target.value)} placeholder="1, 2, 3-4, 5-8, 9-16, 17-32, 33-64, 65-128, …" />
            </div>
            {isEDH && (
              <>
                <div className="form-group" style={{ marginBottom: 0, minWidth: 200 }}>
                  <label htmlFor="deck-edit-commander1">Commander 1</label>
                  <CardSearchInput
                    id="deck-edit-commander1"
                    value={commander1}
                    onChange={(name) => {
                      setCommander1(name)
                      applyCommandersToDeckList(name, commander2)
                    }}
                    placeholder="Search commander..."
                    aria-label="Commander 1"
                  />
                </div>
                <div className="form-group" style={{ marginBottom: 0, minWidth: 200 }}>
                  <label htmlFor="deck-edit-commander2">Commander 2</label>
                  <CardSearchInput
                    id="deck-edit-commander2"
                    value={commander2}
                    onChange={(name) => {
                      setCommander2(name)
                      applyCommandersToDeckList(commander1, name)
                    }}
                    placeholder="Partner / Background (optional)"
                    aria-label="Commander 2"
                  />
                </div>
              </>
            )}
            {!isEDH && (
              <div className="form-group" style={{ marginBottom: 0, minWidth: 140 }}>
                <label htmlFor="deck-edit-archetype">Archetype</label>
                <input
                  id="deck-edit-archetype"
                  type="text"
                  value={archetype}
                  onChange={(e) => setArchetype(e.target.value)}
                />
              </div>
            )}
          </div>
          <div className="form-group" style={{ marginBottom: '1rem' }}>
            <label htmlFor="deck-edit-moxfield">Import from Moxfield</label>
            <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', flexWrap: 'wrap' }}>
              <input
                id="deck-edit-moxfield"
                type="url"
                value={moxfieldUrl}
                onChange={(e) => setMoxfieldUrl(e.target.value)}
                placeholder="https://www.moxfield.com/decks/..."
                style={{ flex: 1, minWidth: 200, maxWidth: 400 }}
              />
              <button type="button" className="btn" onClick={handleImportMoxfield} disabled={importingMoxfield}>
                {importingMoxfield ? 'Importing…' : 'Import'}
              </button>
            </div>
          </div>
          <div className="form-group">
            <label htmlFor="deck-edit-list">Deck list (Moxfield format)</label>
            <textarea
              id="deck-edit-list"
              value={deckListText}
              onChange={(e) => {
                setDeckListText(e.target.value)
                if (invalidCards?.length) setInvalidCards(null)
              }}
              onBlur={() => {
                if (isEDH) {
                  const { commanders: cmdCards } = parseMoxfieldDeckList(deckListText)
                  const names = cmdCards.map((c) => c.card).filter(Boolean)
                  setCommander1(names[0] ?? '')
                  setCommander2(names[1] ?? '')
                }
              }}
              placeholder={'Commander\n1 Atraxa\n\nMainboard\n1 Sol Ring\nLightning Bolt\n4 Counterspell\n\nSideboard\n2 Negate'}
              rows={14}
              style={{ maxWidth: 'none' }}
            />
            <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: '0.25rem', display: 'block' }}>
              Use &quot;Commander&quot;, &quot;Mainboard&quot;, &quot;Sideboard&quot; to separate sections (these words are not cards). One card per line: &quot;QTY Card Name&quot; or &quot;QTYx Card Name&quot;; missing number = 1.
            </span>
          </div>
          {invalidCards != null && invalidCards.length > 0 && (
            <div
              className="error"
              style={{ marginBottom: '1rem' }}
              role="alert"
            >
              <strong>Cards not found:</strong> {invalidCards.join(', ')}. Please correct or remove them before saving.
            </div>
          )}
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button type="button" className="btn btn-primary" onClick={save} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button type="button" className="btn" onClick={() => { setEditing(false); setInvalidCards(null) }}>Cancel</button>
          </div>
        </>
      ) : (
        <button type="button" className="btn" onClick={startEdit}>Edit deck</button>
      )}

      {blocker.state === 'blocked' && hasUnsavedEdits && (
        <Modal
          title="Unsaved changes"
          onClose={() => blocker.reset?.()}
          closeOnOverlayClick={false}
          size={400}
        >
          <p style={{ color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
            You have unsaved changes. Do you want to leave this page? Your changes will be lost.
          </p>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button type="button" className="btn btn-primary" onClick={() => blocker.proceed?.()}>
              Leave
            </button>
            <button type="button" className="btn" onClick={() => blocker.reset?.()}>
              Stay
            </button>
          </div>
        </Modal>
      )}
    </div>
  )
}
