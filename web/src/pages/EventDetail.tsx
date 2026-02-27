import { useState, useEffect, useRef, useMemo } from 'react'
import { useParams, Link, useNavigate, useBlocker, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { getEvent, getDecks, updateEvent, addDeckToEvent, deleteEvent, createEventEditLink, getEventEditLinkInfo, updateDeck, deleteDeck, setEventEditToken, clearEventEditToken, sendMissingDeckLinks, sendFeedbackLinks, sendFeedbackLinkToPlayer, getMatchupDiscrepancies, patchMatchup, getDeckMatchups, updateDeckMatchups } from '../api'
import type { EventWithOrigin } from '../api'
import type { Deck } from '../types'
import { useAuth } from '../contexts/AuthContext'
import { useFetch } from '../hooks/useFetch'
import PageError from '../components/PageError'
import PageSkeleton from '../components/PageSkeleton'
import CardSearchInput from '../components/CardSearchInput'
import { parseMoxfieldDeckList } from '../lib/deckListParser'
import { reportError, ddMmYyToIso, isoToDdMmYy } from '../utils'

/** Coerce value for display; avoid [object Object]. */
function cellStr(v: unknown): string {
  if (v == null) return '—'
  if (typeof v === 'object') return '—'
  return String(v)
}

type EventDetailData = { event: EventWithOrigin & { player_count?: number }; decks: Deck[] }

type BulkDeckEdit = { name: string; player: string; rank: string; archetype: string }

function defaultDeckEdit(d: Deck): BulkDeckEdit {
  return {
    name: d.name ?? '',
    player: d.player ?? '',
    rank: d.rank ?? '',
    archetype: d.archetype ?? (d.commanders?.length ? d.commanders[0] ?? '' : ''),
  }
}

export default function EventDetail() {
  const { eventId } = useParams<{ eventId: string }>()
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()
  const { user } = useAuth()
  const urlToken = searchParams.get('token')
  const [eventEditMode, setEventEditMode] = useState(false)
  const [eventEditTokenError, setEventEditTokenError] = useState<string | null>(null)
  const eventEditValidatedRef = useRef(false)
  const { data, loading, error, refetch } = useFetch<EventDetailData>(
    () =>
      eventId
        ? Promise.all([getEvent(eventId), getDecks({ event_id: eventId, limit: 500 })]).then(([ev, decksRes]) => ({
            event: ev,
            decks: decksRes.decks,
          }))
        : Promise.reject(new Error('Missing event ID')),
    [eventId ?? '']
  )
  const event = data?.event ?? null
  const decks = data?.decks ?? []
  const [editing, setEditing] = useState(false)
  const [editName, setEditName] = useState('')
  const [editStore, setEditStore] = useState('')
  const [editLocation, setEditLocation] = useState('')
  const [editDate, setEditDate] = useState('')
  const [editFormatId, setEditFormatId] = useState('')
  const [editPlayerCount, setEditPlayerCount] = useState(0)
  const [saving, setSaving] = useState(false)
  const [addDecksCount, setAddDecksCount] = useState(1)
  const [addingDecks, setAddingDecks] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [editingDeckId, setEditingDeckId] = useState<number | null>(null)
  const [editDeckName, setEditDeckName] = useState('')
  const [editDeckPlayer, setEditDeckPlayer] = useState('')
  const [editDeckRank, setEditDeckRank] = useState('')
  const [editDeckArchetype, setEditDeckArchetype] = useState('')
  const [savingDeck, setSavingDeck] = useState(false)
  const [deletingDeckId, setDeletingDeckId] = useState<number | null>(null)
  const [bulkDeckEdits, setBulkDeckEdits] = useState<Record<number, BulkDeckEdit>>({})
  const [generatingEventEditLink, setGeneratingEventEditLink] = useState(false)
  const [generatedEventEditLink, setGeneratedEventEditLink] = useState<{ url: string } | null>(null)
  const [uploadDeckForDeckId, setUploadDeckForDeckId] = useState<number | null>(null)
  const [uploadDeckListText, setUploadDeckListText] = useState('')
  const [uploadingDeck, setUploadingDeck] = useState(false)
  const [confirmDeleteEvent, setConfirmDeleteEvent] = useState(false)
  const [confirmDeleteDeckId, setConfirmDeleteDeckId] = useState<number | null>(null)
  const [sendingMissingLinks, setSendingMissingLinks] = useState(false)
  const [sendingFeedbackLinks, setSendingFeedbackLinks] = useState(false)
  const [sendingFeedbackLinkForPlayer, setSendingFeedbackLinkForPlayer] = useState<string | null>(null)
  const [discrepancies, setDiscrepancies] = useState<Awaited<ReturnType<typeof getMatchupDiscrepancies>>['discrepancies'] | null>(null)
  const [loadingDiscrepancies, setLoadingDiscrepancies] = useState(false)
  const [fixingPairKey, setFixingPairKey] = useState<string | null>(null)
  const [matchupsDeckId, setMatchupsDeckId] = useState<number | null>(null)
  const [matchupsList, setMatchupsList] = useState<Array<{ opponent_player: string; result: string; intentional_draw: boolean }>>([])
  const [loadingMatchups, setLoadingMatchups] = useState(false)
  const [savingMatchups, setSavingMatchups] = useState(false)

  const canEditEvent = user === 'admin' || eventEditMode
  const canDeleteEvent = user === 'admin'
  const showUploadLinksSection = user === 'admin'

  useEffect(() => {
    if (!urlToken || !eventId || eventEditValidatedRef.current) return
    eventEditValidatedRef.current = true
    getEventEditLinkInfo(urlToken)
      .then((data) => {
        if (data.event_id === eventId) {
          setEventEditToken(urlToken)
          setEventEditMode(true)
          setEventEditTokenError(null)
        } else {
          setEventEditTokenError('This link is for a different event.')
        }
      })
      .catch(() => {
        toast.error('Link invalid or already used.')
        navigate('/', { replace: true })
      })
  }, [urlToken, eventId, navigate])

  const isUpdateModalOpen = editingDeckId != null
  const isUploadDeckModalOpen = uploadDeckForDeckId != null
  const isConfirmModalOpen = confirmDeleteEvent || confirmDeleteDeckId != null

  const eventEditDirty = useMemo(() => {
    if (!editing || !event) return false
    if (
      editName !== (event.event_name || '') ||
      editStore !== (event.store ?? '') ||
      editLocation !== (event.location ?? '') ||
      editDate !== (event.date || '') ||
      editFormatId !== (event.format_id || '') ||
      editPlayerCount !== (event.player_count ?? 0)
    ) return true
    return decks.some((d) => {
      const current = bulkDeckEdits[d.deck_id] ?? defaultDeckEdit(d)
      const def = defaultDeckEdit(d)
      return current.name !== def.name || current.player !== def.player || current.rank !== def.rank || current.archetype !== def.archetype
    })
  }, [editing, event, editName, editStore, editLocation, editDate, editFormatId, editPlayerCount, decks, bulkDeckEdits])

  const deckBeingEdited = editingDeckId != null ? decks.find((d) => d.deck_id === editingDeckId) : null
  const deckModalDirty = useMemo(() => {
    if (!deckBeingEdited || editingDeckId == null) return false
    const d = deckBeingEdited
    return (
      editDeckName !== (d.name ?? '') ||
      editDeckPlayer !== (d.player ?? '') ||
      editDeckRank !== (d.rank ?? '') ||
      editDeckArchetype !== (d.archetype ?? (d.commanders?.length ? d.commanders[0] ?? '' : ''))
    )
  }, [deckBeingEdited, editingDeckId, editDeckName, editDeckPlayer, editDeckRank, editDeckArchetype])

  const hasUnsavedEdits = eventEditDirty || deckModalDirty
  const blocker = useBlocker(hasUnsavedEdits || isUpdateModalOpen || isUploadDeckModalOpen || isConfirmModalOpen)

  useEffect(() => {
    if (!isUpdateModalOpen && !isUploadDeckModalOpen && !isConfirmModalOpen) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [isUpdateModalOpen, isUploadDeckModalOpen, isConfirmModalOpen])

  useEffect(() => {
    if (!hasUnsavedEdits) return
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault()
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [hasUnsavedEdits])

  useEffect(() => {
    if (!isUpdateModalOpen && !isUploadDeckModalOpen && !isConfirmModalOpen) return
    const prevOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.body.style.overflow = prevOverflow
    }
  }, [isUpdateModalOpen, isUploadDeckModalOpen, isConfirmModalOpen])

  const getDeckEdit = (d: Deck): BulkDeckEdit => bulkDeckEdits[d.deck_id] ?? defaultDeckEdit(d)

  const setDeckEditField = (deckId: number, field: keyof BulkDeckEdit, value: string, fallback: BulkDeckEdit) => {
    setBulkDeckEdits((prev) => ({
      ...prev,
      [deckId]: { ...(prev[deckId] ?? fallback), [field]: value },
    }))
  }

  const startEdit = () => {
    if (event) {
      setEditName(event.event_name || '')
      setEditStore(event.store ?? '')
      setEditLocation(event.location ?? '')
      setEditDate(event.date || '')
      setEditFormatId(event.format_id || '')
      setEditPlayerCount(event.player_count ?? 0)
      setEditing(true)
    }
  }

  const cancelEdit = () => {
    setEditing(false)
    setBulkDeckEdits({})
  }

  const saveEdit = () => {
    if (!eventId) return
    setSaving(true)
    updateEvent(eventId, {
      event_name: editName,
      date: editDate,
      format_id: editFormatId,
      player_count: editPlayerCount,
      store: editStore,
      location: editLocation,
    })
      .then(() => {
        if (decks.length === 0) return Promise.resolve() as Promise<void>
        const deckPromises = decks.map((d) => {
          const edit = getDeckEdit(d)
          const payload: Parameters<typeof updateDeck>[1] = {
            name: edit.name.trim() || undefined,
            player: edit.player.trim() || undefined,
            rank: edit.rank.trim() || undefined,
            archetype: edit.archetype.trim() || undefined,
          }
          if (isEDH && edit.archetype.trim()) {
            payload.commanders = [edit.archetype.trim()]
          }
          return updateDeck(d.deck_id, payload)
        })
        return Promise.all(deckPromises).then((): void => undefined)
      })
      .then(() => {
        refetch()
        setEditing(false)
        setBulkDeckEdits({})
        toast.success(decks.length > 0 ? `Event and ${decks.length} deck${decks.length !== 1 ? 's' : ''} updated` : 'Event updated')
        if (eventEditMode) {
          clearEventEditToken()
          setEventEditMode(false)
          navigate(`/events/${eventId}`, { replace: true })
        }
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setSaving(false))
  }

  const maxDecks = typeof event?.player_count === 'number' && event.player_count > 0 ? event.player_count : Infinity
  const atDeckLimit = decks.length >= maxDecks
  const slotsLeft = Math.max(0, maxDecks - decks.length)

  const handleAddDecks = () => {
    if (!eventId || atDeckLimit) return
    const count = Math.max(1, Math.min(slotsLeft, addDecksCount))
    setAddingDecks(true)
    const addOne = (): Promise<unknown> => addDeckToEvent(eventId)
    const chain = Array.from({ length: count }, () => addOne).reduce<Promise<void>>(
      (acc, fn) => acc.then(() => fn()).then(() => undefined),
      Promise.resolve()
    )
    chain
      .then(() => {
        refetch()
        toast.success(`Added ${count} deck${count !== 1 ? 's' : ''}`)
      })
      .catch((e: unknown) => toast.error(reportError(e)))
      .finally(() => setAddingDecks(false))
  }

  const handleDeleteClick = () => {
    if (eventId) setConfirmDeleteEvent(true)
  }
  const handleDeleteConfirm = () => {
    if (!eventId) return
    setConfirmDeleteEvent(false)
    setDeleting(true)
    deleteEvent(eventId)
      .then(() => {
        toast.success('Event deleted')
        navigate('/events')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setDeleting(false))
  }

  const copyLink = (url: string) => {
    window.navigator.clipboard.writeText(url).then(
      () => toast.success('Copied to clipboard'),
      () => { /* ignore */ }
    )
  }

  const openUpdateDeck = (deck: Deck) => {
    setEditingDeckId(deck.deck_id)
    setEditDeckName(deck.name ?? '')
    setEditDeckPlayer(deck.player ?? '')
    setEditDeckRank(deck.rank ?? '')
    setEditDeckArchetype(deck.archetype ?? (deck.commanders?.length ? deck.commanders[0] ?? '' : ''))
  }

  const closeUpdateDeck = () => {
    setEditingDeckId(null)
    setEditDeckName('')
    setEditDeckPlayer('')
    setEditDeckRank('')
    setEditDeckArchetype('')
  }

  const saveDeckUpdate = () => {
    if (editingDeckId == null) return
    const isEDH = (event?.format_id ?? '').toLowerCase() === 'edh' || (event?.format_id ?? '').toLowerCase() === 'commander'
    setSavingDeck(true)
    const payload: Parameters<typeof updateDeck>[1] = {
      name: editDeckName.trim() || undefined,
      player: editDeckPlayer.trim() || undefined,
      rank: editDeckRank.trim() || undefined,
      archetype: editDeckArchetype.trim() || undefined,
    }
    if (isEDH && editDeckArchetype.trim()) {
      payload.commanders = [editDeckArchetype.trim()]
    }
    updateDeck(editingDeckId, payload)
      .then(() => {
        refetch()
        closeUpdateDeck()
        toast.success('Deck updated')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setSavingDeck(false))
  }

  const isEDH = (event?.format_id ?? '').toLowerCase() === 'edh' || (event?.format_id ?? '').toLowerCase() === 'commander'

  const openUploadDeckModal = (deckId: number) => {
    setUploadDeckForDeckId(deckId)
    setUploadDeckListText('')
  }
  const closeUploadDeckModal = () => {
    setUploadDeckForDeckId(null)
    setUploadDeckListText('')
  }

  const handleUploadDeckSubmit = () => {
    if (uploadDeckForDeckId == null) return
    const parsed = parseMoxfieldDeckList(uploadDeckListText)
    const mainboard = parsed.mainboard.filter((c) => c.card.trim())
    if (mainboard.length === 0) {
      toast.error('Deck list must contain at least one mainboard card.')
      return
    }
    const commanders = parsed.commanders.map((c) => c.card.trim()).filter(Boolean)
    const sideboard = parsed.sideboard.filter((c) => c.card.trim())
    setUploadingDeck(true)
    updateDeck(uploadDeckForDeckId, {
      mainboard,
      sideboard,
      commanders: commanders.length > 0 ? commanders : undefined,
    })
      .then(() => {
        refetch()
        closeUploadDeckModal()
        toast.success('Deck updated')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setUploadingDeck(false))
  }

  const MATCHUP_RESULT_OPTIONS = [
    { value: 'win', label: 'You win' },
    { value: 'loss', label: 'You lose' },
    { value: 'draw', label: 'Draw' },
    { value: 'intentional_draw', label: 'Intentional draw' },
    { value: 'intentional_draw_win', label: 'Intentional draw (you win)' },
    { value: 'intentional_draw_loss', label: 'Intentional draw (you lose)' },
  ] as const

  const openUpdateMatchupsModal = (deckId: number) => {
    setMatchupsDeckId(deckId)
    setMatchupsList([])
    setLoadingMatchups(true)
    getDeckMatchups(deckId)
      .then((res) => {
        const ourMatchups = (res.matchups || []).map((m) => {
          const raw = (m.result || '').trim().toLowerCase()
          let result: string = 'draw'
          if (raw === 'intentional_draw' || raw === 'intentional_draw_win' || raw === 'intentional_draw_loss') {
            result = raw
          } else if (raw) {
            if (raw === 'win' || raw === '2-1' || raw === '1-0' || raw === '2-0') result = 'win'
            else if (raw === 'loss' || raw === '1-2' || raw === '0-1' || raw === '0-2') result = 'loss'
            else if (raw === 'draw' || raw === '1-1' || raw === '0-0') result = 'draw'
          }
          return {
            opponent_player: (m.opponent_player ?? '').trim(),
            result,
            intentional_draw: ['intentional_draw', 'intentional_draw_win', 'intentional_draw_loss'].includes(raw),
          }
        })
        const reportedAgainstMe = (res.opponent_reported_matchups || []).map((m) => ({
          opponent_player: (m.opponent_player ?? '').trim(),
          result: (m.result || 'draw').toLowerCase(),
          intentional_draw: Boolean(m.intentional_draw),
        }))
        const byOpponent = new Map<string, { opponent_player: string; result: string; intentional_draw: boolean }>()
        for (const m of reportedAgainstMe) {
          if (m.opponent_player) byOpponent.set(m.opponent_player, m)
        }
        for (const m of ourMatchups) {
          if (m.opponent_player) byOpponent.set(m.opponent_player, m)
        }
        const merged = Array.from(byOpponent.values())
        setMatchupsList(merged.length > 0 ? merged : [{ opponent_player: '', result: 'draw', intentional_draw: false }])
      })
      .catch((e) => {
        toast.error(reportError(e))
        setMatchupsDeckId(null)
      })
      .finally(() => setLoadingMatchups(false))
  }

  const closeUpdateMatchupsModal = () => {
    setMatchupsDeckId(null)
    setMatchupsList([])
  }

  const addMatchupRow = () =>
    setMatchupsList((prev) =>
      prev.length >= 10 ? prev : [...prev, { opponent_player: '', result: 'draw', intentional_draw: false }]
    )
  const updateMatchupRow = (i: number, field: 'opponent_player' | 'result' | 'intentional_draw', value: string | boolean) =>
    setMatchupsList((prev) => prev.map((m, j) => (j === i ? { ...m, [field]: value } : m)))
  const removeMatchupRow = (i: number) => setMatchupsList((prev) => prev.filter((_, j) => j !== i))

  const handleSaveMatchups = () => {
    if (matchupsDeckId == null) return
    const payload = {
      matchups: matchupsList
        .filter((m) => (m.opponent_player || '').trim())
        .map((m) => ({
          opponent_player: m.opponent_player.trim(),
          result: m.result || 'draw',
        })),
    }
    setSavingMatchups(true)
    updateDeckMatchups(matchupsDeckId, payload)
      .then(() => {
        refetch()
        closeUpdateMatchupsModal()
        toast.success('Matchups updated')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setSavingMatchups(false))
  }

  useEffect(() => {
    if (matchupsDeckId != null) {
      const prev = document.body.style.overflow
      document.body.style.overflow = 'hidden'
      return () => {
        document.body.style.overflow = prev
      }
    }
  }, [matchupsDeckId])

  const matchupsOpponentOptions = useMemo(() => {
    if (matchupsDeckId == null) return []
    return [...new Set(decks.filter((d) => d.deck_id !== matchupsDeckId).map((d) => (d.player || '').trim()).filter(Boolean))]
  }, [matchupsDeckId, decks])

  const missingDecksCount = decks.filter((d) => !(d.mainboard && d.mainboard.length)).length
  const handleSendMissingDeckLinks = () => {
    if (!eventId) return
    setSendingMissingLinks(true)
    sendMissingDeckLinks(eventId)
      .then((res) => {
        refetch()
        toast.success(`Sent ${res.sent} email(s).${res.failed?.length ? ` Failed: ${res.failed.length}` : ''}`)
      })
      .catch((e) => {
        if (String(e?.message || e).includes('503') || String(e?.message || e).toLowerCase().includes('not configured')) {
          toast.error('Email not configured. Set Brevo SMTP or BREVO_API_KEY in .env.')
        } else {
          toast.error(reportError(e))
        }
      })
      .finally(() => setSendingMissingLinks(false))
  }
  const handleSendFeedbackLinks = () => {
    if (!eventId) return
    setSendingFeedbackLinks(true)
    sendFeedbackLinks(eventId)
      .then((res) => {
        refetch()
        toast.success(`Sent ${res.sent} email(s).`)
      })
      .catch((e) => {
        if (String(e?.message || e).includes('503') || String(e?.message || e).toLowerCase().includes('not configured')) {
          toast.error('Email not configured. Set Brevo SMTP or BREVO_API_KEY in .env.')
        } else {
          toast.error(reportError(e))
        }
      })
      .finally(() => setSendingFeedbackLinks(false))
  }

  const handleSendFeedbackLinkToPlayer = (player: string) => {
    if (!eventId) return
    setSendingFeedbackLinkForPlayer(player)
    sendFeedbackLinkToPlayer(eventId, player)
      .then(() => {
        toast.success(`Feedback link sent to ${player}.`)
      })
      .catch((e) => {
        if (String(e?.message || e).includes('503') || String(e?.message || e).toLowerCase().includes('not configured')) {
          toast.error('Email not configured. Set Brevo SMTP or BREVO_API_KEY in .env.')
        } else if (String(e?.message || e).toLowerCase().includes('no email')) {
          toast.error(`No email set for ${player}. Set email on the player's page first.`)
        } else {
          toast.error(reportError(e))
        }
      })
      .finally(() => setSendingFeedbackLinkForPlayer(null))
  }

  const loadDiscrepancies = () => {
    if (!eventId) return
    setLoadingDiscrepancies(true)
    getMatchupDiscrepancies(eventId)
      .then((res) => setDiscrepancies(res.discrepancies))
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setLoadingDiscrepancies(false))
  }
  const pairKey = (d: { matchup_a: { id: number }; matchup_b: { id: number } }) => `${d.matchup_a.id}-${d.matchup_b.id}`
  const fixMatchupPair = (
    d: { matchup_a: { id: number }; matchup_b: { id: number } },
    resultA: string,
    resultB: string
  ) => {
    const key = pairKey(d)
    setFixingPairKey(key)
    Promise.all([
      patchMatchup(d.matchup_a.id, { result: resultA }),
      patchMatchup(d.matchup_b.id, { result: resultB }),
    ])
      .then(() => {
        loadDiscrepancies()
        toast.success('Matchup updated')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setFixingPairKey(null))
  }

  const handleDeleteDeckClick = (deckId: number) => setConfirmDeleteDeckId(deckId)
  const handleDeleteDeckConfirm = () => {
    if (confirmDeleteDeckId == null) return
    const deckId = confirmDeleteDeckId
    setConfirmDeleteDeckId(null)
    setDeletingDeckId(deckId)
    deleteDeck(deckId)
      .then(() => {
        refetch()
        toast.success('Deck deleted')
      })
      .catch((e) => toast.error(reportError(e)))
      .finally(() => setDeletingDeckId(null))
  }

  if (loading) return <PageSkeleton titleWidth={280} blocks={2} />
  if (error || !event) {
    return (
      <PageError
        title="Event"
        message={error || 'Event not found.'}
        onRetry={error ? () => refetch() : undefined}
        retryLabel="Try again"
        extraActions={<Link to="/events" className="btn">Back to events</Link>}
      />
    )
  }

  return (
    <>
      {eventEditMode && !eventEditTokenError && (
        <div style={{ marginBottom: '1rem', padding: '0.75rem 1rem', background: 'var(--accent)', color: '#fff', borderRadius: 8 }}>
          Editing via one-time link. You can edit the event and all decks.
        </div>
      )}
      <div className="page">
        {eventEditTokenError && (
          <div style={{ marginBottom: '1rem', padding: '0.75rem 1rem', background: 'var(--danger, #c00)', color: '#fff', borderRadius: 8 }}>
            {eventEditTokenError}
          </div>
        )}
        <button type="button" className="btn" style={{ marginBottom: '1rem' }} onClick={() => navigate(-1)}>
        Back
      </button>
      <h1 className="page-title">
        {[event.event_name, event.store, event.location].filter(Boolean).length >= 2
          ? `${event.event_name || 'Unnamed'}${event.store ? ` @ ${event.store}` : ''}${event.location ? ` (${event.location})` : ''}`
          : (typeof event.event_name === 'string' && event.event_name.trim()) ? event.event_name : 'Unnamed event'}
      </h1>

      <section className="card" style={{ marginBottom: '1.5rem' }}>
        {editing ? (
          <>
            <h2 style={{ marginTop: 0 }}>Edit event</h2>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '1rem', marginBottom: '1rem' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Name</span>
                <input type="text" value={editName} onChange={(e) => setEditName(e.target.value)} style={{ minWidth: 240 }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Store</span>
                <input type="text" value={editStore} onChange={(e) => setEditStore(e.target.value)} style={{ minWidth: 120 }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Location</span>
                <input type="text" value={editLocation} onChange={(e) => setEditLocation(e.target.value)} style={{ minWidth: 120 }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Date</span>
                <input
                  type="date"
                  value={ddMmYyToIso(editDate)}
                  onChange={(e) => setEditDate(isoToDdMmYy(e.target.value))}
                  style={{ width: 140 }}
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Format</span>
                <input type="text" value={editFormatId} onChange={(e) => setEditFormatId(e.target.value)} style={{ width: 80 }} />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Players</span>
                <input
                  type="number"
                  min={0}
                  value={editPlayerCount || ''}
                  onChange={(e) => setEditPlayerCount(parseInt(e.target.value, 10) || 0)}
                  style={{ width: 70 }}
                />
              </label>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn btn-primary" onClick={saveEdit} disabled={saving}>{saving ? 'Saving…' : 'Save'}</button>
              <button type="button" className="btn" onClick={cancelEdit}>Cancel</button>
            </div>
          </>
        ) : (
          <>
            <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '0.5rem 1.5rem', margin: 0 }}>
              <dt style={{ color: 'var(--text-muted)' }}>Date</dt>
              <dd style={{ margin: 0 }}>{cellStr(event.date)}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Format</dt>
              <dd style={{ margin: 0 }}>{cellStr(event.format_id)}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Players</dt>
              <dd style={{ margin: 0 }}>{typeof event.player_count === 'number' ? event.player_count : cellStr(event.player_count)}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Store</dt>
              <dd style={{ margin: 0 }}>{cellStr(event.store) || '—'}</dd>
              <dt style={{ color: 'var(--text-muted)' }}>Location</dt>
              <dd style={{ margin: 0 }}>{cellStr(event.location) || '—'}</dd>
            </dl>
            {(canEditEvent || canDeleteEvent) && (
              <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
                {canEditEvent && (
                  <>
                    <button type="button" className="btn" onClick={startEdit}>Edit event</button>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                      <input
                        type="number"
                        min={1}
                        max={Math.max(1, slotsLeft)}
                        value={addDecksCount}
                        onChange={(ev) => setAddDecksCount(Math.max(1, Math.min(slotsLeft, parseInt(ev.target.value, 10) || 1)))}
                        style={{ width: 52 }}
                        aria-label="Number of decks to add"
                        disabled={addingDecks || atDeckLimit}
                      />
                      <button
                        type="button"
                        className="btn"
                        onClick={handleAddDecks}
                        disabled={addingDecks || atDeckLimit}
                      >
                        {addingDecks ? 'Adding…' : `Add ${addDecksCount} deck${addDecksCount !== 1 ? 's' : ''}`}
                      </button>
                    </div>
                    {atDeckLimit && maxDecks !== Infinity && (
                      <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>Event is full ({decks.length}/{maxDecks} decks).</span>
                    )}
                  </>
                )}
                {canDeleteEvent && (
                  <button type="button" className="btn" style={{ color: 'var(--danger, #c00)' }} onClick={handleDeleteClick} disabled={deleting}>
                    Delete event
                  </button>
                )}
              </div>
            )}
          </>
        )}
      </section>

      {showUploadLinksSection && (
        <section className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ marginTop: 0 }}>Upload links</h2>
          <h3 style={{ marginTop: 0, marginBottom: '0.5rem' }}>Event edit link</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
            One-time link to this event page to add, update, and delete decks and edit event details. Cannot delete the event or generate new links.
          </p>
          <button
            type="button"
            className="btn"
            onClick={() => {
              if (!eventId) return
              setGeneratingEventEditLink(true)
              createEventEditLink(eventId)
                .then((res) => {
                  if (res.links.length > 0) {
                    const token = res.links[0].token
                    const base = typeof window !== 'undefined' ? window.location.origin : ''
                    const url = `${base}/events/${eventId}?token=${token}`
                    setGeneratedEventEditLink({ url })
                    window.navigator.clipboard.writeText(url).then(
                      () => toast.success('Event edit link copied to clipboard'),
                      () => toast.success('Event edit link generated')
                    )
                  }
                })
                .catch((e) => toast.error(reportError(e)))
                .finally(() => setGeneratingEventEditLink(false))
            }}
            disabled={generatingEventEditLink}
          >
            {generatingEventEditLink ? 'Generating…' : 'Generate event edit link'}
          </button>
          {generatedEventEditLink && (
            <p style={{ marginTop: '0.75rem', fontSize: '0.9rem' }}>
              <code style={{ wordBreak: 'break-all' }}>{generatedEventEditLink.url}</code>{' '}
              <button type="button" className="btn" style={{ flexShrink: 0 }} onClick={() => copyLink(generatedEventEditLink!.url)}>
                Copy
              </button>
            </p>
          )}
          <h3 style={{ marginTop: '1.5rem', marginBottom: '0.5rem' }}>Email links</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
            Send one-time links by email to players (using emails set on each player&apos;s page).
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
            <button
              type="button"
              className="btn"
              onClick={handleSendMissingDeckLinks}
              disabled={sendingMissingLinks || missingDecksCount === 0}
            >
              {sendingMissingLinks ? 'Sending…' : `Email missing deck links${missingDecksCount > 0 ? ` (${missingDecksCount} missing)` : ''}`}
            </button>
            <button
              type="button"
              className="btn"
              onClick={handleSendFeedbackLinks}
              disabled={sendingFeedbackLinks || decks.length === 0}
            >
              {sendingFeedbackLinks ? 'Sending…' : 'Email event feedback links'}
            </button>
          </div>
        </section>
      )}

      {showUploadLinksSection && (
        <section className="card" style={{ marginBottom: '1.5rem' }}>
          <h2 style={{ marginTop: 0 }}>Matchup discrepancies</h2>
          <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
            Pairs where both players reported the same match but results disagree (e.g. one win / one loss = consistent; both win = discrepancy).
          </p>
          <button type="button" className="btn" onClick={loadDiscrepancies} disabled={loadingDiscrepancies}>
            {loadingDiscrepancies ? 'Loading…' : 'View discrepancies'}
          </button>
          {discrepancies !== null && (
            <div style={{ marginTop: '1rem' }}>
              {discrepancies.length === 0 ? (
                <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>No discrepancies found.</p>
              ) : (
                <ul style={{ paddingLeft: '1.25rem' }}>
                  {discrepancies.map((d, i) => {
                    const key = pairKey(d)
                    const fixing = fixingPairKey === key
                    return (
                      <li key={i} style={{ marginBottom: '0.75rem' }}>
                        {d.player_a} vs {d.player_b}: reported &quot;{d.result_a}&quot; vs &quot;{d.result_b}&quot;.
                        {' '}
                        <button type="button" className="btn" style={{ fontSize: '0.875rem', padding: '0.2rem 0.4rem' }} onClick={() => fixMatchupPair(d, 'win', 'loss')} disabled={fixing}>{d.player_a} wins</button>
                        {' '}
                        <button type="button" className="btn" style={{ fontSize: '0.875rem', padding: '0.2rem 0.4rem' }} onClick={() => fixMatchupPair(d, 'loss', 'win')} disabled={fixing}>{d.player_b} wins</button>
                        {' '}
                        <button type="button" className="btn" style={{ fontSize: '0.875rem', padding: '0.2rem 0.4rem' }} onClick={() => fixMatchupPair(d, 'draw', 'draw')} disabled={fixing}>Draw</button>
                        {' '}
                        <button type="button" className="btn" style={{ fontSize: '0.875rem', padding: '0.2rem 0.4rem' }} onClick={() => fixMatchupPair(d, 'intentional_draw', 'intentional_draw')} disabled={fixing}>Intentional draw</button>
                        {' '}
                        <button type="button" className="btn" style={{ fontSize: '0.875rem', padding: '0.2rem 0.4rem' }} onClick={() => fixMatchupPair(d, 'intentional_draw_win', 'intentional_draw_loss')} disabled={fixing}>Intentional draw ({d.player_a} wins)</button>
                        {' '}
                        <button type="button" className="btn" style={{ fontSize: '0.875rem', padding: '0.2rem 0.4rem' }} onClick={() => fixMatchupPair(d, 'intentional_draw_loss', 'intentional_draw_win')} disabled={fixing}>Intentional draw ({d.player_b} wins)</button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </div>
          )}
          <h3 style={{ marginTop: '1.5rem', marginBottom: '0.5rem' }}>Event edit link</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
            One-time link to this event page to add, update, and delete decks and edit event details. Cannot delete the event or generate new links.
          </p>
          <button
            type="button"
            className="btn"
            onClick={() => {
              if (!eventId) return
              setGeneratingEventEditLink(true)
              createEventEditLink(eventId)
                .then((res) => {
                  if (res.links.length > 0) {
                    const token = res.links[0].token
                    const base = typeof window !== 'undefined' ? window.location.origin : ''
                    const url = `${base}/events/${eventId}?token=${token}`
                    setGeneratedEventEditLink({ url })
                    window.navigator.clipboard.writeText(url).then(
                      () => toast.success('Event edit link copied to clipboard'),
                      () => toast.success('Event edit link generated')
                    )
                  }
                })
                .catch((e) => toast.error(reportError(e)))
                .finally(() => setGeneratingEventEditLink(false))
            }}
            disabled={generatingEventEditLink}
          >
            {generatingEventEditLink ? 'Generating…' : 'Generate event edit link'}
          </button>
          {generatedEventEditLink && (
            <p style={{ marginTop: '0.75rem', fontSize: '0.9rem' }}>
              <code style={{ wordBreak: 'break-all' }}>{generatedEventEditLink.url}</code>{' '}
              <button type="button" className="btn" style={{ flexShrink: 0 }} onClick={() => copyLink(generatedEventEditLink!.url)}>
                Copy
              </button>
            </p>
          )}
          <h3 style={{ marginTop: '1.5rem', marginBottom: '0.5rem' }}>Event edit link</h3>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
            One-time link to this event page to add, update, and delete decks and edit event details. Cannot delete the event or generate new links.
          </p>
          <button
            type="button"
            className="btn"
            onClick={() => {
              if (!eventId) return
              setGeneratingEventEditLink(true)
              createEventEditLink(eventId)
                .then((res) => {
                  if (res.links.length > 0) {
                    const token = res.links[0].token
                    const base = typeof window !== 'undefined' ? window.location.origin : ''
                    const url = `${base}/events/${eventId}?token=${token}`
                    setGeneratedEventEditLink({ url })
                    window.navigator.clipboard.writeText(url).then(
                      () => toast.success('Event edit link copied to clipboard'),
                      () => toast.success('Event edit link generated')
                    )
                  }
                })
                .catch((e) => toast.error(reportError(e)))
                .finally(() => setGeneratingEventEditLink(false))
            }}
            disabled={generatingEventEditLink}
          >
            {generatingEventEditLink ? 'Generating…' : 'Generate event edit link'}
          </button>
          {generatedEventEditLink && (
            <p style={{ marginTop: '0.75rem', fontSize: '0.9rem' }}>
              <code style={{ wordBreak: 'break-all' }}>{generatedEventEditLink.url}</code>{' '}
              <button type="button" className="btn" style={{ flexShrink: 0 }} onClick={() => copyLink(generatedEventEditLink!.url)}>
                Copy
              </button>
            </p>
          )}
        </section>
      )}

      <h2>Decks ({decks.length})</h2>
      {decks.length === 0 ? (
        <p style={{ color: 'var(--text-muted)' }}>No decks in this event yet. {canEditEvent && 'Use "Add decks" above to add one or more.'}</p>
      ) : (
        <>
          {canEditEvent && editing && (
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
              Update deck name, player, rank, and archetype below. Click Save above to save event and all deck changes.
            </p>
          )}
          <div className="table-wrap-outer">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Deck</th>
                    <th scope="col">Player</th>
                    <th scope="col">Rank</th>
                    <th scope="col">{editing && isEDH ? 'Archetype (commander)' : 'Archetype'}</th>
                    {canEditEvent && !editing && <th scope="col">Actions</th>}
                  </tr>
                </thead>
                <tbody>
                  {decks.map((d) => (
                    <tr key={d.deck_id}>
                      {editing ? (
                        <>
                          <td>
                            <input
                              type="text"
                              value={getDeckEdit(d).name}
                              onChange={(e) => setDeckEditField(d.deck_id, 'name', e.target.value, defaultDeckEdit(d))}
                              placeholder="Deck name"
                              style={{ width: '100%', minWidth: 120, boxSizing: 'border-box' }}
                              aria-label={`Deck name for deck ${d.deck_id}`}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              value={getDeckEdit(d).player}
                              onChange={(e) => setDeckEditField(d.deck_id, 'player', e.target.value, defaultDeckEdit(d))}
                              placeholder="Player"
                              style={{ width: '100%', minWidth: 100, boxSizing: 'border-box' }}
                              aria-label={`Player for deck ${d.deck_id}`}
                            />
                          </td>
                          <td>
                            <input
                              type="text"
                              value={getDeckEdit(d).rank}
                              onChange={(e) => setDeckEditField(d.deck_id, 'rank', e.target.value, defaultDeckEdit(d))}
                              placeholder="e.g. 1, 2, 3-4"
                              style={{ width: '100%', minWidth: 70, boxSizing: 'border-box' }}
                              aria-label={`Rank for deck ${d.deck_id}`}
                            />
                          </td>
                          <td>
                            {isEDH ? (
                              <CardSearchInput
                                id={`bulk-archetype-${d.deck_id}`}
                                value={getDeckEdit(d).archetype}
                                onChange={(val) => setDeckEditField(d.deck_id, 'archetype', val, defaultDeckEdit(d))}
                                placeholder="Search commander..."
                                aria-label={`Archetype (commander) for deck ${d.deck_id}`}
                              />
                            ) : (
                              <input
                                type="text"
                                value={getDeckEdit(d).archetype}
                                onChange={(e) => setDeckEditField(d.deck_id, 'archetype', e.target.value, defaultDeckEdit(d))}
                                placeholder="Archetype"
                                style={{ width: '100%', minWidth: 100, boxSizing: 'border-box' }}
                                aria-label={`Archetype for deck ${d.deck_id}`}
                              />
                            )}
                          </td>
                        </>
                      ) : (
                        <>
                          <td>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                              <Link to={`/decks/${d.deck_id}`} style={{ color: 'var(--accent)' }}>{cellStr(d.name) || 'Unnamed'}</Link>
                              {!(d.mainboard && d.mainboard.length) && (
                                <span
                                  style={{
                                    marginLeft: 6,
                                    fontSize: '0.7rem',
                                    padding: '0.1rem 0.35rem',
                                    background: 'rgba(220, 53, 69, 0.2)',
                                    borderRadius: 4,
                                    color: 'var(--danger, #dc3545)',
                                  }}
                                  title="No cards in mainboard"
                                >
                                  empty
                                </span>
                              )}
                            </span>
                          </td>
                          <td>
                            {cellStr(d.player) ? (
                              <Link to={`/players/${encodeURIComponent(cellStr(d.player))}`} style={{ color: 'var(--accent)' }}>
                                {cellStr(d.player)}
                              </Link>
                            ) : (
                              '—'
                            )}
                          </td>
                          <td>{cellStr(d.rank) || '—'}</td>
                          <td>
                            {cellStr(d.archetype) ? (
                              <Link to={`/archetypes/${encodeURIComponent(cellStr(d.archetype))}`} style={{ color: 'var(--accent)' }}>
                                {cellStr(d.archetype)}
                              </Link>
                            ) : (
                              '—'
                            )}
                          </td>
                          {canEditEvent && (
                            <td>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', alignItems: 'center' }}>
                                <button
                                  type="button"
                                  className="btn"
                                  style={{ fontSize: '0.875rem', padding: '0.25rem 0.5rem' }}
                                  onClick={() => openUpdateDeck(d)}
                                >
                                  Update
                                </button>
                                <button
                                  type="button"
                                  className="btn"
                                  style={{ fontSize: '0.875rem', padding: '0.25rem 0.5rem', color: 'var(--danger, #c00)' }}
                                  disabled={deletingDeckId === d.deck_id}
                                  onClick={() => handleDeleteDeckClick(d.deck_id)}
                                >
                                  {deletingDeckId === d.deck_id ? '…' : 'Delete deck'}
                                </button>
                                <button
                                  type="button"
                                  className="btn"
                                  style={{ fontSize: '0.875rem', padding: '0.25rem 0.5rem' }}
                                  disabled={uploadingDeck && uploadDeckForDeckId === d.deck_id}
                                  onClick={() => openUploadDeckModal(d.deck_id)}
                                >
                                  {uploadingDeck && uploadDeckForDeckId === d.deck_id ? 'Uploading…' : 'Upload deck'}
                                </button>
                                <button
                                  type="button"
                                  className="btn"
                                  style={{ fontSize: '0.875rem', padding: '0.25rem 0.5rem' }}
                                  disabled={loadingMatchups || savingMatchups}
                                  onClick={() => openUpdateMatchupsModal(d.deck_id)}
                                >
                                  Update matchups
                                </button>
                                {showUploadLinksSection && (
                                  <button
                                    type="button"
                                    className="btn"
                                    style={{ fontSize: '0.875rem', padding: '0.25rem 0.5rem' }}
                                    disabled={sendingFeedbackLinkForPlayer !== null}
                                    onClick={() => handleSendFeedbackLinkToPlayer(cellStr(d.player))}
                                  >
                                    {sendingFeedbackLinkForPlayer === cellStr(d.player) ? 'Sending…' : 'Send feedback link'}
                                  </button>
                                )}
                              </div>
                            </td>
                          )}
                        </>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {canEditEvent && editingDeckId != null && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="update-deck-title"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
          onClick={(e) => e.target === e.currentTarget && closeUpdateDeck()}
        >
          <div
            className="card"
            style={{
              maxWidth: 420,
              width: '100%',
              maxHeight: '90vh',
              overflow: 'auto',
              margin: '1.5rem',
              padding: '1.5rem',
              borderRadius: 12,
              background: 'var(--bg-card)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="update-deck-title" style={{ marginTop: 0, marginBottom: '1rem' }}>Update deck</h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1rem' }}>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Deck name</span>
                <input
                  type="text"
                  value={editDeckName}
                  onChange={(e) => setEditDeckName(e.target.value)}
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  placeholder="Deck name"
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Player</span>
                <input
                  type="text"
                  value={editDeckPlayer}
                  onChange={(e) => setEditDeckPlayer(e.target.value)}
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  placeholder="Player"
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">Rank</span>
                <input
                  type="text"
                  value={editDeckRank}
                  onChange={(e) => setEditDeckRank(e.target.value)}
                  style={{ width: '100%', boxSizing: 'border-box' }}
                  placeholder="e.g. 1, 2, 3-4, 5-8, 9-16, 17-32, 33-64, 65-128"
                />
              </label>
              <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                <span className="label">
                  {(event?.format_id ?? '').toLowerCase() === 'edh' || (event?.format_id ?? '').toLowerCase() === 'commander'
                    ? 'Archetype (commander)'
                    : 'Archetype'}
                </span>
                {(event?.format_id ?? '').toLowerCase() === 'edh' || (event?.format_id ?? '').toLowerCase() === 'commander' ? (
                  <CardSearchInput
                    value={editDeckArchetype}
                    onChange={setEditDeckArchetype}
                    placeholder="Search commander..."
                    aria-label="Archetype (commander)"
                  />
                ) : (
                  <input
                    type="text"
                    value={editDeckArchetype}
                    onChange={(e) => setEditDeckArchetype(e.target.value)}
                    style={{ width: '100%', boxSizing: 'border-box' }}
                    placeholder="Archetype"
                  />
                )}
              </label>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn" onClick={saveDeckUpdate} disabled={savingDeck}>
                {savingDeck ? 'Saving…' : 'Save'}
              </button>
              <button type="button" className="btn" onClick={closeUpdateDeck}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {canEditEvent && uploadDeckForDeckId != null && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="upload-deck-title"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
          onClick={(e) => e.target === e.currentTarget && closeUploadDeckModal()}
        >
          <div
            className="card"
            style={{
              maxWidth: 520,
              width: '100%',
              maxHeight: '90vh',
              overflow: 'auto',
              margin: '1.5rem',
              padding: '1.5rem',
              borderRadius: 12,
              background: 'var(--bg-card)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="upload-deck-title" style={{ marginTop: 0, marginBottom: '1rem' }}>
              Upload deck {decks.find((x) => x.deck_id === uploadDeckForDeckId) ? `— ${cellStr(decks.find((x) => x.deck_id === uploadDeckForDeckId)?.name) || 'Unnamed'}` : ''}
            </h2>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem', marginBottom: '0.75rem' }}>
              Paste a deck list in Moxfield style (section headers: Commander, Mainboard, Sideboard; lines like &quot;4 Lightning Bolt&quot;).
            </p>
            <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem', marginBottom: '1rem' }}>
              <span className="label">Deck list</span>
              <textarea
                value={uploadDeckListText}
                onChange={(e) => setUploadDeckListText(e.target.value)}
                placeholder={`Mainboard\n4 Lightning Bolt\n2 Counterspell\n\nSideboard\n2 Flusterstorm`}
                rows={14}
                style={{ width: '100%', boxSizing: 'border-box', fontFamily: 'inherit', fontSize: '0.9rem', resize: 'vertical' }}
                aria-label="Deck list"
              />
            </label>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn btn-primary" onClick={handleUploadDeckSubmit} disabled={uploadingDeck}>
                {uploadingDeck ? 'Uploading…' : 'Upload'}
              </button>
              <button type="button" className="btn" onClick={closeUploadDeckModal} disabled={uploadingDeck}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {matchupsDeckId != null && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="update-matchups-title"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
          onClick={(e) => e.target === e.currentTarget && !savingMatchups && closeUpdateMatchupsModal()}
        >
          <div
            className="card"
            style={{
              maxWidth: 520,
              width: '100%',
              maxHeight: '90vh',
              overflow: 'auto',
              margin: '1.5rem',
              padding: '1.5rem',
              borderRadius: 12,
              background: 'var(--bg-card)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="update-matchups-title" style={{ marginTop: 0, marginBottom: '1rem' }}>
              Update matchups {decks.find((d) => d.deck_id === matchupsDeckId) ? `— ${cellStr(decks.find((d) => d.deck_id === matchupsDeckId)?.name) || 'Unnamed'}` : ''}
            </h2>
            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
              Result is for <strong>this deck (you)</strong> vs the selected opponent. Use &quot;Intentional draw&quot; for agreed draws; use &quot;Intentional draw (you win/lose)&quot; when the result is ID but tiebreakers assign a win or loss. Opponent name must match a player in this event.
            </p>
            {loadingMatchups ? (
              <p>Loading…</p>
            ) : (
              <>
                <div style={{ marginBottom: '1rem' }}>
                  {matchupsList.map((m, i) => (
                    <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <select
                        value={m.opponent_player}
                        onChange={(e) => updateMatchupRow(i, 'opponent_player', e.target.value)}
                        style={{ minWidth: 140 }}
                        disabled={savingMatchups}
                        aria-label="Opponent"
                      >
                        <option value="">Select opponent</option>
                        {matchupsOpponentOptions.map((name) => (
                          <option key={name} value={name}>{name}</option>
                        ))}
                      </select>
                      <select
                        value={m.result || 'draw'}
                        onChange={(e) => updateMatchupRow(i, 'result', e.target.value)}
                        disabled={savingMatchups}
                        style={{ minWidth: 200 }}
                        aria-label="Result (you vs this opponent)"
                        title="Result for you vs this opponent"
                      >
                        {MATCHUP_RESULT_OPTIONS.map((opt) => (
                          <option key={opt.value} value={opt.value}>{opt.label}</option>
                        ))}
                      </select>
                      <button type="button" className="btn" style={{ padding: '0.2rem 0.5rem' }} onClick={() => removeMatchupRow(i)} disabled={savingMatchups}>
                        Remove
                      </button>
                    </div>
                  ))}
                  <button type="button" className="btn" style={{ marginTop: '0.35rem' }} onClick={addMatchupRow} disabled={savingMatchups || matchupsList.length >= 10}>
                    Add matchup
                  </button>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button type="button" className="btn btn-primary" onClick={handleSaveMatchups} disabled={savingMatchups}>
                    {savingMatchups ? 'Saving…' : 'Save'}
                  </button>
                  <button type="button" className="btn" onClick={closeUpdateMatchupsModal} disabled={savingMatchups}>
                    Cancel
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {confirmDeleteEvent && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-delete-event-title"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
          onClick={(e) => e.target === e.currentTarget && setConfirmDeleteEvent(false)}
        >
          <div
            className="card"
            style={{
              maxWidth: 400,
              width: '100%',
              padding: '1.5rem',
              borderRadius: 12,
              background: 'var(--bg-card)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="confirm-delete-event-title" style={{ marginTop: 0, marginBottom: '0.75rem' }}>Delete event?</h2>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Are you sure you want to delete this event and all its decks? This cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn" style={{ color: 'var(--danger, #c00)' }} onClick={handleDeleteConfirm} disabled={deleting}>
                {deleting ? 'Deleting…' : 'Delete event'}
              </button>
              <button type="button" className="btn" onClick={() => setConfirmDeleteEvent(false)} disabled={deleting}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {confirmDeleteDeckId != null && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="confirm-delete-deck-title"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
          onClick={(e) => e.target === e.currentTarget && setConfirmDeleteDeckId(null)}
        >
          <div
            className="card"
            style={{
              maxWidth: 400,
              width: '100%',
              padding: '1.5rem',
              borderRadius: 12,
              background: 'var(--bg-card)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="confirm-delete-deck-title" style={{ marginTop: 0, marginBottom: '0.75rem' }}>Delete deck?</h2>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Are you sure you want to delete this deck? This cannot be undone.
            </p>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn" style={{ color: 'var(--danger, #c00)' }} onClick={handleDeleteDeckConfirm} disabled={deletingDeckId !== null}>
                {deletingDeckId === confirmDeleteDeckId ? 'Deleting…' : 'Delete deck'}
              </button>
              <button type="button" className="btn" onClick={() => setConfirmDeleteDeckId(null)} disabled={deletingDeckId !== null}>
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {blocker.state === 'blocked' && hasUnsavedEdits && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="unsaved-changes-title"
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
            padding: '1rem',
          }}
          onClick={(e) => e.target === e.currentTarget && blocker.reset()}
        >
          <div
            className="card"
            style={{
              maxWidth: 400,
              width: '100%',
              padding: '1.5rem',
              borderRadius: 12,
              background: 'var(--bg-card)',
              boxShadow: '0 8px 32px rgba(0,0,0,0.3)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="unsaved-changes-title" style={{ marginTop: 0, marginBottom: '0.75rem' }}>Unsaved changes</h2>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              You have unsaved changes. Do you want to leave this page? Your changes will be lost.
            </p>
            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button type="button" className="btn btn-primary" onClick={() => blocker.proceed()}>
                Leave
              </button>
              <button type="button" className="btn" onClick={() => blocker.reset()}>
                Stay
              </button>
            </div>
          </div>
        </div>
      )}

      </div>
    </>
  )
}
