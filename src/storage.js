const WORKSPACE_KEY = 'md5-scribe:workspace:v3'
const LEGACY_TASK_KEY = 'md5-scribe:task:v2'

const createId = () => globalThis.crypto?.randomUUID?.() || `task-${Date.now()}-${Math.random().toString(16).slice(2)}`

function normalizeTask(task) {
  return {
    ...task,
    id: task.id || createId(),
  }
}

export function loadWorkspace() {
  try {
    const raw = localStorage.getItem(WORKSPACE_KEY)
    if (raw) {
      const workspace = JSON.parse(raw)
      const tasks = Array.isArray(workspace.tasks) ? workspace.tasks.map(normalizeTask) : []
      const activeTaskId = tasks.some((task) => task.id === workspace.activeTaskId)
        ? workspace.activeTaskId
        : tasks[0]?.id || null
      return { tasks, activeTaskId }
    }

    const legacyRaw = localStorage.getItem(LEGACY_TASK_KEY)
    if (legacyRaw) {
      const task = normalizeTask(JSON.parse(legacyRaw))
      const workspace = { tasks: [task], activeTaskId: task.id }
      localStorage.setItem(WORKSPACE_KEY, JSON.stringify(workspace))
      localStorage.removeItem(LEGACY_TASK_KEY)
      return workspace
    }
  } catch {
    // Corrupt local data should not prevent the app from starting.
  }
  return { tasks: [], activeTaskId: null }
}

export function saveWorkspace(tasks, activeTaskId) {
  localStorage.setItem(WORKSPACE_KEY, JSON.stringify({ tasks, activeTaskId }))
}
