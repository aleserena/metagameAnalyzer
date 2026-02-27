import CardSearchInput from '../CardSearchInput'

export interface UpdateDeckFormProps {
  name: string
  player: string
  rank: string
  archetype: string
  isEDH: boolean
  onNameChange: (v: string) => void
  onPlayerChange: (v: string) => void
  onRankChange: (v: string) => void
  onArchetypeChange: (v: string) => void
  onSave: () => void
  onCancel: () => void
  saving: boolean
}

export default function UpdateDeckForm({
  name,
  player,
  rank,
  archetype,
  isEDH,
  onNameChange,
  onPlayerChange,
  onRankChange,
  onArchetypeChange,
  onSave,
  onCancel,
  saving,
}: UpdateDeckFormProps) {
  return (
    <>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1rem' }}>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <span className="label">Deck name</span>
          <input
            type="text"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            style={{ width: '100%', boxSizing: 'border-box' }}
            placeholder="Deck name"
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <span className="label">Player</span>
          <input
            type="text"
            value={player}
            onChange={(e) => onPlayerChange(e.target.value)}
            style={{ width: '100%', boxSizing: 'border-box' }}
            placeholder="Player"
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <span className="label">Rank</span>
          <input
            type="text"
            value={rank}
            onChange={(e) => onRankChange(e.target.value)}
            style={{ width: '100%', boxSizing: 'border-box' }}
            placeholder="e.g. 1, 2, 3-4, 5-8, 9-16, 17-32, 33-64, 65-128"
          />
        </label>
        <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
          <span className="label">{isEDH ? 'Archetype (commander)' : 'Archetype'}</span>
          {isEDH ? (
            <CardSearchInput
              value={archetype}
              onChange={onArchetypeChange}
              placeholder="Search commander..."
              aria-label="Archetype (commander)"
            />
          ) : (
            <input
              type="text"
              value={archetype}
              onChange={(e) => onArchetypeChange(e.target.value)}
              style={{ width: '100%', boxSizing: 'border-box' }}
              placeholder="Archetype"
            />
          )}
        </label>
      </div>
      <div style={{ display: 'flex', gap: '0.5rem' }}>
        <button type="button" className="btn" onClick={onSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </>
  )
}
