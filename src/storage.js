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

export function serializeWorkspace(tasks, activeTaskId) {
  return JSON.stringify({
    format: 'md5-scribe-workspace',
    version: 4,
    exportedAt: new Date().toISOString(),
    activeTaskId,
    tasks,
  }, null, 2)
}

export function parseWorkspaceJSON(text) {
  let parsed
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new Error('这个文件不是有效的 JSON。')
  }
  if (!parsed || !Array.isArray(parsed.tasks)) throw new Error('找不到有效的解密进度列表。')
  const tasks = parsed.tasks.filter((task) => task && typeof task.message === 'string').map(normalizeTask)
  if (tasks.length !== parsed.tasks.length) throw new Error('部分工单数据格式不正确，未执行导入。')
  const activeTaskId = tasks.some((task) => task.id === parsed.activeTaskId) ? parsed.activeTaskId : tasks[0]?.id || null
  return { tasks, activeTaskId }
}
