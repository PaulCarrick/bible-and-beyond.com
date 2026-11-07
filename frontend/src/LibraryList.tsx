import { useEffect, useState } from 'react'

// Where an item can be opened: its groups (books, months or parts) and their units (chapters or days).
export interface LibraryChoices {
  // A short line about what it covers, such as "The whole Bible" or "4 parts, 114 chapters".
  summary: string
  groupLabel: string
  unitLabel: string
  groups: { number: number; name: string; units: { number: number; label: string }[] }[]
  // Where the choosers start (the first chapter, or today for a daily devotional).
  start: { group: number; unit: number }
}

export interface LibraryListItem {
  id: string
  name: string
  // The author, or another line under the name; may be empty.
  detail: string
}

interface LibraryListProps {
  heading: string
  intro: string
  items: LibraryListItem[]
  isHidden: boolean
  loadChoices: (id: string, signal: AbortSignal) => Promise<LibraryChoices>
  onRead: (id: string, group: number, unit: number) => void
}

// The first page of the commentaries, devotionals and other books: every item with its own choosers (book and
// chapter, month and day, or part and chapter) and a Read button that opens the reader there. Each item loads
// what it has only once the list is first shown.
function LibraryList({ heading, intro, items, isHidden, loadChoices, onRead }: LibraryListProps) {
  return (
    <div className="welcome library-list" hidden={isHidden}>
      <h1>{heading}</h1>
      <p>{intro}</p>
      <ul className="library-items">
        {items.map((item) => (
          <LibraryItem key={item.id} item={item} isHidden={isHidden} loadChoices={loadChoices} onRead={onRead} />
        ))}
      </ul>
    </div>
  )
}

interface LibraryItemProps {
  item: LibraryListItem
  isHidden: boolean
  loadChoices: LibraryListProps['loadChoices']
  onRead: LibraryListProps['onRead']
}

function LibraryItem({ item, isHidden, loadChoices, onRead }: LibraryItemProps) {
  const [choices, setChoices] = useState<LibraryChoices | null>(null)
  const [group, setGroup] = useState<number | null>(null)
  const [unit, setUnit] = useState<number | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    if (isHidden || choices !== null) {
      return
    }
    const controller = new AbortController()
    loadChoices(item.id, controller.signal)
      .then((loaded) => {
        setChoices(loaded)
        setGroup(loaded.start.group)
        setUnit(loaded.start.unit)
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setFailed(true)
        }
      })
    return () => controller.abort()
  }, [isHidden, choices, item.id, loadChoices])

  const groups = choices?.groups ?? []
  const units = groups.find((entry) => entry.number === group)?.units ?? []

  function chooseGroup(number: number) {
    setGroup(number)
    const newUnits = groups.find((entry) => entry.number === number)?.units ?? []
    // Keep the day when the month changes (a daily devotional), if that month has it; else the first.
    setUnit(newUnits.some((entry) => entry.number === unit) && choices?.unitLabel === 'Day' ? unit : (newUnits[0]?.number ?? 1))
  }

  return (
    <li className="library-item">
      <h3>{item.name}</h3>
      <p className="library-item-detail">
        {[item.detail, choices?.summary ?? ''].filter((part) => part !== '').join(' · ')}
        {failed && ' · its contents could not be loaded'}
      </p>
      <div className="library-item-choosers">
        <label className="inline-label">
          {choices?.groupLabel ?? 'Part'}
          <select
            value={group ?? ''}
            disabled={choices === null}
            aria-label={`${choices?.groupLabel ?? 'Part'} of ${item.name}`}
            onChange={(event) => chooseGroup(Number(event.target.value))}
          >
            {groups.map((entry) => (
              <option key={entry.number} value={entry.number}>
                {entry.name}
              </option>
            ))}
          </select>
        </label>
        <label className="inline-label">
          {choices?.unitLabel ?? 'Chapter'}
          <select
            value={unit ?? ''}
            disabled={choices === null}
            aria-label={`${choices?.unitLabel ?? 'Chapter'} of ${item.name}`}
            onChange={(event) => setUnit(Number(event.target.value))}
          >
            {units.map((entry) => (
              <option key={entry.number} value={entry.number}>
                {entry.label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="primary-button"
          disabled={choices === null && !failed}
          onClick={() => onRead(item.id, group ?? choices?.start.group ?? 1, unit ?? choices?.start.unit ?? 1)}
        >
          Read
        </button>
      </div>
    </li>
  )
}

export default LibraryList
