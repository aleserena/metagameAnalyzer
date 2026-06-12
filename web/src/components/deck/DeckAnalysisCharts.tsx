import { useRef, useState } from 'react'
import { ComposedChart, Bar, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend } from 'recharts'
import type { DeckAnalysis } from '../../api'
import { MTG_COLOR_FILL } from '../../constants'
import { PieChartTooltipContent } from '../PieChartTooltip'

const TYPE_COLORS = ['#1d9bf0', '#00ba7c', '#f7931a', '#e91e63', '#9c27b0', '#8b7355', '#00bcd4']

const FUNCTIONAL_LABELS: Record<string, string> = {
  land: 'Lands',
  manaless: 'Manaless',
  ramp: 'Ramp',
  removal: 'Removal',
  wipe: 'Board Wipes',
  disenchant: 'Disenchant',
  counter: 'Counter Spells',
  'card-draw': 'Card Draw',
  tutor: 'Tutors',
  graveyard: 'Graveyard',
  token: 'Token Gen.',
  protection: 'Protection',
  evasion: 'Evasion',
  lifegain: 'Lifegain',
  'combat-trick': 'Combat Tricks',
  uncounterable: 'Uncounterable',
  ward: 'Ward',
  hatebear: 'Hatebears',
  discard: 'Discard',
}

export interface DeckAnalysisChartsProps {
  analysis: DeckAnalysis
}

export default function DeckAnalysisCharts({ analysis }: DeckAnalysisChartsProps) {
  const functionalEntries = Object.entries(analysis.functional_stats ?? {}).filter(([, v]) => v.count > 0)
  const [tooltipAnchor, setTooltipAnchor] = useState<{ rect: DOMRect; key: string } | null>(null)
  const hideTimeout = useRef<ReturnType<typeof setTimeout> | null>(null)
  const activeCategory = tooltipAnchor ? (analysis.functional_stats ?? {})[tooltipAnchor.key] : null

  const showTooltip = (el: HTMLElement, key: string) => {
    if (hideTimeout.current) clearTimeout(hideTimeout.current)
    setTooltipAnchor({ rect: el.getBoundingClientRect(), key })
  }
  const scheduleHide = () => {
    hideTimeout.current = setTimeout(() => setTooltipAnchor(null), 80)
  }
  const cancelHide = () => {
    if (hideTimeout.current) clearTimeout(hideTimeout.current)
  }

  const tooltipPos = tooltipAnchor
    ? (() => {
        const { rect } = tooltipAnchor
        const vw = window.innerWidth
        const vh = window.innerHeight
        const estW = 220
        const estH = Math.min(32 + (activeCategory?.cards.length ?? 0) * 22, 260)
        const centerX = rect.left + rect.width / 2
        const left = Math.max(8 + estW / 2, Math.min(vw - 8 - estW / 2, centerX))
        const showBelow = rect.bottom + 8 + estH <= vh - 8
        return showBelow
          ? { left, top: rect.bottom, transform: 'translate(-50%, 8px)' }
          : { left, top: rect.top, transform: 'translate(-50%, calc(-100% - 8px))' }
      })()
    : null

  return (
    <div style={{ marginBottom: '1rem' }}>
      <h3 style={{ margin: '0 0 0.5rem' }}>Deck Analysis</h3>
      {functionalEntries.length > 0 && (
        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '0.5rem',
            marginBottom: '1rem',
          }}
        >
          {functionalEntries.map(([key, stat]) => (
            <div
              key={key}
              onMouseEnter={(e) => showTooltip(e.currentTarget as HTMLElement, key)}
              onMouseLeave={scheduleHide}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                padding: '0.25rem 0.6rem',
                borderRadius: 20,
                border: '1px solid var(--border)',
                background: 'var(--bg-card)',
                fontSize: '0.82rem',
                whiteSpace: 'nowrap',
                cursor: 'default',
              }}
            >
              <span style={{ fontWeight: 700, fontFamily: 'monospace', fontSize: '0.9rem' }}>{stat.count}</span>
              <span style={{ color: 'var(--text-muted)' }}>{FUNCTIONAL_LABELS[key] ?? key}</span>
            </div>
          ))}
        </div>
      )}
      {tooltipAnchor && activeCategory && tooltipPos && (
        <div
          onMouseEnter={cancelHide}
          onMouseLeave={() => setTooltipAnchor(null)}
          style={{
            position: 'fixed',
            left: tooltipPos.left,
            top: tooltipPos.top,
            transform: tooltipPos.transform,
            zIndex: 9999,
            background: 'var(--bg-card)',
            border: '1px solid var(--border)',
            borderRadius: 8,
            padding: '0.5rem 0.75rem',
            minWidth: 160,
            maxWidth: 260,
            maxHeight: 260,
            overflowY: 'auto',
            boxShadow: '0 4px 16px rgba(0,0,0,0.3)',
          }}
        >
          <div style={{ fontWeight: 600, fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.35rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
            {FUNCTIONAL_LABELS[tooltipAnchor.key] ?? tooltipAnchor.key}
          </div>
          {activeCategory.cards.map(([qty, name]) => (
            <div key={name} style={{ display: 'flex', gap: '0.4rem', fontSize: '0.85rem', padding: '0.1rem 0' }}>
              <span style={{ fontFamily: 'monospace', color: 'var(--text-muted)', minWidth: 16, textAlign: 'right' }}>{qty}</span>
              <span>{name}</span>
            </div>
          ))}
        </div>
      )}
      <div className="deck-analysis-grid">
        <div className="chart-container">
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Mana Curve</h4>
          <ResponsiveContainer width="100%" height={180}>
            <ComposedChart
              data={(() => {
                const curve = analysis.mana_curve || {}
                const perm = analysis.mana_curve_permanent ?? {}
                const nonPerm = analysis.mana_curve_non_permanent ?? {}
                const hasSplit = Object.keys(perm).length > 0 || Object.keys(nonPerm).length > 0
                const maxCmc = Math.max(0, ...Object.keys(curve).map(Number), ...Object.keys(perm).map(Number), ...Object.keys(nonPerm).map(Number))
                return Array.from({ length: maxCmc + 1 }, (_, cmc) => {
                  const p = hasSplit ? (perm[cmc] ?? 0) : (curve[cmc] ?? 0)
                  const n = hasSplit ? (nonPerm[cmc] ?? 0) : 0
                  return { cmc, permanent: p, non_permanent: n, count: p + n }
                })
              })()}
              margin={{ top: 10, right: 16, left: 36, bottom: 24 }}
            >
              <XAxis dataKey="cmc" />
              <YAxis width={28} />
              <Tooltip
                contentStyle={{
                  background: 'var(--bg-card)',
                  border: '1px solid var(--border)',
                  borderRadius: 8,
                  color: 'var(--text)',
                }}
                labelStyle={{ color: 'var(--text)', fontWeight: 600 }}
              />
              <Bar dataKey="permanent" stackId="curve" fill="#22c55e" name="Permanents" />
              <Bar dataKey="non_permanent" stackId="curve" fill="#ef4444" name="Non-permanents" />
              <Line type="monotone" dataKey="count" stroke="#c2410c" strokeWidth={2} dot={{ r: 4, fill: '#c2410c' }} name="" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-container">
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Color Distribution</h4>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart margin={{ top: 8, right: 8, bottom: 58, left: 8 }}>
              <Pie
                data={[
                  { name: 'White', value: analysis.color_distribution.W || 0, color: MTG_COLOR_FILL.White },
                  { name: 'Blue', value: analysis.color_distribution.U || 0, color: MTG_COLOR_FILL.Blue },
                  { name: 'Black', value: analysis.color_distribution.B || 0, color: MTG_COLOR_FILL.Black },
                  { name: 'Red', value: analysis.color_distribution.R || 0, color: MTG_COLOR_FILL.Red },
                  { name: 'Green', value: analysis.color_distribution.G || 0, color: MTG_COLOR_FILL.Green },
                  { name: 'Colorless', value: analysis.color_distribution.C || 0, color: MTG_COLOR_FILL.Colorless },
                ].filter((d) => d.value > 0)}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={58}
              >
                {[
                  { name: 'White', value: analysis.color_distribution.W || 0, color: MTG_COLOR_FILL.White },
                  { name: 'Blue', value: analysis.color_distribution.U || 0, color: MTG_COLOR_FILL.Blue },
                  { name: 'Black', value: analysis.color_distribution.B || 0, color: MTG_COLOR_FILL.Black },
                  { name: 'Red', value: analysis.color_distribution.R || 0, color: MTG_COLOR_FILL.Red },
                  { name: 'Green', value: analysis.color_distribution.G || 0, color: MTG_COLOR_FILL.Green },
                  { name: 'Colorless', value: analysis.color_distribution.C || 0, color: MTG_COLOR_FILL.Colorless },
                ]
                  .filter((d) => d.value > 0)
                  .map((d) => (
                    <Cell key={d.name} fill={d.color} />
                  ))}
              </Pie>
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const p = payload[0]?.payload as { name?: string; value?: number }
                  if (!p) return null
                  return (
                    <PieChartTooltipContent
                      title={p.name ?? ''}
                      subtitle={p.value != null ? `${p.value}%` : undefined}
                    />
                  )
                }}
              />
              <Legend layout="horizontal" verticalAlign="bottom" wrapperStyle={{ paddingTop: 4 }} formatter={(_, entry: { payload?: { name?: string; value?: number } }) => entry?.payload ? `${entry.payload.name ?? ''} ${entry.payload.value ?? ''}%` : ''} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        <div className="chart-container">
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Lands Distribution</h4>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart margin={{ top: 8, right: 8, bottom: 58, left: 8 }}>
              <Pie
                data={[
                  { name: 'Lands', value: analysis.lands_distribution.lands, color: '#8b7355' },
                  { name: 'Non-Lands', value: analysis.lands_distribution.nonlands, color: '#1d9bf0' },
                ].filter((d) => d.value > 0)}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                outerRadius={58}
              >
                {[
                  { name: 'Lands', value: analysis.lands_distribution.lands, color: '#8b7355' },
                  { name: 'Non-Lands', value: analysis.lands_distribution.nonlands, color: '#1d9bf0' },
                ]
                  .filter((d) => d.value > 0)
                  .map((d) => (
                    <Cell key={d.name} fill={d.color} />
                  ))}
              </Pie>
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const p = payload[0]?.payload as { name?: string; value?: number }
                  if (!p) return null
                  const total = analysis.lands_distribution.lands + analysis.lands_distribution.nonlands
                  const pct = total ? Math.round((100 * (p.value ?? 0)) / total) : 0
                  return (
                    <PieChartTooltipContent
                      title={p.name ?? ''}
                      subtitle={`${p.value ?? ''} (${pct}%)`}
                    />
                  )
                }}
              />
              <Legend layout="horizontal" verticalAlign="bottom" formatter={(_, entry: { payload?: { name?: string; value?: number } }) => {
                const p = entry?.payload
                if (!p) return ''
                const total = analysis.lands_distribution.lands + analysis.lands_distribution.nonlands
                const pct = total ? Math.round((100 * (p.value ?? 0)) / total) : 0
                return `${p.name ?? ''} ${p.value ?? ''} (${pct}%)`
              }} wrapperStyle={{ paddingTop: 4 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
        {analysis.type_distribution && Object.keys(analysis.type_distribution).length > 0 && (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Card Type Distribution</h4>
            <ResponsiveContainer width="100%" height={220}>
              <PieChart margin={{ top: 28, right: 8, bottom: 72, left: 8 }}>
                <Pie
                  data={Object.entries(analysis.type_distribution)
                    .filter(([, v]) => v > 0)
                    .map(([name, value], i) => ({
                      name,
                      value,
                      color: TYPE_COLORS[i % TYPE_COLORS.length],
                    }))}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={54}
                >
                  {Object.entries(analysis.type_distribution)
                    .filter(([, v]) => v > 0)
                    .map(([name], i) => (
                      <Cell key={name} fill={TYPE_COLORS[i % TYPE_COLORS.length]} />
                    ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null
                    const p = payload[0]?.payload as { name?: string; value?: number }
                    if (!p) return null
                    return (
                      <PieChartTooltipContent
                        title={p.name ?? ''}
                        subtitle={p.value != null ? `${p.value}` : undefined}
                      />
                    )
                  }}
                />
                <Legend layout="horizontal" verticalAlign="bottom" wrapperStyle={{ paddingTop: 4 }} formatter={(_, entry: { payload?: { name?: string; value?: number } }) => entry?.payload ? `${entry.payload.name ?? ''} ${entry.payload.value ?? ''}` : ''} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}
