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
  const clear = useCallback(() => setPicks([]), [])
  return { picks, isPicked, toggle, clear }
}

export type ListPicks = ReturnType<typeof useListPicks>
