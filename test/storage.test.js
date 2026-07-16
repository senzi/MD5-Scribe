import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { loadWorkspace, parseWorkspaceJSON, saveWorkspace, serializeWorkspace } from '../src/storage.js'

function installStorage(initial = {}) {
  const data = new Map(Object.entries(initial))
  globalThis.localStorage = {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, String(value)),
    removeItem: (key) => data.delete(key),
  }
  return data
}

test('migrates the legacy single task into a workspace', () => {
  const data = installStorage({
    'md5-scribe:task:v2': JSON.stringify({ message: 'legacy', completedSteps: [] }),
  })
  const workspace = loadWorkspace()
  assert.equal(workspace.tasks.length, 1)
  assert.equal(workspace.tasks[0].message, 'legacy')
  assert.equal(workspace.activeTaskId, workspace.tasks[0].id)
  assert.equal(data.has('md5-scribe:task:v2'), false)
  assert.equal(data.has('md5-scribe:workspace:v3'), true)
})

test('preserves multiple tasks and the active selection', () => {
  installStorage()
  const tasks = [
    { id: 'one', message: 'first', completedSteps: [] },
    { id: 'two', message: 'second', completedSteps: [0] },
  ]
  saveWorkspace(tasks, 'two')
  assert.deepEqual(loadWorkspace(), { tasks, activeTaskId: 'two' })
})

test('exports and imports a versioned JSON workspace', () => {
  const tasks = [{ id: 'one', message: 'hello', stageProgress: { '0:0': { attempts: 1, passed: true } } }]
  const text = serializeWorkspace(tasks, 'one')
  const parsed = parseWorkspaceJSON(text)
  assert.deepEqual(parsed, { tasks, activeTaskId: 'one' })
})

test('rejects malformed imported workspaces', () => {
  assert.throws(() => parseWorkspaceJSON('{bad json'), /不是有效的 JSON/)
  assert.throws(() => parseWorkspaceJSON('{"tasks":"nope"}'), /找不到有效的解密进度列表/)
})

test('imports the near-final interaction fixture', () => {
  const fixtureUrl = new URL('./fixtures/near-final-workspace.json', import.meta.url)
  const workspace = parseWorkspaceJSON(readFileSync(fixtureUrl, 'utf8'))
  const [task] = workspace.tasks
  assert.equal(workspace.activeTaskId, 'test-near-final-abc')
  assert.equal(task.message, 'abc')
  assert.equal(task.completedSteps.length, 63)
  assert.equal(task.currentRound, 63)
  assert.equal(task.currentStage, 5)
  assert.equal(Object.keys(task.stageProgress).length, 5)
  assert.equal(task.finalVerified, false)
})
