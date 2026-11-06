import type { Translation } from './types'

// The Bible that a verse from a commentary is shown in: the BSB, else the first Bible on this site.
export function chooseContextTranslation(translations: Translation[]) {
  const local = translations.filter((translation) => translation.source === 'local')
  return (local.find((translation) => translation.code === 'BSB') ?? local[0])?.code ?? 'BSB'
}
