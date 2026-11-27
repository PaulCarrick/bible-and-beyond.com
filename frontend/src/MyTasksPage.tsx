import { useContext, useEffect, useState } from 'react'
import { fetchMyScheduledTasks } from './api'
import type { MemberScheduledTask } from './api'
import { AccountContext } from './AccountContext'
import type { View } from './views'

interface MyTasksPageProps {
  onNavigate: (view: View) => void
}

// "Sunday, November 29, 2026" for a date written 2026-11-29 (read as that calendar day, whatever the time zone).
function dayLabel(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString(undefined, {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
    timeZone: 'UTC',
  })
}

function TaskItem({ task }: { task: MemberScheduledTask }) {
  return (
    <li className="my-task">
      <div className="my-task-heading">
        <h3>{task.task_name}</h3>
        <span className={`my-task-status${task.confirmed ? ' is-confirmed' : ''}`}>
          {task.confirmed ? 'Confirmed' : 'Not confirmed yet'}
        </span>
      </div>
      <p className="my-task-date">
        {dayLabel(task.on_date)}
        {task.owner_name && <span className="my-task-owner"> · set by {task.owner_name}</span>}
      </p>
      {/* Both are cleaned on the server (formatted_text.clean), like the other editor text the site shows. */}
      {task.description_html && <div className="my-task-text" dangerouslySetInnerHTML={{ __html: task.description_html }} />}
      {task.note_html && (
        <div className="my-task-note">
          <strong>A note for you</strong>
          <div dangerouslySetInnerHTML={{ __html: task.note_html }} />
        </div>
      )}
    </li>
  )
}

// My scheduled tasks (in the account icon's menu when the member has some; the owner's request, 2026-11-27): the
// tasks an administrator gave this account on the Drupal Scheduled tasks page (scheduled_tasks.member_tasks), the
// coming ones soonest first with whether each is confirmed, and those of the last 60 days under Earlier. Read only.
function MyTasksPage({ onNavigate }: MyTasksPageProps) {
  const { user } = useContext(AccountContext)
  const [tasks, setTasks] = useState<{ upcoming: MemberScheduledTask[]; past: MemberScheduledTask[] } | null>(null)
  const [problem, setProblem] = useState('')

  useEffect(() => {
    if (!user) {
      return
    }
    fetchMyScheduledTasks()
      .then((found) => {
        setTasks(found)
        setProblem('')
      })
      .catch((error: Error) => setProblem(error.message))
  }, [user])

  if (!user) {
    return (
      <div className="welcome my-tasks">
        <h1>My scheduled tasks</h1>
        <p>
          The tasks you are scheduled for show here when you are logged in.{' '}
          <button type="button" className="link-button" onClick={() => onNavigate('login')}>
            Log in
          </button>
        </p>
      </div>
    )
  }

  return (
    <div className="welcome my-tasks">
      <h1>My scheduled tasks</h1>
      <p className="my-tasks-intro">
        The tasks you are scheduled for, soonest first. Each says whether it is confirmed. If a date does not suit you,
        tell the person who set it.
      </p>
      {problem && <p className="error" role="alert">{problem}</p>}
      {!tasks && !problem && <p>Loading…</p>}
      {tasks && (
        <>
          {tasks.upcoming.length > 0 ? (
            <ul className="my-tasks-list">
              {tasks.upcoming.map((task) => <TaskItem key={task.id} task={task} />)}
            </ul>
          ) : (
            <p>You have no scheduled tasks coming up.</p>
          )}
          {tasks.past.length > 0 && (
            <details className="my-tasks-past">
              <summary>Earlier ({tasks.past.length})</summary>
              <ul className="my-tasks-list">
                {tasks.past.map((task) => <TaskItem key={task.id} task={task} />)}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  )
}

export default MyTasksPage
