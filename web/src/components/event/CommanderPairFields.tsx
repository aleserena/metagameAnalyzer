import { useEffect, useRef, useState } from 'react'
import CardSearchInput from '../CardSearchInput'
import { getCardLookup } from '../../api'
import { getPartnerMode, type PartnerMode } from '../../lib/deckUtils'

export interface CommanderPairFieldsProps {
  commander1: string
  commander2: string
  onCommander1Change: (name: string) => void
  onCommander2Change: (name: string) => void
  label1?: string
  label2?: string
  id1?: string
  id2?: string
}

/** Hint text describing what the enabled secondary slot accepts. */
const ROLE_HINT: Record<string, string> = {
  partner: 'Partner',
  partner_with: 'Partner',
  friends_forever: 'Friends forever',
  background: 'Background',
  doctors_companion: "Doctor's companion",
  time_lord_doctor: 'Time Lord Doctor',
}

/**
 * Two commander pickers with partner-aware filtering: the primary only offers
 * legal commanders; the secondary is enabled only when the primary has a
 * partner-style ability and is filtered to cards that may legally pair with it.
 */
export default function CommanderPairFields({
  commander1,
  commander2,
  onCommander1Change,
  onCommander2Change,
  label1 = 'Commander 1',
  label2 = 'Commander 2',
  id1 = 'commander-1',
  id2 = 'commander-2',
}: CommanderPairFieldsProps) {
  const [mode, setMode] = useState<PartnerMode>({ role: null })
  const prevC1 = useRef<string | null>(null)

  useEffect(() => {
    let cancelled = false
    const isInitial = prevC1.current === null
    const changed = !isInitial && prevC1.current !== commander1
    prevC1.current = commander1

    if (!commander1.trim()) {
      setMode({ role: null })
      if (changed) onCommander2Change('')
      return
    }

    getCardLookup([commander1])
      .then((lk) => {
        if (cancelled) return
        const m = getPartnerMode(lk[commander1])
        setMode(m)
        if (m.role === 'partner_with' && m.partnerWithName) {
          // "Partner with X" only pairs with that specific card: lock it in.
          if (changed || !commander2.trim()) onCommander2Change(m.partnerWithName)
        } else if (m.role === null && changed) {
          onCommander2Change('')
        }
      })
      .catch(() => {
        if (!cancelled) setMode({ role: null })
      })

    return () => {
      cancelled = true
    }
    // Re-run only when the primary commander changes; callbacks are intentionally
    // excluded to avoid re-running on every parent render.
  }, [commander1])

  const secondaryEnabled = mode.role !== null
  const lockedToNamedPartner = mode.role === 'partner_with'
  // 'partner_with' has no backend search role (the card is fixed); others map 1:1.
  const secondaryRole = lockedToNamedPartner ? undefined : mode.role ?? undefined
  const secondaryHint = mode.role ? ROLE_HINT[mode.role] : undefined

  return (
    <>
      <div className="form-group" style={{ marginBottom: 0, minWidth: 200 }}>
        <label htmlFor={id1}>{label1}</label>
        <CardSearchInput
          id={id1}
          value={commander1}
          onChange={onCommander1Change}
          role="commander"
          placeholder="Search commander..."
          aria-label={label1}
        />
      </div>
      <div className="form-group" style={{ marginBottom: 0, minWidth: 200 }}>
        <label htmlFor={id2}>
          {label2}
          {secondaryHint ? ` (${secondaryHint})` : ''}
        </label>
        <CardSearchInput
          id={id2}
          value={commander2}
          onChange={onCommander2Change}
          role={secondaryRole}
          disabled={!secondaryEnabled || lockedToNamedPartner}
          placeholder={secondaryEnabled ? 'Search partner...' : 'No partner ability'}
          aria-label={label2}
        />
      </div>
    </>
  )
}
