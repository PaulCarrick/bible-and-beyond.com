import { useRef, useState } from 'react'
import { askOpenQuestion } from './api'
import type { OpenQuestionAnswer } from './api'
import FaqAnswerView from './FaqAnswerView'
import RichTextEditor from './RichTextEditor'
import type { RichTextEditorHandle } from './RichTextEditor'

// "Ask your own question" on the FAQ page: the Quill editor and Gemini's answer. The FAQ page shows it only to
// a logged-in visitor whose account an administrator allowed (open_ai_queries); the server checks that too.
// No <form> here: the button must not submit anything around it.
function OpenQuestionBox() {
  const editorReference = useRef<RichTextEditorHandle>(null)
  const [isAsking, setIsAsking] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [answer, setAnswer] = useState<OpenQuestionAnswer | null>(null)

  function ask() {
    const editor = editorReference.current
    if (!editor || isAsking) {
      return
    }
    if (editor.isEmpty()) {
      setErrorMessage('Please write your question first.')
      return
    }
    setErrorMessage('')
    setAnswer(null)
    setIsAsking(true)
    askOpenQuestion(editor.getHtml())
      .then(setAnswer)
      .catch((error: Error) => setErrorMessage(error.message))
      .finally(() => setIsAsking(false))
  }

  return (
    <section className="open-question" aria-labelledby="open-question-heading">
      <h2 id="open-question-heading">Ask your own question</h2>
      <p id="open-question-label">
        Write a question about God, the Bible or the Christian life, up to 1,500 characters. The answer comes from the
        same AI, with the same care.
      </p>
      <RichTextEditor ref={editorReference} placeholder="Write your question here" labelledBy="open-question-label" />
      <div className="open-question-actions">
        <button type="button" className="primary-button" onClick={ask} disabled={isAsking}>
          {isAsking ? 'Asking…' : 'Ask'}
        </button>
        {answer && !isAsking && (
          <button
            type="button"
            className="link-button"
            onClick={() => {
              editorReference.current?.clear()
              setAnswer(null)
            }}
          >
            Ask another question
          </button>
        )}
      </div>
      <div aria-live="polite">
        {isAsking && <p className="faq-waiting">Writing the answer. This can take up to half a minute…</p>}
        {errorMessage && <p className="error">{errorMessage}</p>}
        {answer && !isAsking && <FaqAnswerView question={answer.question} answer={answer.answer} references={answer.references} />}
      </div>
    </section>
  )
}

export default OpenQuestionBox
