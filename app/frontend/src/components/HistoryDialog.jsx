import { useEffect, useId, useRef } from 'react'
import { StationHistory } from './Views.jsx'
import './HistoryDialog.css'

export default function HistoryDialog({ state, dispatch }) {
  const dialogRef = useRef(null)
  const closeButtonRef = useRef(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = dialogRef.current
    const trigger = document.activeElement
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    dialog.showModal()
    closeButtonRef.current.focus()

    return () => {
      dialog.close()
      document.body.style.overflow = previousOverflow
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus()
    }
  }, [])

  const close = () => dispatch({ type: 'closeHistory' })

  return <dialog ref={dialogRef} className="history-dialog" aria-labelledby={titleId}
    onCancel={(event) => {
      event.preventDefault()
      close()
    }}
    onKeyDown={(event) => {
      if (event.key === 'Escape') event.stopPropagation()
    }}>
    <header className="history-dialog-header">
      <h2 id={titleId}>Station history</h2>
      <button ref={closeButtonRef} type="button" className="history-dialog-close" aria-label="Close history" onClick={close}>
        <span aria-hidden="true">×</span> Close
      </button>
    </header>
    <div className="history-dialog-content">
      <StationHistory state={state} dispatch={dispatch} />
    </div>
  </dialog>
}
