import type { PerPage } from './types'

export const perPageOptions: { value: PerPage; label: string }[] = [
  { value: 'automatic', label: 'Automatic (fit screen)' },
  { value: 10, label: '10' },
  { value: 25, label: '25' },
  { value: 50, label: '50' },
  { value: 100, label: '100' },
]

export function parsePerPage(value: string): PerPage {
  return value === 'automatic' ? 'automatic' : Number(value)
}
