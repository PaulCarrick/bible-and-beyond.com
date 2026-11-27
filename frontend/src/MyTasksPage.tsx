import { useContext, useEffect, useState } from 'react'
import { fetchMyScheduledTasks, fetchOfferedTasks, requestScheduledTask, withdrawScheduledTask } from './api'
import type { MemberScheduledTask, OfferedTask } from './api'
import { AccountContext } from './AccountContext'
import type { View } from './views'

interface MyTasksPageProps {
  onNavigate: (view: View) => void
}

type TaskLists = { upcoming: MemberScheduledTask[]; past: MemberScheduledTask[] }

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

interface TaskItemProps {
  task: MemberScheduledTask
  // Coming tasks can be removed; past ones cannot.
  onRemove?: (task: MemberScheduledTask) => Promise<void>
}

function TaskItem({ task, onRemove }: TaskItemProps) {
  const [isConfirming, setIsConfirming] = useState(false)
  const [isBusy, setIsBusy] = useState(false)

  async function remove() {
    if (!onRemove) {
      return
    }
    setIsBusy(true)
    try {
      await onRemove(task)
    } finally {
      setIsBusy(false)
      setIsConfirming(false)
    }
  }

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
      {onRemove && (
        <div className="my-task-actions">
          {isConfirming ? (
            <>
              <span>Take yourself off this task? Your group leader will be told by email.</span>
              <button type="button" className="secondary-button small-button danger-button" disabled={isBusy} onClick={remove}>
                Yes, remove it
              </button>
              <button type="button" className="secondary-button small-button" disabled={isBusy} onClick={() => setIsConfirming(false)}>
                Cancel
              </button>
            </>
          ) : (
            <button
              type="button"
              className="secondary-button small-button"
              aria-label={`Remove ${task.task_name} on ${dayLabel(task.on_date)}`}
              onClick={() => setIsConfirming(true)}
            >
              Remove
            </button>
          )}
        </div>
      )}
    </li>
  )
}

interface AddTaskBoxProps {
  onSaved: (lists: TaskLists, message: string) => void
  onCancel: () => void
}

// Add a task: a task (the tasks of the member's group leaders), then one of its dates in the next two months that
// the member does not have yet, then Save. It is added not confirmed and the group leader is emailed. No form element.
function AddTaskBox({ onSaved, onCancel }: AddTaskBoxProps) {
  const [offered, setOffered] = useState<OfferedTask[] | null>(null)
  const [taskId, setTaskId] = useState('')
  const [onDate, setOnDate] = useState('')
  const [problem, setProblem] = useState('')
  const [isSaving, setIsSaving] = useState(false)

  useEffect(() => {
    fetchOfferedTasks()
      .then(setOffered)
      .catch((error: Error) => setProblem(error.message))
  }, [])

  const chosen = offered?.find((task) => String(task.id) === taskId)

  async function save() {
    if (!chosen || !onDate) {
      return
    }
    setIsSaving(true)
    setProblem('')
    try {
      const lists = await requestScheduledTask(chosen.id, onDate)
      const label = chosen.dates.find((day) => day.value === onDate)?.label ?? dayLabel(onDate)
      onSaved(lists, `You asked for ${chosen.name} on ${label}. It is not confirmed yet: your group leader has been emailed, and you will be told when they confirm it.`)
    } catch (error) {
      setProblem((error as Error).message)
      setIsSaving(false)
    }
  }

  return (
    <div className="my-task-add" role="group" aria-labelledby="my-task-add-heading">
      <h2 id="my-task-add-heading">Add a task</h2>
      {!offered && !problem && <p>Loading…</p>}
      {offered && offered.length === 0 && (
        <p>There are no tasks with free dates in the next two months.</p>
      )}
      {offered && offered.length > 0 && (
        <div className="my-task-add-fields">
          <label>
            Task
            <select
              value={taskId}
              onChange={(event) => {
                setTaskId(event.target.value)
                setOnDate('')
              }}
            >
              <option value="">- Choose a task -</option>
              {offered.map((task) => (
                <option key={task.id} value={task.id}>{task.name}</option>
              ))}
            </select>
          </label>
          <label>
            Date
            <select value={onDate} onChange={(event) => setOnDate(event.target.value)} disabled={!chosen}>
              <option value="">{chosen ? '- Choose a date -' : 'Choose a task first'}</option>
              {chosen?.dates.map((day) => (
                <option key={day.value} value={day.value}>{day.label}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      {problem && <p className="error" role="alert">{problem}</p>}
      <div className="my-task-add-buttons">
        <button type="button" className="primary-button" disabled={!chosen || !onDate || isSaving} onClick={save}>
          {isSaving ? 'Saving…' : 'Save'}
        </button>
        <button type="button" className="secondary-button" disabled={isSaving} onClick={onCancel}>
          Cancel
        </button>
      </div>
    </div>
  )
}

// My scheduled tasks (in the account icon's menu for a member of at least one group; the owner's request, 2026-11-27): the
// tasks an administrator gave this account on the Drupal Scheduled tasks page (scheduled_tasks.member_tasks), the
// coming ones soonest first with whether each is confirmed, and those of the last 60 days under Earlier. A member of a
// group can also ask for a task (Add a task) and take themselves off a coming one (Remove); their group leader is
// emailed either way, and the member is emailed when the leader confirms (member_task_requests.py).
function MyTasksPage({ onNavigate }: MyTasksPageProps) {
  const { user } = useContext(AccountContext)
  const [tasks, setTasks] = useState<TaskLists | null>(null)
  const [problem, setProblem] = useState('')
  const [message, setMessage] = useState('')
  const [isAdding, setIsAdding] = useState(false)

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

  async function remove(task: MemberScheduledTask) {
    try {
      setTasks(await withdrawScheduledTask(task.id))
      setProblem('')
      setMessage(`You are off ${task.task_name} on ${dayLabel(task.on_date)}. Your group leader has been emailed.`)
    } catch (error) {
      setProblem((error as Error).message)
    }
  }

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
        The tasks you are scheduled for, soonest first. Each says whether it is confirmed.
        {user.in_a_group && ' You can ask for a task with Add a task, or take yourself off one with Remove; your group leader is emailed either way.'}
      </p>
      {user.in_a_group && !isAdding && (
        <p>
          <button
            type="button"
            className="primary-button"
            onClick={() => {
              setIsAdding(true)
              setMessage('')
            }}
          >
            Add a task
          </button>
        </p>
      )}
      {isAdding && (
        <AddTaskBox
          onSaved={(lists, words) => {
            setTasks(lists)
            setMessage(words)
            setIsAdding(false)
          }}
          onCancel={() => setIsAdding(false)}
        />
      )}
      {message && <p className="success" role="status">{message}</p>}
      {problem && <p className="error" role="alert">{problem}</p>}
      {!tasks && !problem && <p>Loading…</p>}
      {tasks && (
        <>
          {tasks.upcoming.length > 0 ? (
            <ul className="my-tasks-list">
              {tasks.upcoming.map((task) => <TaskItem key={task.id} task={task} onRemove={remove} />)}
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
