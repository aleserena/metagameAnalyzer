import { MATCHUP_RESULT_OPTIONS } from '../../lib/matchups'

export type MatchupRow = { opponent_player: string; result: string; intentional_draw: boolean }

export interface MatchupsFormProps {
  matchupsList: MatchupRow[]
  opponentOptions: string[]
  loading: boolean
  saving: boolean
  onUpdateRow: (i: number, field: 'opponent_player' | 'result' | 'intentional_draw', value: string | boolean) => void
  onRemoveRow: (i: number) => void
  onAddRow: () => void
  onSave: () => void
  onCancel: () => void
}

export default function MatchupsForm({
  matchupsList,
  opponentOptions,
  loading,
  saving,
  onUpdateRow,
  onRemoveRow,
  onAddRow,
  onSave,
  onCancel,
}: MatchupsFormProps) {
  return (
    <>
      <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
        Result is for <strong>this deck (you)</strong> vs the selected opponent. Use &quot;Intentional draw&quot; for agreed draws; use &quot;Intentional draw (you win/lose)&quot; when the result is ID but tiebreakers assign a win or loss. Opponent name must match a player in this event.
      </p>
      {loading ? (
        <p>Loading…</p>
      ) : (
        <>
          <div style={{ marginBottom: '1rem' }}>
            {matchupsList.map((m, i) => (
              <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
                <select
                  value={m.opponent_player}
                  onChange={(e) => onUpdateRow(i, 'opponent_player', e.target.value)}
                  style={{ minWidth: 140 }}
                  disabled={saving}
                  aria-label="Opponent"
                >
                  <option value="">Select opponent</option>
                  {opponentOptions.map((name) => (
                    <option key={name} value={name}>{name}</option>
                  ))}
                </select>
                <select
                  value={m.result || 'draw'}
                  onChange={(e) => onUpdateRow(i, 'result', e.target.value)}
                  disabled={saving}
                  style={{ minWidth: 200 }}
                  aria-label="Result (you vs this opponent)"
                  title="Result for you vs this opponent"
                >
                  {MATCHUP_RESULT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
                <button type="button" className="btn" style={{ padding: '0.2rem 0.5rem' }} onClick={() => onRemoveRow(i)} disabled={saving}>
                  Remove
                </button>
              </div>
            ))}
            <button type="button" className="btn" style={{ marginTop: '0.35rem' }} onClick={onAddRow} disabled={saving || matchupsList.length >= 10}>
              Add matchup
            </button>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button type="button" className="btn btn-primary" onClick={onSave} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button type="button" className="btn" onClick={onCancel} disabled={saving}>
              Cancel
            </button>
          </div>
        </>
      )}
    </>
  )
}
