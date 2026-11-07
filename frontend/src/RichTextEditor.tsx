import { useEffect, useImperativeHandle, useRef } from 'react'
import type { Ref } from 'react'
import Quill from 'quill'
import 'quill/dist/quill.snow.css'

// What a page can ask of the editor.
export interface RichTextEditorHandle {
  // The text as a little clean HTML (paragraphs, bold, italic, links, lists...).
  getHtml: () => string
  isEmpty: () => boolean
  clear: () => void
  // Puts saved HTML into the editor, to be changed.
  setHtml: (html: string) => void
}

interface RichTextEditorProps {
  ref?: Ref<RichTextEditorHandle>
  placeholder: string
  // Names the editor for people who cannot see it.
  labelledBy: string
}

// The editor used for the contact message and for notes: Quill, with the toolbar of bold, italic, strike,
// link, heading, quote, code, lists, undo and redo.
function RichTextEditor({ ref, placeholder, labelledBy }: RichTextEditorProps) {
  const toolbarReference = useRef<HTMLDivElement>(null)
  const editorReference = useRef<HTMLDivElement>(null)
  const quillReference = useRef<Quill | null>(null)

  useEffect(() => {
    if (quillReference.current || !editorReference.current || !toolbarReference.current) {
      return
    }
    quillReference.current = new Quill(editorReference.current, {
      theme: 'snow',
      modules: { toolbar: toolbarReference.current, history: { delay: 1000, maxStack: 100 } },
      placeholder,
    })
  }, [placeholder])

  useImperativeHandle(ref, () => ({
    getHtml: () => quillReference.current?.getSemanticHTML() ?? '',
    isEmpty: () => (quillReference.current?.getText().trim() ?? '') === '',
    clear: () => quillReference.current?.setText(''),
    setHtml: (html: string) => {
      const quill = quillReference.current
      if (quill) {
        quill.setContents(quill.clipboard.convert({ html }), 'silent')
        quill.history.clear()
      }
    },
  }))

  return (
    <div className="contact-editor" role="group" aria-labelledby={labelledBy}>
      <div ref={toolbarReference} className="contact-toolbar">
        <span className="ql-formats">
          <button type="button" className="ql-bold" aria-label="Bold" />
          <button type="button" className="ql-italic" aria-label="Italic" />
          <button type="button" className="ql-strike" aria-label="Strikethrough" />
          <button type="button" className="ql-link" aria-label="Link" />
        </span>
        <span className="ql-formats">
          <button type="button" className="ql-header" value="2" aria-label="Heading" />
          <button type="button" className="ql-blockquote" aria-label="Quote" />
          <button type="button" className="ql-code-block" aria-label="Code" />
          <button type="button" className="ql-list" value="bullet" aria-label="Bulleted list" />
          <button type="button" className="ql-list" value="ordered" aria-label="Numbered list" />
        </span>
        <span className="ql-formats">
          <button type="button" onClick={() => quillReference.current?.history.undo()} aria-label="Undo">
            ↶
          </button>
          <button type="button" onClick={() => quillReference.current?.history.redo()} aria-label="Redo">
            ↷
          </button>
        </span>
      </div>
      <div ref={editorReference} className="contact-text" />
    </div>
  )
}

export default RichTextEditor
