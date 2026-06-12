import test from 'node:test'
import assert from 'node:assert/strict'
import { loadWorkspace, saveWorkspace } from '../src/storage.js'

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
