import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import type { PlayerAnalysis, PlayerAnalysisEvent } from '../../api'
import { MTG_COLOR_FILL } from '../../constants'
import { PieChartTooltipContent } from '../PieChartTooltip'

const ARCH_PALETTE = [
  '#1d9bf0',
  '#00ba7c',
  '#f7931a',
  '#e91e63',
  '#9c27b0',
  '#8b7355',
  '#00bcd4',
  '#ff9800',
  '#4caf50',
  '#795548',
]

const FINISH_LABELS = ['1st', '2nd', 'T4', 'T8', 'T16', 'T32', 'T64', 'T128']
const FINISH_TICKS = [1, 2, 3.5, 6.5, 12.5, 24.5, 48.5, 96.5]

const BASE_CHART_TOOLTIP = {
  background: 'var(--bg-card)',
  border: '1px solid var(--border)',
  borderRadius: 8,
  color: 'var(--text)',
} as const

const BASE_CHART_LABEL = { color: 'var(--text)', fontWeight: 600 } as const

export interface PlayerAnalysisChartsProps {
  analysis: PlayerAnalysis
}

function parseDDMMYY(s: string): number {
  const parts = s.split('/')
  if (parts.length !== 3) return 0
  const dd = parseInt(parts[0], 10) || 0
  const mm = parseInt(parts[1], 10) || 0
  const yy = parseInt(parts[2], 10) || 0
  const year = yy < 100 ? 2000 + yy : yy
  return Date.UTC(year, mm - 1, dd)
}

function formatShortDate(ms: number): string {
  if (!ms) return ''
  const d = new Date(ms)
  return `${d.getUTCDate().toString().padStart(2, '0')}/${(d.getUTCMonth() + 1).toString().padStart(2, '0')}/${String(d.getUTCFullYear()).slice(2)}`
}

function monthKey(ms: number): string {
  const d = new Date(ms)
  return `${d.getUTCFullYear()}-${(d.getUTCMonth() + 1).toString().padStart(2, '0')}`
}

function formatMonthLabel(key: string): string {
  const [y, m] = key.split('-')
  const months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
  const mi = Math.max(0, Math.min(11, parseInt(m, 10) - 1))
  return `${months[mi]} ${y.slice(2)}`
}

function rankLabelFromNum(n: number | null | undefined): string {
  if (n == null) return ''
  if (n <= 1) return '1st'
  if (n <= 2) return '2nd'
  if (n <= 4) return 'T4'
  if (n <= 8) return 'T8'
  if (n <= 16) return 'T16'
  if (n <= 32) return 'T32'
  if (n <= 64) return 'T64'
  return 'T128+'
}

function KPI({ label, value, hint }: { label: string; value: React.ReactNode; hint?: string }) {
  return (
    <div
      style={{
        background: 'var(--bg-card)',
        border: '1px solid var(--border)',
        borderRadius: 8,
        padding: '0.75rem 1rem',
        minWidth: 140,
        flex: '1 1 140px',
      }}
    >
      <div className="label" style={{ fontSize: '0.75rem' }}>{label}</div>
      <div style={{ fontSize: '1.4rem', fontWeight: 600 }}>{value}</div>
      {hint ? (
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{hint}</div>
      ) : null}
    </div>
  )
}

export default function PlayerAnalysisCharts({ analysis }: PlayerAnalysisChartsProps) {
  const events = analysis.per_event
  const hasEvents = events.length > 0

  // Finish per event scatter + rolling average
  const finishSeries = useMemo(() => {
    return events
      .filter((e) => e.normalized_rank_num != null && e.date)
      .map((e) => ({
        x: parseDDMMYY(e.date),
        y: e.normalized_rank_num ?? 0,
        player_count: e.player_count || 0,
        event_name: e.event_name || '',
        rank: e.rank || '',
        archetype: e.archetype || '',
      }))
      .sort((a, b) => a.x - b.x)
  }, [events])

  // Merged series: per-event dot + running rolling avg (window 5) + running median.
  // Running median is maintained via a sorted insertion so it O(n log n) updates per date.
  const finishChartData = useMemo(() => {
    const window = 5
    const sorted: number[] = []
    return finishSeries.map((s, i) => {
      const slice = finishSeries.slice(Math.max(0, i - window + 1), i + 1)
      const rolling = slice.reduce((acc, p) => acc + p.y, 0) / slice.length
      let lo = 0
      let hi = sorted.length
      while (lo < hi) {
        const mid = (lo + hi) >>> 1
        if (sorted[mid] < s.y) lo = mid + 1
        else hi = mid
      }
      sorted.splice(lo, 0, s.y)
      const n = sorted.length
      const midIdx = Math.floor(n / 2)
      const median = n % 2 === 0 ? (sorted[midIdx - 1] + sorted[midIdx]) / 2 : sorted[midIdx]
      return {
        ...s,
        rolling: Math.round(rolling * 10) / 10,
        median: Math.round(median * 10) / 10,
      }
    })
  }, [finishSeries])

  // Cumulative points with rolling top-8%
  const cumulativePoints = useMemo(() => {
    let running = 0
    let top8Running = 0
    const window = 5
    return events
      .filter((e) => e.date)
      .map((e, i, arr) => {
        running += e.points || 0
        const windowSlice = arr.slice(Math.max(0, i - window + 1), i + 1)
        const top8 = windowSlice.filter(
          (s) => s.normalized_rank === '1' || s.normalized_rank === '2' || s.normalized_rank === '3-4' || s.normalized_rank === '5-8',
        ).length
        top8Running = Math.round((100 * top8) / windowSlice.length)
        return {
          x: parseDDMMYY(e.date),
          cumulative: Math.round(running * 10) / 10,
          top8_pct: top8Running,
        }
      })
  }, [events])

  // Leaderboard rank history
  const rankHistory = useMemo(
    () =>
      analysis.leaderboard_history.map((p) => ({
        x: parseDDMMYY(p.date),
        rank: p.rank,
        total_players: p.total_players,
      })),
    [analysis.leaderboard_history],
  )

  // Events per month (stacked bar of wins/top2-only/top4-only/top8-only/other)
  const eventsPerMonth = useMemo(() => {
    const byMonth: Record<string, { wins: number; top2: number; top4: number; top8: number; other: number }> = {}
    for (const e of events) {
      if (!e.date) continue
      const k = monthKey(parseDDMMYY(e.date))
      const entry = byMonth[k] ?? { wins: 0, top2: 0, top4: 0, top8: 0, other: 0 }
      if (e.normalized_rank === '1') entry.wins += 1
      else if (e.normalized_rank === '2') entry.top2 += 1
      else if (e.normalized_rank === '3-4') entry.top4 += 1
      else if (e.normalized_rank === '5-8') entry.top8 += 1
      else entry.other += 1
      byMonth[k] = entry
    }
    return Object.keys(byMonth)
      .sort()
      .map((k) => ({ month: formatMonthLabel(k), key: k, ...byMonth[k] }))
  }, [events])

  // Calendar heatmap — by month, last 24 months
  const monthlyHeatmap = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const e of events) {
      if (!e.date) continue
      const k = monthKey(parseDDMMYY(e.date))
      counts[k] = (counts[k] ?? 0) + 1
    }
    const keys = Object.keys(counts).sort()
    if (keys.length === 0) return { cells: [], max: 0 }
    const first = keys[0]
    const last = keys[keys.length - 1]
    const [fy, fm] = first.split('-').map((v) => parseInt(v, 10))
    const [ly, lm] = last.split('-').map((v) => parseInt(v, 10))
    const cells: { key: string; count: number; label: string }[] = []
    let y = fy
    let m = fm
    while (y < ly || (y === ly && m <= lm)) {
      const k = `${y}-${m.toString().padStart(2, '0')}`
      cells.push({ key: k, count: counts[k] ?? 0, label: formatMonthLabel(k) })
      m += 1
      if (m > 12) {
        m = 1
        y += 1
      }
    }
    const max = Math.max(...cells.map((c) => c.count), 1)
    return { cells, max }
  }, [events])

  // Color identity pie — use color_distribution from backend (per-deck avg)
  const colorPieData = useMemo(() => {
    const cd = analysis.color_distribution || {}
    return [
      { name: 'White', value: cd.W || 0, color: MTG_COLOR_FILL.White },
      { name: 'Blue', value: cd.U || 0, color: MTG_COLOR_FILL.Blue },
      { name: 'Black', value: cd.B || 0, color: MTG_COLOR_FILL.Black },
      { name: 'Red', value: cd.R || 0, color: MTG_COLOR_FILL.Red },
      { name: 'Green', value: cd.G || 0, color: MTG_COLOR_FILL.Green },
      { name: 'Colorless', value: cd.C || 0, color: MTG_COLOR_FILL.Colorless },
    ].filter((d) => d.value > 0)
  }, [analysis.color_distribution])

  const archetypePie = useMemo(() => {
    const rows = [...analysis.archetype_distribution]
    rows.sort((a, b) => b.count - a.count)
    const top = rows.slice(0, 8)
    const rest = rows.slice(8)
    const other = rest.reduce(
      (acc, r) => ({ count: acc.count + r.count, pct: acc.pct + r.pct }),
      { count: 0, pct: 0 },
    )
    const combined = [...top]
    if (other.count > 0) {
      combined.push({ archetype: `Other (${rest.length})`, count: other.count, pct: Math.round(other.pct * 10) / 10 })
    }
    return combined
  }, [analysis.archetype_distribution])

  const formatPie = useMemo(() => analysis.format_distribution, [analysis.format_distribution])

  const colorCountPie = useMemo(() => {
    const cc = analysis.color_count_distribution || {}
    return [
      { name: 'Colorless', value: cc['0'] || 0 },
      { name: 'Mono', value: cc['1'] || 0 },
      { name: '2-color', value: cc['2'] || 0 },
      { name: '3-color', value: cc['3'] || 0 },
      { name: '4-color', value: cc['4'] || 0 },
      { name: '5-color', value: cc['5'] || 0 },
    ].filter((d) => d.value > 0)
  }, [analysis.color_count_distribution])

  // Domain for finish axis based on worst rank seen
  const finishMax = useMemo(() => {
    const m = finishSeries.reduce((acc, s) => Math.max(acc, s.y), 1)
    return Math.max(m, 8)
  }, [finishSeries])

  const finishTicks = useMemo(() => FINISH_TICKS.filter((t) => t <= finishMax), [finishMax])

  if (!hasEvents) {
    return null
  }

  const h = analysis.highlights
  const commanderTop = analysis.commander_distribution.slice(0, 10)

  return (
    <div style={{ marginBottom: '1.5rem' }}>
      <h3 style={{ margin: '0 0 0.75rem' }}>Player Analytics</h3>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '1rem' }}>
        <KPI label="Best finish" value={h.best_finish || '—'} />
        <KPI label="Longest Top-8 streak" value={h.longest_top8_streak} hint="events in a row" />
        <KPI
          label="Biggest-field win"
          value={h.biggest_field_win != null ? `${h.biggest_field_win}p` : '—'}
          hint={h.biggest_field_win != null ? 'players in the event' : 'no wins yet'}
        />
        <KPI label="Total events" value={h.total_events} />
        <KPI
          label="Avg cadence"
          value={h.avg_days_between_events != null ? `${h.avg_days_between_events}d` : '—'}
          hint="days between events"
        />
        {h.first_event_date && h.last_event_date ? (
          <KPI label="Active span" value={`${h.first_event_date} → ${h.last_event_date}`} />
        ) : null}
      </div>

      <div className="deck-analysis-grid">
        <div className="chart-container">
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Finish per event</h4>
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={finishChartData} margin={{ top: 10, right: 16, left: 30, bottom: 10 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis
                type="number"
                dataKey="x"
                domain={['dataMin', 'dataMax']}
                tickFormatter={formatShortDate}
                name="Date"
                scale="time"
              />
              <YAxis
                type="number"
                reversed
                domain={[1, finishMax]}
                ticks={finishTicks}
                tickFormatter={(v) => FINISH_LABELS[FINISH_TICKS.indexOf(v)] ?? String(v)}
                width={40}
                name="Finish"
              />
              <ZAxis type="number" dataKey="player_count" range={[40, 260]} name="Field" />
              <Tooltip
                contentStyle={BASE_CHART_TOOLTIP}
                labelStyle={BASE_CHART_LABEL}
                labelFormatter={(v) => formatShortDate(Number(v))}
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const p = payload[0]?.payload as typeof finishChartData[number] | undefined
                  if (!p) return null
                  return (
                    <PieChartTooltipContent
                      title={p.event_name || 'Event'}
                      subtitle={`${formatShortDate(p.x)} · ${p.rank || rankLabelFromNum(p.y)}${p.player_count ? ` · ${p.player_count}p` : ''}`}
                    >
                      {p.archetype ? (
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{p.archetype}</div>
                      ) : null}
                      <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: 4 }}>
                        Rolling avg: {rankLabelFromNum(p.rolling)} ({p.rolling}) · Median: {rankLabelFromNum(p.median)} ({p.median})
                      </div>
                    </PieChartTooltipContent>
                  )
                }}
              />
              <Legend wrapperStyle={{ fontSize: '0.75rem' }} />
              <Scatter name="Event finish" dataKey="y" fill="#1d9bf0" />
              {finishChartData.length > 1 ? (
                <Line
                  type="monotone"
                  dataKey="rolling"
                  name="Rolling avg (5)"
                  stroke="#c2410c"
                  strokeWidth={2}
                  dot={false}
                  activeDot={false}
                  isAnimationActive={false}
                />
              ) : null}
              {finishChartData.length > 1 ? (
                <Line
                  type="monotone"
                  dataKey="median"
                  name="Running median"
                  stroke="#a855f7"
                  strokeWidth={2}
                  strokeDasharray="5 4"
                  dot={false}
                  activeDot={false}
                  isAnimationActive={false}
                />
              ) : null}
            </ComposedChart>
          </ResponsiveContainer>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            Dot size reflects field size. Orange is the 5-event rolling average; dashed purple is the running median finish over time.
          </div>
        </div>

        <div className="chart-container">
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Cumulative points</h4>
          <ResponsiveContainer width="100%" height={240}>
            <ComposedChart data={cumulativePoints} margin={{ top: 10, right: 16, left: 30, bottom: 10 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} tickFormatter={formatShortDate} />
              <YAxis yAxisId="left" width={40} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} width={40} tickFormatter={(v) => `${v}%`} />
              <Tooltip
                contentStyle={BASE_CHART_TOOLTIP}
                labelStyle={BASE_CHART_LABEL}
                labelFormatter={(v) => formatShortDate(Number(v))}
              />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="cumulative" name="Points" stroke="#00ba7c" strokeWidth={2} dot={false} />
              <Line yAxisId="right" type="monotone" dataKey="top8_pct" name="Top-8 % (rolling 5)" stroke="#f7931a" strokeWidth={2} dot={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>

        {rankHistory.length > 0 ? (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Leaderboard rank over time</h4>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={rankHistory} margin={{ top: 10, right: 16, left: 30, bottom: 10 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="x" type="number" domain={['dataMin', 'dataMax']} tickFormatter={formatShortDate} />
                <YAxis reversed width={40} allowDecimals={false} />
                <Tooltip
                  contentStyle={BASE_CHART_TOOLTIP}
                  labelStyle={BASE_CHART_LABEL}
                  labelFormatter={(v) => formatShortDate(Number(v))}
                  formatter={(value, _name, props) => {
                    const total = (props?.payload as { total_players?: number } | undefined)?.total_players ?? 0
                    return [`#${value} of ${total}`, 'Leaderboard rank']
                  }}
                />
                <Line type="monotone" dataKey="rank" stroke="#9c27b0" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Rank at each date they played, relative to all players with a deck up to that date.
            </div>
          </div>
        ) : null}

        {eventsPerMonth.length > 0 ? (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Events per month</h4>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={eventsPerMonth} margin={{ top: 10, right: 16, left: 20, bottom: 40 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="month" angle={-35} textAnchor="end" interval={0} height={60} tick={{ fontSize: 11 }} />
                <YAxis allowDecimals={false} width={30} />
                <Tooltip contentStyle={BASE_CHART_TOOLTIP} labelStyle={BASE_CHART_LABEL} />
                <Legend />
                <Bar dataKey="wins" stackId="ev" fill="#f59e0b" name="Wins" />
                <Bar dataKey="top2" stackId="ev" fill="#84cc16" name="2nd" />
                <Bar dataKey="top4" stackId="ev" fill="#22d3ee" name="T4" />
                <Bar dataKey="top8" stackId="ev" fill="#1d9bf0" name="T8" />
                <Bar dataKey="other" stackId="ev" fill="#6b7280" name="Other" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : null}
      </div>

      <div className="deck-analysis-grid">
        <div className="chart-container">
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Archetypes played</h4>
          <ResponsiveContainer width="100%" height={240}>
            <PieChart margin={{ top: 8, right: 8, bottom: 40, left: 8 }}>
              <Pie data={archetypePie} dataKey="count" nameKey="archetype" cx="50%" cy="50%" outerRadius={72}>
                {archetypePie.map((_, i) => (
                  <Cell key={i} fill={ARCH_PALETTE[i % ARCH_PALETTE.length]} />
                ))}
              </Pie>
              <Tooltip
                content={({ active, payload }) => {
                  if (!active || !payload?.length) return null
                  const p = payload[0]?.payload as { archetype?: string; count?: number; pct?: number }
                  if (!p) return null
                  return (
                    <PieChartTooltipContent
                      title={p.archetype ?? ''}
                      subtitle={`${p.count ?? 0} decks${p.pct != null ? ` · ${p.pct}%` : ''}`}
                    />
                  )
                }}
              />
              <Legend
                layout="horizontal"
                verticalAlign="bottom"
                wrapperStyle={{ paddingTop: 4, fontSize: '0.75rem' }}
                formatter={(value, entry) => {
                  const p = (entry as unknown as { payload?: { archetype?: string; pct?: number } })?.payload
                  return p ? `${p.archetype ?? ''} ${p.pct ?? ''}%` : String(value ?? '')
                }}
              />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {colorPieData.length > 0 ? (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Color identity (avg)</h4>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart margin={{ top: 8, right: 8, bottom: 40, left: 8 }}>
                <Pie data={colorPieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={72}>
                  {colorPieData.map((d) => (
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
                <Legend
                  layout="horizontal"
                  verticalAlign="bottom"
                  wrapperStyle={{ paddingTop: 4, fontSize: '0.75rem' }}
                  formatter={(value, entry) => {
                    const p = (entry as unknown as { payload?: { name?: string; value?: number } })?.payload
                    return p ? `${p.name ?? ''} ${p.value ?? 0}%` : String(value ?? '')
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        {formatPie.length > 0 ? (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Formats</h4>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart margin={{ top: 8, right: 8, bottom: 40, left: 8 }}>
                <Pie data={formatPie} dataKey="count" nameKey="format_id" cx="50%" cy="50%" outerRadius={72}>
                  {formatPie.map((_, i) => (
                    <Cell key={i} fill={ARCH_PALETTE[i % ARCH_PALETTE.length]} />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null
                    const p = payload[0]?.payload as { format_id?: string; count?: number; pct?: number }
                    if (!p) return null
                    return (
                      <PieChartTooltipContent
                        title={p.format_id ?? ''}
                        subtitle={`${p.count ?? 0} decks${p.pct != null ? ` · ${p.pct}%` : ''}`}
                      />
                    )
                  }}
                />
                <Legend
                  layout="horizontal"
                  verticalAlign="bottom"
                  wrapperStyle={{ paddingTop: 4, fontSize: '0.75rem' }}
                  formatter={(value, entry) => {
                    const p = (entry as unknown as { payload?: { format_id?: string; pct?: number } })?.payload
                    return p ? `${p.format_id ?? ''} ${p.pct ?? ''}%` : String(value ?? '')
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        {colorCountPie.length > 0 ? (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Color count</h4>
            <ResponsiveContainer width="100%" height={240}>
              <PieChart margin={{ top: 8, right: 8, bottom: 40, left: 8 }}>
                <Pie data={colorCountPie} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={72}>
                  {colorCountPie.map((_, i) => (
                    <Cell key={i} fill={ARCH_PALETTE[(i + 3) % ARCH_PALETTE.length]} />
                  ))}
                </Pie>
                <Tooltip
                  content={({ active, payload }) => {
                    if (!active || !payload?.length) return null
                    const p = payload[0]?.payload as { name?: string; value?: number }
                    if (!p) return null
                    return <PieChartTooltipContent title={p.name ?? ''} subtitle={`${p.value ?? 0} decks`} />
                  }}
                />
                <Legend
                  layout="horizontal"
                  verticalAlign="bottom"
                  wrapperStyle={{ paddingTop: 4, fontSize: '0.75rem' }}
                  formatter={(value, entry) => {
                    const p = (entry as unknown as { payload?: { name?: string; value?: number } })?.payload
                    return p ? `${p.name ?? ''} (${p.value ?? 0})` : String(value ?? '')
                  }}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
        ) : null}
      </div>

      {analysis.archetype_performance.length > 0 ? (
        <div className="chart-container">
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Archetype performance</h4>
          <div className="table-wrap-outer">
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Archetype</th>
                    <th>Decks</th>
                    <th>Avg finish</th>
                    <th>Best</th>
                    <th>Win %</th>
                    <th>Top-8 %</th>
                  </tr>
                </thead>
                <tbody>
                  {analysis.archetype_performance.map((r) => (
                    <tr key={r.archetype}>
                      <td>{r.archetype}</td>
                      <td>{r.count}</td>
                      <td>{r.avg_finish != null ? rankLabelFromNum(r.avg_finish) + ` (${r.avg_finish})` : '—'}</td>
                      <td>{r.best_finish || '—'}</td>
                      <td>{r.win_pct.toFixed(1)}%</td>
                      <td>{r.top8_pct.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : null}

      {commanderTop.length > 0 ? (
        <div className="chart-container">
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Most-played commanders</h4>
          <ResponsiveContainer width="100%" height={Math.max(180, commanderTop.length * 26)}>
            <BarChart data={commanderTop} layout="vertical" margin={{ top: 4, right: 16, left: 20, bottom: 4 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis type="number" allowDecimals={false} />
              <YAxis type="category" dataKey="commander" width={140} tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={BASE_CHART_TOOLTIP} labelStyle={BASE_CHART_LABEL} />
              <Bar dataKey="count" fill="#1d9bf0" name="Decks" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}

      {monthlyHeatmap.cells.length > 0 ? (
        <div className="chart-container">
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Activity heatmap</h4>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(48px, 1fr))',
              gap: 4,
            }}
          >
            {monthlyHeatmap.cells.map((cell) => {
              const alpha = cell.count === 0 ? 0.08 : 0.2 + 0.8 * (cell.count / monthlyHeatmap.max)
              return (
                <div
                  key={cell.key}
                  title={`${cell.label}: ${cell.count} event${cell.count === 1 ? '' : 's'}`}
                  style={{
                    background: `rgba(29, 155, 240, ${alpha})`,
                    border: '1px solid var(--border)',
                    borderRadius: 4,
                    padding: '0.35rem 0.35rem',
                    fontSize: 10,
                    color: cell.count > 0 ? 'var(--text)' : 'var(--text-muted)',
                    textAlign: 'center',
                  }}
                >
                  <div style={{ fontWeight: 600 }}>{cell.label.slice(0, 3)}</div>
                  <div>{cell.label.slice(4)}</div>
                  <div style={{ marginTop: 2 }}>{cell.count > 0 ? cell.count : ''}</div>
                </div>
              )
            })}
          </div>
        </div>
      ) : null}

      <div className="deck-analysis-grid">
        {analysis.top_cards.length > 0 ? (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Most-played cards</h4>
            <ResponsiveContainer width="100%" height={Math.max(220, analysis.top_cards.length * 22)}>
              <BarChart data={analysis.top_cards} layout="vertical" margin={{ top: 4, right: 16, left: 16, bottom: 4 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis type="number" allowDecimals={false} />
                <YAxis type="category" dataKey="card" width={160} tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={BASE_CHART_TOOLTIP}
                  labelStyle={BASE_CHART_LABEL}
                  formatter={(value, name, props) => {
                    const payload = (props?.payload ?? {}) as { deck_count?: number; total_copies?: number }
                    return [
                      `${payload.deck_count ?? value} decks · ${payload.total_copies ?? 0} copies`,
                      name,
                    ]
                  }}
                />
                <Bar dataKey="deck_count" fill="#00ba7c" name="Decks" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        {analysis.pet_cards.length > 0 ? (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Pet cards</h4>
            <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 0 }}>
              Cards this player keeps coming back to across many decks.
            </p>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
              {analysis.pet_cards.map((c) => (
                <span
                  key={c.card}
                  title={`${c.deck_count} decks · ${c.total_copies} total copies`}
                  style={{
                    padding: '0.2rem 0.55rem',
                    borderRadius: 999,
                    background: 'var(--bg-hover)',
                    border: '1px solid var(--border)',
                    fontSize: '0.8rem',
                  }}
                >
                  {c.card} <span style={{ color: 'var(--text-muted)' }}>×{c.deck_count}</span>
                </span>
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className="deck-analysis-grid">
        {analysis.metagame_comparison.length > 0 ? (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>You vs the metagame</h4>
            <ResponsiveContainer width="100%" height={Math.max(220, analysis.metagame_comparison.length * 28)}>
              <BarChart data={analysis.metagame_comparison} layout="vertical" margin={{ top: 4, right: 16, left: 20, bottom: 4 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis type="number" tickFormatter={(v) => `${v}%`} />
                <YAxis type="category" dataKey="archetype" width={140} tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={BASE_CHART_TOOLTIP}
                  labelStyle={BASE_CHART_LABEL}
                  formatter={(v, name) => [`${v}%`, name]}
                />
                <Legend />
                <Bar dataKey="player_pct" fill="#1d9bf0" name="Player" />
                <Bar dataKey="global_pct" fill="#8b7355" name="Metagame" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : null}

        {analysis.field_size_buckets.some((b) => b.count > 0) ? (
          <div className="chart-container">
            <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Performance by field size</h4>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={analysis.field_size_buckets} margin={{ top: 10, right: 16, left: 20, bottom: 10 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="bucket" />
                <YAxis yAxisId="left" allowDecimals={false} width={30} />
                <YAxis yAxisId="right" orientation="right" domain={[0, 100]} width={40} tickFormatter={(v) => `${v}%`} />
                <Tooltip contentStyle={BASE_CHART_TOOLTIP} labelStyle={BASE_CHART_LABEL} />
                <Legend />
                <Bar yAxisId="left" dataKey="count" fill="#1d9bf0" name="Events" />
                <Bar yAxisId="right" dataKey="top8_pct" fill="#f7931a" name="Top-8 %" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : null}
      </div>

      {Object.keys(analysis.average_mana_curve).length > 0 ? (
        <div className="chart-container">
          <h4 style={{ margin: '0 0 0.75rem', fontSize: '0.95rem' }}>Average mana curve</h4>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart
              data={Object.keys(analysis.average_mana_curve)
                .sort((a, b) => Number(a) - Number(b))
                .map((k) => ({ cmc: Number(k), count: analysis.average_mana_curve[k] }))}
              margin={{ top: 10, right: 16, left: 20, bottom: 10 }}
            >
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="cmc" />
              <YAxis width={30} />
              <Tooltip contentStyle={BASE_CHART_TOOLTIP} labelStyle={BASE_CHART_LABEL} />
              <Bar dataKey="count" fill="#22c55e" name="Avg copies" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : null}
    </div>
  )
}

export function _testing_parseDDMMYY(s: string): number {
  return parseDDMMYY(s)
}

export type { PlayerAnalysisEvent }
