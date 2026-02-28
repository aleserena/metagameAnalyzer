import type { ReactNode } from 'react'
import type { CardLookupResult } from '../api'
import type { TopCardItem } from '../lib/topCards'
import CardHover from './CardHover'
import { ColorFilterPills, CmcFilterPills, TypeFilterPills } from './FilterPills'
import { useTopCardsFilters } from '../hooks/useTopCardsFilters'

function formatConversion(c: TopCardItem): string {
  const pct =
    c.conversion_rate_pct ??
    (typeof c.decks_top8 === 'number' && c.decks > 0
      ? Math.round((100 * c.decks_top8) / c.decks * 10) / 10
      : null)
  return pct != null ? `${pct}%` : '—'
}

export interface TopCardsSectionProps {
  title: string
  subtitle?: ReactNode
  topCardsMain: TopCardItem[]
  cardMeta: Record<string, CardLookupResult>
  loadingCardMeta: boolean
  placementWeighted?: boolean
  /** Optional toolbar content before filters (e.g. "Ignore lands" checkbox) */
  extraToolbar?: ReactNode
}

export default function TopCardsSection({
  title,
  subtitle,
  topCardsMain,
  cardMeta,
  loadingCardMeta,
  placementWeighted = false,
  extraToolbar,
}: TopCardsSectionProps) {
  const {
    filterColor,
    filterCmc,
    filterType,
    setFilterColorAndResetPage,
    setFilterCmcAndResetPage,
    setFilterTypeAndResetPage,
    clearFilters,
    hasAnyFilter,
    sortBy,
    setSortBy,
    filteredTotal,
    filteredPages,
    safePage,
    topCardsSlice,
    setTopCardsPage,
    perPage,
  } = useTopCardsFilters({ topCardsMain, cardMeta })

  return (
    <div className="chart-container">
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '1rem',
          flexWrap: 'wrap',
          gap: '0.5rem',
        }}
      >
        <h3 style={{ margin: 0 }}>
          {title}
          {subtitle}
        </h3>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <span style={{ fontSize: '0.875rem', color: 'var(--text-muted)' }}>
            {filteredTotal === 0
              ? '0'
              : `${safePage * perPage + 1}–${Math.min((safePage + 1) * perPage, filteredTotal)}`}{' '}
            of {filteredTotal}
          </span>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.2rem 0.5rem', fontSize: '0.8rem' }}
            disabled={safePage === 0}
            onClick={() => setTopCardsPage((p) => Math.max(0, p - 1))}
          >
            Prev
          </button>
          <button
            type="button"
            className="btn"
            style={{ padding: '0.2rem 0.5rem', fontSize: '0.8rem' }}
            disabled={filteredTotal <= perPage || safePage >= filteredPages - 1}
            onClick={() => setTopCardsPage((p) => Math.min(filteredPages - 1, p + 1))}
          >
            Next
          </button>
        </div>
      </div>

      <div
        className="top-cards-filters"
        style={{
          padding: '0.5rem 0.75rem',
          background: 'var(--bg)',
          border: '1px solid var(--border)',
          borderRadius: 8,
          marginBottom: '1rem',
          fontSize: '0.8125rem',
        }}
      >
        <div className="toolbar pill-group" style={{ gap: '0.5rem', alignItems: 'center' }}>
          {extraToolbar}
          <span style={{ color: 'var(--text-muted)', fontWeight: 600 }}>Filter:</span>
          <span style={{ fontWeight: 600 }}>Color</span>
          <ColorFilterPills
            selected={filterColor}
            onChange={setFilterColorAndResetPage}
            disabled={loadingCardMeta}
          />
          <span style={{ fontWeight: 600 }}>Cost</span>
          <CmcFilterPills
            selected={filterCmc}
            onChange={setFilterCmcAndResetPage}
            disabled={loadingCardMeta}
          />
          <span style={{ fontWeight: 600 }}>Type</span>
          <TypeFilterPills
            selected={filterType}
            onChange={setFilterTypeAndResetPage}
            disabled={loadingCardMeta}
          />
          <button
            type="button"
            className="btn"
            style={{ padding: '0.2rem 0.5rem', fontSize: '0.8rem' }}
            onClick={clearFilters}
            disabled={!hasAnyFilter}
          >
            Clear filters
          </button>
        </div>
      </div>

      {loadingCardMeta && (
        <p style={{ color: 'var(--text-muted)', fontSize: '0.875rem', marginBottom: '0.5rem' }}>
          Loading card data…
        </p>
      )}
      {hasAnyFilter && filteredTotal === 0 && !loadingCardMeta && (
        <p style={{ color: 'var(--text-muted)', marginBottom: '1rem' }}>
          No cards match the current filters.
        </p>
      )}
      <div className="table-wrap-outer">
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col">#</th>
                <th scope="col">Card</th>
                <th scope="col">Decks</th>
                <th scope="col">
                  <button
                    type="button"
                    className="th-sort"
                    onClick={() => setSortBy('play_rate')}
                    title="Sort by play rate"
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      font: 'inherit',
                      cursor: 'pointer',
                      color: 'inherit',
                      textDecoration: sortBy === 'play_rate' ? 'underline' : undefined,
                    }}
                  >
                    Play Rate {sortBy === 'play_rate' ? '▼' : ''}
                  </button>
                </th>
                <th scope="col">
                  <button
                    type="button"
                    className="th-sort"
                    onClick={() => setSortBy('conversion_rate')}
                    title="Sort by conversion rate (top 8)"
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      font: 'inherit',
                      cursor: 'pointer',
                      color: 'inherit',
                      textDecoration: sortBy === 'conversion_rate' ? 'underline' : undefined,
                    }}
                  >
                    Conversion % {sortBy === 'conversion_rate' ? '▼' : ''}
                  </button>
                </th>
                <th scope="col">
                  <button
                    type="button"
                    className="th-sort"
                    onClick={() => setSortBy('copies')}
                    title="Sort by copies"
                    style={{
                      background: 'none',
                      border: 'none',
                      padding: 0,
                      font: 'inherit',
                      cursor: 'pointer',
                      color: 'inherit',
                      textDecoration: sortBy === 'copies' ? 'underline' : undefined,
                    }}
                  >
                    {placementWeighted ? 'Weighted Score' : 'Copies'} {sortBy === 'copies' ? '▼' : ''}
                  </button>
                </th>
              </tr>
            </thead>
            <tbody>
              {topCardsSlice.map((c, i) => (
                <tr key={c.card}>
                  <td style={{ color: 'var(--text-muted)' }}>{safePage * perPage + i + 1}</td>
                  <td>
                    <CardHover cardName={c.card} linkTo>
                      {c.card}
                    </CardHover>
                  </td>
                  <td>{c.decks}</td>
                  <td>{c.play_rate_pct}%</td>
                  <td title={c.decks_top8 != null ? `${c.decks_top8} top 8` : undefined}>
                    {formatConversion(c)}
                  </td>
                  <td>{c.total_copies}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
