import { useState, useMemo } from 'react'
import type { CardLookupResult } from '../api'
import type { TopCardItem } from '../lib/topCards'
import {
  getCardTypes,
  colorCategory,
  cmcBucket,
  TOP_CARDS_PER_PAGE,
} from '../lib/topCards'

export type TopCardsSortKey = 'copies' | 'play_rate' | 'conversion_rate'

export interface UseTopCardsFiltersParams {
  topCardsMain: TopCardItem[]
  cardMeta: Record<string, CardLookupResult>
}

export interface UseTopCardsFiltersResult {
  filterColor: string[]
  filterCmc: number[]
  filterType: string[]
  setFilterColorAndResetPage: (v: string[]) => void
  setFilterCmcAndResetPage: (v: number[]) => void
  setFilterTypeAndResetPage: (v: string[]) => void
  clearFilters: () => void
  hasAnyFilter: boolean
  sortBy: TopCardsSortKey
  setSortBy: (key: TopCardsSortKey) => void
  filteredTopCards: TopCardItem[]
  filteredTotal: number
  filteredPages: number
  safePage: number
  topCardsSlice: TopCardItem[]
  topCardsPage: number
  setTopCardsPage: (p: number | ((prev: number) => number)) => void
  perPage: number
}

export function useTopCardsFilters({
  topCardsMain,
  cardMeta,
}: UseTopCardsFiltersParams): UseTopCardsFiltersResult {
  const [filterColor, setFilterColor] = useState<string[]>([])
  const [filterCmc, setFilterCmc] = useState<number[]>([])
  const [filterType, setFilterType] = useState<string[]>([])
  const [topCardsPage, setTopCardsPage] = useState(0)
  const [sortBy, setSortByState] = useState<TopCardsSortKey>('copies')

  const hasAnyFilter = filterColor.length > 0 || filterCmc.length > 0 || filterType.length > 0

  const filteredTopCards = useMemo(() => {
    const filtered = topCardsMain.filter((c) => {
      const m = cardMeta[c.card]
      if (!m || 'error' in m) return !hasAnyFilter
      const colors = (m as CardLookupResult).color_identity ?? (m as CardLookupResult).colors ?? []
      const cat = colorCategory(colors)
      const bucket = cmcBucket((m as CardLookupResult).cmc)
      const cardTypes = getCardTypes((m as CardLookupResult).type_line)
      if (filterColor.length > 0 && !filterColor.includes(cat)) return false
      if (filterCmc.length > 0 && !filterCmc.includes(bucket)) return false
      if (filterType.length > 0 && !filterType.some((t) => cardTypes.includes(t))) return false
      return true
    })
    const key: (c: TopCardItem) => number =
      sortBy === 'conversion_rate'
        ? (c) => c.conversion_rate_pct ?? 0
        : sortBy === 'play_rate'
          ? (c) => c.play_rate_pct
          : (c) => c.total_copies
    return [...filtered].sort((a, b) => key(b) - key(a))
  }, [topCardsMain, cardMeta, filterColor, filterCmc, filterType, hasAnyFilter, sortBy])

  const setSortBy = (key: TopCardsSortKey) => {
    setSortByState(key)
    setTopCardsPage(0)
  }

  const filteredTotal = filteredTopCards.length
  const filteredPages = Math.ceil(filteredTotal / TOP_CARDS_PER_PAGE)
  const safePage = Math.min(topCardsPage, Math.max(0, filteredPages - 1))
  const topCardsSlice = filteredTopCards.slice(
    safePage * TOP_CARDS_PER_PAGE,
    (safePage + 1) * TOP_CARDS_PER_PAGE
  )

  const setFilterColorAndResetPage = (v: string[]) => {
    setFilterColor(v)
    setTopCardsPage(0)
  }
  const setFilterCmcAndResetPage = (v: number[]) => {
    setFilterCmc(v)
    setTopCardsPage(0)
  }
  const setFilterTypeAndResetPage = (v: string[]) => {
    setFilterType(v)
    setTopCardsPage(0)
  }
  const clearFilters = () => {
    setFilterColor([])
    setFilterCmc([])
    setFilterType([])
    setTopCardsPage(0)
  }

  return {
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
    filteredTopCards,
    filteredTotal,
    filteredPages,
    safePage,
    topCardsSlice,
    topCardsPage,
    setTopCardsPage,
    perPage: TOP_CARDS_PER_PAGE,
  }
}
