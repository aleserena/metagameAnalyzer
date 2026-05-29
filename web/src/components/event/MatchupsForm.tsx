import {
  MATCHUP_RESULT_OPTIONS,
  MAX_MATCHUPS_TOTAL,
  MAX_TOP8_MATCHUP_ROWS,
  type MatchupRow,
} from '../../lib/matchups'

export type { MatchupRow }

export interface MatchupsFormProps {
  swissMatchups: MatchupRow[]
  top8Matchups: MatchupRow[]
  showTop8Section: boolean
  swissRounds: number
  opponentOptions: string[]
  loading: boolean
  saving: boolean
  onUpdateSwissRow: (i: number, field: 'opponent_player' | 'result' | 'intentional_draw', value: string | boolean) => void
  onRemoveSwissRow: (i: number) => void
  onAddSwissRow: () => void
  onUpdateTop8Row: (i: number, field: 'opponent_player' | 'result' | 'intentional_draw', value: string | boolean) => void
  onRemoveTop8Row: (i: number) => void
  onAddTop8Row: () => void
  onSave: () => void
  onCancel: () => void
}

function MatchupRows({
  rows,
  phaseLabel,
  opponentOptions,
  saving,
  maxRows,
  totalCount,
  onUpdateRow,
  onRemoveRow,
  onAddRow,
}: {
  rows: MatchupRow[]
  phaseLabel: string
  opponentOptions: string[]
  saving: boolean
  maxRows: number
  totalCount: number
  onUpdateRow: (i: number, field: 'opponent_player' | 'result' | 'intentional_draw', value: string | boolean) => void
  onRemoveRow: (i: number) => void
  onAddRow: () => void
}) {
  return (
    <div style={{ marginBottom: '1rem' }}>
      <h3 style={{ fontSize: '0.95rem', margin: '0 0 0.5rem' }}>{phaseLabel}</h3>
      {rows.map((m, i) => (
        <div key={i} style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem', alignItems: 'center', marginBottom: '0.5rem' }}>
          <select
            value={m.opponent_player}
            onChange={(e) => onUpdateRow(i, 'opponent_player', e.target.value)}
            style={{ minWidth: 140 }}
            disabled={saving}
            aria-label={`${phaseLabel} opponent`}
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
            aria-label={`${phaseLabel} result`}
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
      <button
        type="button"
        className="btn"
        style={{ marginTop: '0.35rem' }}
        onClick={onAddRow}
        disabled={saving || rows.length >= maxRows || totalCount >= MAX_MATCHUPS_TOTAL}
      >
        Add matchup
      </button>
    </div>
  )
}

export default function MatchupsForm({
  swissMatchups,
  top8Matchups,
  showTop8Section,
  swissRounds,
  opponentOptions,
  loading,
  saving,
  onUpdateSwissRow,
  onRemoveSwissRow,
  onAddSwissRow,
  onUpdateTop8Row,
  onRemoveTop8Row,
  onAddTop8Row,
  onSave,
  onCancel,
}: MatchupsFormProps) {
  const totalCount = swissMatchups.length + top8Matchups.length

  return (
    <>
      <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
        Result is for <strong>this deck (you)</strong> vs the selected opponent. Swiss rounds are numbered 1–{swissRounds}.
        {showTop8Section && ' Top 8 matchups can repeat an opponent from Swiss (e.g. quarterfinal rematch).'}
        {' '}Use intentional-draw options when tiebreakers assign win/loss.
      </p>
      {loading ? (
        <p>Loading…</p>
      ) : (
        <>
          <MatchupRows
            rows={swissMatchups}
            phaseLabel="Swiss"
            opponentOptions={opponentOptions}
            saving={saving}
            maxRows={swissRounds}
            totalCount={totalCount}
            onUpdateRow={onUpdateSwissRow}
            onRemoveRow={onRemoveSwissRow}
            onAddRow={onAddSwissRow}
          />
          {showTop8Section && (
            <MatchupRows
              rows={top8Matchups}
              phaseLabel="Top 8"
              opponentOptions={opponentOptions.filter((n) => n !== 'Bye' && n !== '(drop)')}
              saving={saving}
              maxRows={MAX_TOP8_MATCHUP_ROWS}
              totalCount={totalCount}
              onUpdateRow={onUpdateTop8Row}
              onRemoveRow={onRemoveTop8Row}
              onAddRow={onAddTop8Row}
            />
          )}
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
