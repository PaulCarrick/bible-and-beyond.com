import { useCallback, useState } from 'react'
import type { ListItem } from './listItems'

// The results ticked for a list on one search page, in the order they were ticked (the ticks stay through other
// pages of results and other searches, as for playlists, until saved or cancelled).
export function useListPicks() {
  const [picks, setPicks] = useState<ListItem[]>([])
  const isPicked = useCallback((key: string) => picks.some((item) => item.key === key), [picks])
  const toggle = useCallback((item: ListItem, picked: boolean) => {
    setPicks((current) => (picked ? (current.some((each) => each.key === item.key) ? current : [...current, item]) : current.filter((each) => each.key !== item.key)))
  }, [])
  // Select all: tick many at once (those ticked already keep their place), or untick them.
  const addMany = useCallback((items: ListItem[]) => {
    setPicks((current) => [...current, ...items.filter((item, index) => !current.some((each) => each.key === item.key) && items.findIndex((each) => each.key === item.key) === index)])
  }, [])
  const removeMany = useCallback((keys: string[]) => {
    const unwanted = new Set(keys)
    setPicks((current) => current.filter((each) => !unwanted.has(each.key)))
  }, [])
  const clear = useCallback(() => setPicks([]), [])
  return { picks, isPicked, toggle, addMany, removeMany, clear }
}

export type ListPicks = ReturnType<typeof useListPicks>

// One save takes up to this many entries (saved_lists.py MAX_ITEMS_PER_SAVE), so Select all ticks no more.
export const SELECT_ALL_LIMIT = 200

// Every result of a paged search, page after page, until the limit or the end.
export async function collectPages<T>(
  fetchPage: (page: number) => Promise<{ results: T[]; total: number }>,
  limit: number,
): Promise<T[]> {
  const all: T[] = []
  for (let page = 1; all.length < limit; page += 1) {
    const found = await fetchPage(page)
    all.push(...found.results)
    if (found.results.length === 0 || all.length >= found.total) {
      break
    }
  }
  return all.slice(0, limit)
}
