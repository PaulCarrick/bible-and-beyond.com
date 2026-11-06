// The bold button that follows the reader on a long read. It goes back to the top of the page; see
// useBackToTop for the Home key and for why the browser's own jump is not enough.
interface BackToTopButtonProps {
  isVisible: boolean
  onClick: () => void
}

function BackToTopButton({ isVisible, onClick }: BackToTopButtonProps) {
  return (
    <button type="button" className="primary-button back-to-top" hidden={!isVisible} onClick={onClick}>
      ↑ Back to top
    </button>
  )
}

export default BackToTopButton
