import CommanderPairFields from './CommanderPairFields'

export interface UpdateDeckFormProps {
  name: string
  player: string
  rank: string
  /** EDH: the primary commander. Non-EDH: the free-text archetype. */
  archetype: string
  /** EDH only: the secondary (partner/background) commander. */
  commander2?: string
  isEDH: boolean
  /** Suggested player names (existing players not already in this event). New names can be typed. */
  playerOptions?: string[]
  onNameChange: (v: string) => void
  onPlayerChange: (v: string) => void
  onRankChange: (v: string) => void
  onArchetypeChange: (v: string) => void
  onCommander2Change?: (v: string) => void
  onSave: () => void
  onCancel: () => void
  saving: boolean
}

const PLAYER_DATALIST_ID = 'update-deck-player-datalist'

export default function UpdateDeckForm({
  name,
  player,
  rank,
  archetype,
  commander2 = '',
  isEDH,
  playerOptions = [],
  onNameChange,
  onPlayerChange,
  onRankChange,
  onArchetypeChange,
  onCommander2Change,
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
            list={PLAYER_DATALIST_ID}
            style={{ width: '100%', boxSizing: 'border-box' }}
            placeholder="Select existing player or type new name"
            aria-describedby="player-hint"
          />
          <datalist id={PLAYER_DATALIST_ID}>
            {playerOptions.map((opt) => (
              <option key={opt} value={opt} />
            ))}
          </datalist>
          <span id="player-hint" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Players already in this event are not shown. Type a new name to add a new player.
          </span>
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
        {isEDH ? (
          <CommanderPairFields
            id1="update-deck-commander1"
            id2="update-deck-commander2"
            commander1={archetype}
            commander2={commander2}
            onCommander1Change={onArchetypeChange}
            onCommander2Change={onCommander2Change ?? (() => {})}
            label1="Commander"
            label2="Partner / Background"
          />
        ) : (
          <label style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
            <span className="label">Archetype</span>
            <input
              type="text"
              value={archetype}
              onChange={(e) => onArchetypeChange(e.target.value)}
              style={{ width: '100%', boxSizing: 'border-box' }}
              placeholder="Archetype"
            />
          </label>
        )}
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
