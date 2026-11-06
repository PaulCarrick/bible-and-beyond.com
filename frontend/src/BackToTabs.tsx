// The bold button that follows the reader on a long read. It goes back to the tabs at the top of the
// page; see useBackToTabs for the Home key and for why the browser's own jump is not enough.
interface BackToTabsButtonProps {
  isVisible: boolean
  onClick: () => void
}

function BackToTabsButton({ isVisible, onClick }: BackToTabsButtonProps) {
  return (
    <button type="button" className="primary-button back-to-top" hidden={!isVisible} onClick={onClick}>
      ↑ Back to tabs
    </button>
  )
}

export default BackToTabsButton
