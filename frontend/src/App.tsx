import { useState } from 'react'
import type { FormEvent } from 'react'
import './App.css'

const mlServiceUrl = 'http://localhost:8000'

function App() {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const [isLoading, setIsLoading] = useState(false)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setIsLoading(true)
    setErrorMessage('')
    setAnswer('')

    try {
      const response = await fetch(`${mlServiceUrl}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`)
      }
      const data = await response.json()
      setAnswer(data.answer)
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : 'Something went wrong')
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <main className="ask-page">
      <h1>Bible Answers</h1>
      <form onSubmit={handleSubmit}>
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          placeholder="Ask a question about the Bible..."
          rows={4}
        />
        <button type="submit" disabled={isLoading || question.trim() === ''}>
          {isLoading ? 'Asking...' : 'Ask'}
        </button>
      </form>
      {answer && (
        <section className="answer">
          <h2>Answer</h2>
          <p>{answer}</p>
        </section>
      )}
      {errorMessage && <p className="error">{errorMessage}</p>}
    </main>
  )
}

export default App
