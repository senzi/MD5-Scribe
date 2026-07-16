<script setup>
import { computed, nextTick, ref, watch } from 'vue'
import { bin32, computeMd5, diffBits, hex32 } from './md5.js'
import { loadWorkspace, parseWorkspaceJSON, saveWorkspace, serializeWorkspace } from './storage.js'

const MAX_BYTES = 55
const STAGES = [
  { short: 'f', label: '逻辑函数' },
  { short: 'T1', label: 'A + f' },
  { short: 'T2', label: 'T1 + Mⱼ' },
  { short: 'T3', label: 'T2 + Kᵢ' },
  { short: 'ROT', label: '循环左移' },
  { short: 'B′', label: 'ROT + B' },
]
const encoder = new TextEncoder()

function createId() {
  return globalThis.crypto?.randomUUID?.() || `task-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function prepareTask(raw) {
  const task = {
    id: raw.id || createId(),
    message: raw.message || '',
    stageProgress: raw.stageProgress && typeof raw.stageProgress === 'object' ? raw.stageProgress : {},
    completedSteps: Array.isArray(raw.completedSteps) ? raw.completedSteps : [],
    logs: Array.isArray(raw.logs) ? raw.logs : [],
    createdAt: raw.createdAt || Date.now(),
    updatedAt: raw.updatedAt || Date.now(),
    currentRound: Number.isInteger(raw.currentRound) ? raw.currentRound : 0,
    currentStage: Number.isInteger(raw.currentStage) ? raw.currentStage : 0,
    finalVerified: Boolean(raw.finalVerified),
    finalStatus: raw.finalStatus || 'idle',
    finalAttempts: Number(raw.finalAttempts) || 0,
    ...raw,
  }

  // A completed round from the older version becomes six completed game cells.
  for (const round of task.completedSteps) {
    for (let stage = 0; stage < STAGES.length; stage += 1) {
      task.stageProgress[`${round}:${stage}`] ||= { attempts: 1, passed: true, hadError: false }
    }
  }
  return task
}

const saved = loadWorkspace()
const tasks = ref(saved.tasks.map(prepareTask))
const activeTaskId = ref(saved.activeTaskId || tasks.value[0]?.id || null)
const view = ref('lobby')
const roundIndex = ref(0)
const stageIndex = ref(0)
const messageInput = ref('')
const notice = ref('')
const progressOpen = ref(false)
const answer = ref('')
const feedback = ref(null)
const answerInput = ref(null)
const importInput = ref(null)
const scratchButtons = ref([])
const rotationBitInputs = ref([])
const finalMode = ref(false)
const activeEntry = ref({ type: 'answer', index: null })

const carryMarks = ref(Array(8).fill(''))
const addScratch = ref(Array(8).fill(''))
const logicScratch = ref(Array(32).fill(''))
const rotationBits = ref(Array(32).fill(''))
const rotationPointer = ref(null)
const activeRotationBit = ref(0)
const additionScratchLinked = ref(false)

const activeTask = computed(() => tasks.value.find((item) => item.id === activeTaskId.value) || null)
const result = computed(() => activeTask.value ? computeMd5(activeTask.value.message) : null)
const currentRound = computed(() => result.value?.steps[roundIndex.value] || null)
const messageBytes = computed(() => encoder.encode(messageInput.value).length)

function keyFor(round, stage) {
  return `${round}:${stage}`
}

function entryAt(round, stage) {
  return activeTask.value?.stageProgress?.[keyFor(round, stage)] || null
}

function cellStatus(round, stage) {
  const entry = entryAt(round, stage)
  if (!entry?.attempts) return 'idle'
  if (entry.hadError || !entry.passed) return 'error'
  return 'success'
}

function isPassed(round, stage) {
  return Boolean(entryAt(round, stage)?.passed)
}

function firstIncomplete(task = activeTask.value) {
  if (!task) return { round: 0, stage: 0 }
  for (let round = 0; round < 64; round += 1) {
    for (let stage = 0; stage < STAGES.length; stage += 1) {
      if (!task.stageProgress?.[keyFor(round, stage)]?.passed) return { round, stage }
    }
  }
  return null
}

function isSelectable(round, stage) {
  if (isPassed(round, stage)) return true
  const next = firstIncomplete()
  return Boolean(next && next.round === round && next.stage === stage)
}

const completedCells = computed(() => {
  if (!activeTask.value) return 0
  return Object.values(activeTask.value.stageProgress || {}).filter((entry) => entry?.passed).length
})

const completedRounds = computed(() => {
  let count = 0
  for (let round = 0; round < 64; round += 1) {
    if (STAGES.every((_, stage) => isPassed(round, stage))) count += 1
  }
  return count
})

const allStagesPassed = computed(() => completedCells.value === 64 * STAGES.length)

const stageSpec = computed(() => {
  const step = currentRound.value
  if (!step) return null
  const [a, b, c, d] = step.registersBefore
  const [t1, t2, t3, rotated, bNew] = step.correctAtoms
  const common = { round: roundIndex.value + 1, stage: stageIndex.value + 1 }

  switch (stageIndex.value) {
    case 0:
      return {
        ...common,
        kind: 'logic',
        title: `求 ${step.logicFunc}(B, C, D)`,
        prompt: '逐位完成本轮逻辑函数，写出 32 位结果。',
        formula: step.logicFunc === 'F' ? '(B ∧ C) ∨ (¬B ∧ D)' : step.logicFunc === 'G' ? '(B ∧ D) ∨ (C ∧ ¬D)' : step.logicFunc === 'H' ? 'B ⊕ C ⊕ D' : 'C ⊕ (B ∨ ¬D)',
        expected: step.fValue,
        rows: [
          { name: 'B', value: b },
          { name: 'C', value: c },
          { name: 'D', value: d },
        ],
      }
    case 1:
      return { ...common, kind: 'addition', title: '计算 T1 = A + f', prompt: '从右向左逐列相加，溢出部分按 32 位截断。', expected: t1, operands: [{ name: 'A', value: a }, { name: 'f', value: step.fValue }] }
    case 2:
      return { ...common, kind: 'addition', title: '计算 T2 = T1 + Mⱼ', prompt: `本轮使用消息字 M[${step.mjIdx}]。`, expected: t2, operands: [{ name: 'T1', value: t1 }, { name: `M[${step.mjIdx}]`, value: step.mj }] }
    case 3:
      return { ...common, kind: 'addition', title: '计算 T3 = T2 + Kᵢ', prompt: '加入本轮正弦常量，保留低 32 位。', expected: t3, operands: [{ name: 'T2', value: t2 }, { name: `K${roundIndex.value}`, value: step.ki }] }
    case 4:
      return { ...common, kind: 'rotation', title: `循环左移 ${step.shift} 位`, prompt: '可先填二进制草稿，再点选移位后成为最高位的位置。', expected: rotated, source: t3, shift: step.shift }
    default:
      return { ...common, kind: 'addition', title: '计算新的 B′ = ROT + B', prompt: '完成本轮最后一次 32 位加法。', expected: bNew, operands: [{ name: 'ROT', value: rotated }, { name: 'B', value: b }] }
  }
})

const rotatedGroups = computed(() => {
  if (rotationPointer.value === null || rotationBits.value.some((bit) => bit === '')) return []
  const arranged = [...rotationBits.value.slice(rotationPointer.value), ...rotationBits.value.slice(0, rotationPointer.value)]
  return Array.from({ length: 8 }, (_, index) => arranged.slice(index * 4, index * 4 + 4).join(''))
})

function persist() {
  const task = activeTask.value
  if (!task) return
  task.updatedAt = Date.now()
  task.currentRound = roundIndex.value
  task.currentStage = stageIndex.value
  saveWorkspace(tasks.value, task.id)
}

function resetQuestion() {
  answer.value = ''
  feedback.value = null
  activeEntry.value = { type: 'answer', index: null }
  carryMarks.value = Array(8).fill('')
  additionScratchLinked.value = false
  addScratch.value = Array(8).fill('')
  logicScratch.value = Array(32).fill('')
  rotationBits.value = Array(32).fill('')
  rotationPointer.value = null
  activeRotationBit.value = 0
  if (finalMode.value && activeTask.value?.finalVerified && result.value) {
    answer.value = result.value.digest.toUpperCase()
    feedback.value = { ok: true, message: '该工单此前已验证通过，已自动恢复最终 MD5 摘要。' }
  }
}

watch([activeTaskId, roundIndex, stageIndex, finalMode], resetQuestion)

function startTask() {
  notice.value = ''
  if (!messageInput.value) return
  if (messageBytes.value > MAX_BYTES) {
    notice.value = `字符串超过单块上限，请缩短到 ${MAX_BYTES} bytes 以内。`
    return
  }
  const now = Date.now()
  const task = prepareTask({
    id: createId(),
    message: messageInput.value,
    stageProgress: {},
    completedSteps: [],
    logs: [],
    createdAt: now,
    updatedAt: now,
  })
  tasks.value.unshift(task)
  activeTaskId.value = task.id
  roundIndex.value = 0
  stageIndex.value = 0
  finalMode.value = false
  messageInput.value = ''
  view.value = 'game'
  persist()
}

function openTask(task) {
  activeTaskId.value = task.id
  const next = firstIncomplete(task)
  roundIndex.value = next?.round ?? Math.min(task.currentRound || 0, 63)
  stageIndex.value = next?.stage ?? Math.min(task.currentStage || 0, STAGES.length - 1)
  finalMode.value = !next
  view.value = 'game'
  notice.value = ''
  saveWorkspace(tasks.value, task.id)
}

function switchTask(task) {
  persist()
  openTask(task)
}

function removeTask(task) {
  if (!globalThis.confirm(`删除“${task.message}”及其全部进度？`)) return
  tasks.value = tasks.value.filter((item) => item.id !== task.id)
  if (activeTaskId.value === task.id) activeTaskId.value = tasks.value[0]?.id || null
  saveWorkspace(tasks.value, activeTaskId.value)
}

function goLobby() {
  persist()
  view.value = 'lobby'
  finalMode.value = false
}

function selectCell(round, stage) {
  if (!isSelectable(round, stage)) return
  finalMode.value = false
  roundIndex.value = round
  stageIndex.value = stage
  persist()
}

function sanitizeHex(value, limit = 8) {
  return String(value).toUpperCase().replace(/[^0-9A-F]/g, '').slice(0, limit)
}

function setAnswer(value) {
  answer.value = sanitizeHex(value, finalMode.value ? 32 : 8)
  activeEntry.value = { type: 'answer', index: null }
}

function keypad(key) {
  if (activeEntry.value.type === 'scratch' && stageSpec.value?.kind === 'addition') {
    const index = activeEntry.value.index
    if (key === 'backspace' || key === 'clear') updateAdditionScratch(index, '')
    else if (/^[0-9A-F]$/.test(key)) {
      updateAdditionScratch(index, key)
      focusAdditionScratch(Math.max(0, index - 1))
    }
    return
  }
  if (key === 'backspace') answer.value = answer.value.slice(0, -1)
  else if (key === 'clear') answer.value = ''
  else answer.value = sanitizeHex(answer.value + key, finalMode.value ? 32 : 8)
  activeEntry.value = { type: 'answer', index: null }
}

function updateAdditionScratch(index, value) {
  addScratch.value[index] = value
  if (!additionScratchLinked.value && addScratch.value.every(Boolean)) additionScratchLinked.value = true
  if (additionScratchLinked.value) answer.value = addScratch.value.join('')
}

function focusAdditionScratch(index) {
  activeEntry.value = { type: 'scratch', index }
  nextTick(() => scratchButtons.value[index]?.focus())
}

function additionScratchKeydown(event) {
  if (activeEntry.value.type !== 'scratch') return
  const key = event.key.toUpperCase()
  if (/^[0-9A-F]$/.test(key)) {
    event.preventDefault()
    keypad(key)
  } else if (event.key === 'Backspace' || event.key === 'Delete') {
    event.preventDefault()
    keypad('backspace')
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    focusAdditionScratch(Math.max(0, activeEntry.value.index - 1))
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    focusAdditionScratch(Math.min(7, activeEntry.value.index + 1))
  }
}

function toggleCarry(index) {
  carryMarks.value[index] = carryMarks.value[index] === '' ? '1' : ''
}

function toggleBit(collection, index) {
  const next = collection[index] === '' ? '0' : collection[index] === '0' ? '1' : ''
  collection[index] = next
}

function copyLogicBit(bit, index) {
  logicScratch.value[index] = bit
}

function focusRotationBit(index) {
  const nextIndex = Math.max(0, Math.min(31, index))
  activeRotationBit.value = nextIndex
  nextTick(() => rotationBitInputs.value[nextIndex]?.focus())
}

function setRotationBit(index, bit, advance = true) {
  rotationBits.value[index] = bit
  focusRotationBit(advance ? index + 1 : index)
}

function rotationBitKeydown(event, index) {
  if (event.key === '1' || event.key === 'ArrowUp') {
    event.preventDefault()
    setRotationBit(index, '1')
  } else if (event.key === '0' || event.key === 'ArrowDown') {
    event.preventDefault()
    setRotationBit(index, '0')
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault()
    focusRotationBit(index - 1)
  } else if (event.key === 'ArrowRight') {
    event.preventDefault()
    focusRotationBit(index + 1)
  }
}

async function verifyCurrent() {
  const normalized = sanitizeHex(answer.value, 8)
  answer.value = normalized
  if (normalized.length !== 8) {
    feedback.value = { ok: false, format: true, message: '最终答案需要恰好 8 位十六进制。' }
    return
  }
  const expected = stageSpec.value.expected >>> 0
  const actual = Number.parseInt(normalized, 16) >>> 0
  const ok = expected === actual
  const key = keyFor(roundIndex.value, stageIndex.value)
  const previous = activeTask.value.stageProgress[key] || { attempts: 0, passed: false, hadError: false }
  const attempts = previous.attempts + 1
  activeTask.value.stageProgress[key] = {
    attempts,
    passed: previous.passed || ok,
    hadError: previous.hadError || !ok,
    lastAnswer: normalized,
    verifiedAt: Date.now(),
  }
  if (!ok) {
    activeTask.value.logs.push({
      timestamp: new Date().toISOString(),
      round: roundIndex.value,
      stage: stageIndex.value,
      atomName: STAGES[stageIndex.value].label,
      expected: hex32(expected),
      actual: hex32(actual),
      diffBits: diffBits(expected, actual),
    })
  }

  const roundComplete = STAGES.every((_, index) => activeTask.value.stageProgress[keyFor(roundIndex.value, index)]?.passed)
  if (roundComplete && !activeTask.value.completedSteps.includes(roundIndex.value)) {
    activeTask.value.completedSteps.push(roundIndex.value)
    activeTask.value.completedSteps.sort((a, b) => a - b)
  }
  feedback.value = ok
    ? { ok: true, message: previous.hadError ? '答案正确。这一格保留橙色，记录本题曾经出错。' : '一次通过，进度格已点亮为绿色。' }
    : { ok: false, message: `还差一点：有 ${diffBits(expected, actual)} 个二进制位不同。草稿不会参与判定。` }
  persist()
  await nextTick()
  answerInput.value?.focus()
}

function advance() {
  if (!isPassed(roundIndex.value, stageIndex.value)) return
  if (stageIndex.value < STAGES.length - 1) stageIndex.value += 1
  else if (roundIndex.value < 63) {
    roundIndex.value += 1
    stageIndex.value = 0
  } else finalMode.value = true
  persist()
}

function openFinal() {
  if (!allStagesPassed.value) return
  finalMode.value = true
}

function verifyFinal() {
  const normalized = sanitizeHex(answer.value, 32)
  answer.value = normalized
  if (normalized.length !== 32) {
    feedback.value = { ok: false, format: true, message: '最终摘要需要恰好 32 位十六进制。' }
    return
  }
  const ok = normalized.toLowerCase() === result.value.digest
  activeTask.value.finalAttempts += 1
  activeTask.value.finalVerified = ok || activeTask.value.finalVerified
  if (!ok) activeTask.value.finalStatus = 'error'
  else if (activeTask.value.finalStatus !== 'error') activeTask.value.finalStatus = 'success'
  feedback.value = ok
    ? { ok: true, message: '解密工单完成。最终 MD5 摘要验证通过。' }
    : { ok: false, message: '摘要不匹配。请检查四个寄存器的小端序拼接。' }
  persist()
}

function exportJSON() {
  const blob = new Blob([serializeWorkspace(tasks.value, activeTaskId.value)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `md5-scribe-progress-${new Date().toISOString().slice(0, 10)}.json`
  anchor.click()
  URL.revokeObjectURL(url)
}

async function importJSON(event) {
  const file = event.target.files?.[0]
  event.target.value = ''
  if (!file) return
  try {
    const imported = parseWorkspaceJSON(await file.text())
    tasks.value = imported.tasks.map(prepareTask)
    activeTaskId.value = imported.activeTaskId || tasks.value[0]?.id || null
    saveWorkspace(tasks.value, activeTaskId.value)
    view.value = 'lobby'
    notice.value = `已导入 ${tasks.value.length} 个解密进度。`
  } catch (error) {
    notice.value = error instanceof Error ? error.message : 'JSON 导入失败。'
  }
}

function formatTime(value) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }).format(value)
}

function taskCellCount(task) {
  return Object.values(task.stageProgress || {}).filter((entry) => entry?.passed).length
}
</script>

<template>
  <div class="app-shell has-reference">
    <header class="topbar">
      <button class="brand" type="button" @click="goLobby">
        <span class="brand-mark">MD5</span>
        <span><strong>MD5 SCRIBE</strong><small>手算解密训练场</small></span>
      </button>
      <div v-if="view === 'game' && tasks.length > 1" class="task-tabs" aria-label="切换解密进度">
        <button v-for="item in tasks" :key="item.id" type="button" :class="{ active: item.id === activeTaskId }" @click="switchTask(item)">{{ item.message || '空字符串' }}</button>
      </div>
      <div class="top-actions">
        <button type="button" class="text-button" @click="importInput?.click()">导入 JSON</button>
        <button type="button" class="text-button" :disabled="!tasks.length" @click="exportJSON">导出 JSON</button>
      </div>
      <input ref="importInput" class="visually-hidden" type="file" accept="application/json,.json" @change="importJSON" />
    </header>

    <main v-if="view === 'lobby'" class="lobby">
      <div v-if="notice" class="notice">{{ notice }}</div>
      <section class="lobby-intro">
        <span class="eyebrow">LOCAL DESKTOP GAME</span>
        <h1>把 MD5 的 384 个小步骤<br />一格一格点亮。</h1>
        <p>每次只解决一个问题。草稿随便写，系统只检查最终答案。</p>
      </section>

      <div class="lobby-grid">
        <section class="new-mission panel">
          <div class="panel-number">NEW</div>
          <h2>创建解密工单</h2>
          <label for="message">要计算的字符串</label>
          <input id="message" v-model="messageInput" type="text" placeholder="例如：hello" autofocus @keydown.enter="startTask" />
          <div class="byte-meta"><span>UTF-8 单块长度</span><strong :class="{ over: messageBytes > MAX_BYTES }">{{ messageBytes }} / {{ MAX_BYTES }} bytes</strong></div>
          <div class="byte-track"><span :class="{ over: messageBytes > MAX_BYTES }" :style="{ width: `${Math.min(messageBytes / MAX_BYTES * 100, 100)}%` }"></span></div>
          <p class="field-note">练习限定在一个 MD5 消息块内。</p>
          <button class="primary-button" type="button" :disabled="!messageInput || messageBytes > MAX_BYTES" @click="startTask">进入工单</button>
        </section>

        <section class="missions panel">
          <div class="section-title-row"><div><span class="eyebrow">SAVED RUNS</span><h2>解密进度</h2></div><span class="mission-count">{{ tasks.length }}</span></div>
          <div v-if="tasks.length" class="mission-list">
            <article v-for="item in tasks" :key="item.id" class="mission-row">
              <button class="mission-main" type="button" @click="openTask(item)">
                <span class="mission-message">“{{ item.message || '空字符串' }}”</span>
                <span class="mission-progress"><i><b :style="{ width: `${taskCellCount(item) / 384 * 100}%` }"></b></i>{{ taskCellCount(item) }} / 384</span>
                <span class="mission-time">{{ formatTime(item.updatedAt) }}</span>
              </button>
              <button class="delete-button" type="button" aria-label="删除工单" @click="removeTask(item)">×</button>
            </article>
          </div>
          <div v-else class="empty-missions"><span>00</span><p>还没有工单。创建一个字符串，第一格就会解锁。</p></div>
        </section>
      </div>
    </main>

    <main v-else-if="activeTask && result" class="game">
      <section class="progress-deck" :class="{ collapsed: !progressOpen }">
        <div class="progress-heading">
          <div><span class="eyebrow">WORKSHEET MATRIX</span><h2>工单进度</h2></div>
          <div class="progress-summary"><strong>{{ completedCells }}</strong><span>/ 384 小题</span><strong>{{ completedRounds }}</strong><span>/ 64 轮</span></div>
          <div class="legend"><span><i class="idle"></i>未开始</span><span><i class="success"></i>一次通过</span><span><i class="error"></i>曾经出错</span></div>
          <button type="button" class="progress-toggle" :aria-expanded="progressOpen" @click="progressOpen = !progressOpen">{{ progressOpen ? '收起矩阵 ↑' : '展开矩阵 ↓' }}</button>
        </div>
        <div v-show="progressOpen" class="matrix-scroll">
          <div class="progress-matrix">
            <div class="corner-cell">步骤 / 轮次</div>
            <div v-for="round in 64" :key="`head-${round}`" class="round-head" :class="{ current: round - 1 === roundIndex }">{{ String(round).padStart(2, '0') }}</div>
            <template v-for="(stage, sIndex) in STAGES" :key="stage.short">
              <div class="stage-head"><strong>{{ stage.short }}</strong><span>{{ stage.label }}</span></div>
              <button v-for="round in 64" :key="`${sIndex}-${round}`" type="button" class="progress-cell" :class="[cellStatus(round - 1, sIndex), { active: round - 1 === roundIndex && sIndex === stageIndex && !finalMode, locked: !isSelectable(round - 1, sIndex) }]" :disabled="!isSelectable(round - 1, sIndex)" :aria-label="`第 ${round} 轮，${stage.label}，${cellStatus(round - 1, sIndex)}`" @click="selectCell(round - 1, sIndex)"></button>
            </template>
          </div>
        </div>
      </section>

      <section class="question-layout">
        <aside class="round-rail">
          <button type="button" class="back-lobby" @click="goLobby">← 工单列表</button>
          <div class="round-number"><small>ROUND</small><strong>{{ String(roundIndex + 1).padStart(2, '0') }}</strong><span>/ 64</span></div>
          <div class="rail-message"><small>原始字符串</small><p>“{{ activeTask.message || '空字符串' }}”</p><span>{{ encoder.encode(activeTask.message).length }} bytes</span></div>
          <div v-if="currentRound" class="rail-params"><div><span>函数</span><b>{{ currentRound.logicFunc }}</b></div><div><span>Mⱼ</span><b>{{ currentRound.mjIdx }}</b></div><div><span>移位</span><b>{{ currentRound.shift }}</b></div></div>
          <button v-if="allStagesPassed" type="button" class="final-link" :class="activeTask.finalStatus" @click="openFinal">FINAL DIGEST →</button>
        </aside>

        <article class="question-card">
          <template v-if="!finalMode && stageSpec">
            <header class="question-header">
              <div><span class="eyebrow">ROUND {{ String(roundIndex + 1).padStart(2, '0') }} · STEP {{ String(stageIndex + 1).padStart(2, '0') }}</span><h1>{{ stageSpec.title }}</h1><p>{{ stageSpec.prompt }}</p></div>
              <span class="step-chip">{{ STAGES[stageIndex].short }}</span>
            </header>

            <section v-if="stageSpec.kind === 'logic'" class="scratch logic-template">
              <div class="formula-card"><span>{{ currentRound.logicFunc }}</span><code>{{ stageSpec.formula }}</code></div>
              <div class="bit-workspace">
                <div class="bit-index-row"><span></span><i v-for="n in 32" :key="n">{{ (32 - n) % 4 === 0 ? 32 - n : '' }}</i></div>
                <div v-for="row in stageSpec.rows" :key="row.name" class="bit-row source-row"><strong>{{ row.name }}</strong><button v-for="(bit, index) in bin32(row.value)" :key="index" type="button" :aria-label="`把 ${row.name} 的第 ${32 - index} 位 ${bit} 填入 f 草稿`" @click="copyLogicBit(bit, index)">{{ bit }}</button></div>
                <div class="logic-result-groups"><strong>f</strong><div v-for="group in 8" :key="group" class="four-bit-scratch"><button v-for="bit in 4" :key="bit" type="button" @click="toggleBit(logicScratch, (group - 1) * 4 + bit - 1)">{{ logicScratch[(group - 1) * 4 + bit - 1] || '·' }}</button></div></div>
              </div>
              <p class="scratch-note">点击 B / C / D 的某一位可快速复制到 f；点击 f 格切换 0 / 1 / 空白。草稿不参与校验</p>
            </section>

            <section v-else-if="stageSpec.kind === 'addition'" class="scratch addition-template">
              <div class="addition-board">
                <div class="add-line carry-line"><span>进位</span><button v-for="(_, index) in carryMarks" :key="index" type="button" :class="{ marked: carryMarks[index] }" @click="toggleCarry(index)">{{ carryMarks[index] || '·' }}</button></div>
                <div v-for="(operand, opIndex) in stageSpec.operands" :key="operand.name" class="add-line operand-line"><span>{{ opIndex ? '+ ' : '' }}{{ operand.name }}</span><i v-for="(digit, index) in hex32(operand.value)" :key="index">{{ digit }}</i></div>
                <div class="add-divider"></div>
                <div class="add-line scratch-answer"><span>草稿</span><button v-for="(_, index) in addScratch" :key="index" ref="scratchButtons" type="button" :class="{ focused: activeEntry.type === 'scratch' && activeEntry.index === index }" @click="focusAdditionScratch(index)" @focus="activeEntry = { type: 'scratch', index }" @keydown="additionScratchKeydown">{{ addScratch[index] || '·' }}</button></div>
              </div>
              <p class="scratch-note">点进位格进行标记；草稿支持实体键盘和下方键盘，填满 8 位后会持续同步到最终答案</p>
            </section>

            <section v-else class="scratch rotation-template">
              <div class="rotation-source"><span>T3 (HEX)</span><strong>{{ hex32(stageSpec.source) }}</strong><em>左移 {{ stageSpec.shift }} 位</em></div>
              <div class="pointer-label">先填二进制草稿</div>
              <div class="rotation-bits">
                <div v-for="(_, index) in rotationBits" :key="index" class="rotation-bit-picker">
                  <button type="button" class="bit-arrow bit-one" :aria-label="`第 ${32 - index} 位填 1`" @click="setRotationBit(index, '1')">▴</button>
                  <button ref="rotationBitInputs" type="button" class="bit-value" :class="{ filled: rotationBits[index] !== '', active: activeRotationBit === index }" :aria-label="`第 ${32 - index} 位，当前${rotationBits[index] || '未填写'}`" @click="focusRotationBit(index)" @focus="activeRotationBit = index" @keydown="rotationBitKeydown($event, index)">{{ rotationBits[index] || '·' }}</button>
                  <button type="button" class="bit-arrow bit-zero" :aria-label="`第 ${32 - index} 位填 0`" @click="setRotationBit(index, '0')">▾</button>
                </div>
              </div>
              <div class="pointer-track"><div v-for="group in 8" :key="group" class="pointer-group"><button v-for="bit in 4" :key="bit" type="button" :class="{ selected: rotationPointer === (group - 1) * 4 + bit - 1 }" :aria-label="`将第 ${(group - 1) * 4 + bit} 位标为移位起点`" @click="rotationPointer = (group - 1) * 4 + bit - 1">{{ rotationPointer === (group - 1) * 4 + bit - 1 ? '↑' : '·' }}</button></div></div>
              <div class="pointer-label pointer-label-after">再点选移位后成为最高位的位置</div>
              <div v-if="rotatedGroups.length" class="four-bit-groups"><span v-for="(group, index) in rotatedGroups" :key="index">{{ group }}</span></div>
              <div v-else class="four-bit-placeholder">填满 32 位并标记指针后，这里会自动拆成 8 组 4bit。</div>
              <div class="rotation-help">
                <p><span>键盘</span><b>1 / ↑</b> 填 1，<b>0 / ↓</b> 填 0</p>
                <p><span>页面</span>点击每一位的上、下箭头快速填写</p>
                <small>每次填写后焦点自动右移。系统只按 4bit 分组，不转换十六进制；草稿与指针不参与校验。</small>
              </div>
            </section>

            <form class="answer-zone" @submit.prevent="verifyCurrent">
              <label for="answer">最终答案</label>
              <div class="answer-row">
                <input id="answer" ref="answerInput" :value="answer" type="text" maxlength="8" inputmode="text" autocomplete="off" spellcheck="false" placeholder="00000000" @focus="activeEntry = { type: 'answer', index: null }" @input="setAnswer($event.target.value)" />
                <button class="verify-button" type="submit">验证答案</button>
              </div>
              <div v-if="feedback" class="feedback" :class="feedback.ok ? 'ok' : 'wrong'" role="status"><span>{{ feedback.ok ? '✓' : '!' }}</span><p>{{ feedback.message }}</p><button v-if="feedback.ok" type="button" @click="advance">{{ roundIndex === 63 && stageIndex === 5 ? '验证最终摘要' : '下一题 →' }}</button></div>
            </form>
          </template>

          <template v-else>
            <header class="question-header final-header"><div><span class="eyebrow">FINAL CHECK</span><h1>拼接最终 MD5 摘要</h1><p>将 A、B、C、D 分别按小端序输出，再依次拼接。</p></div><span class="step-chip">END</span></header>
            <section class="final-registers"><div v-for="(register, index) in result.registers" :key="index"><span>{{ ['A','B','C','D'][index] }}</span><strong>{{ hex32(register) }}</strong><small>→ {{ hex32(register).match(/../g).reverse().join('') }}</small></div></section>
            <form class="answer-zone final-answer" @submit.prevent="verifyFinal"><label for="digest">最终答案 <span>32 位十六进制</span></label><div class="answer-row"><input id="digest" ref="answerInput" :value="answer" type="text" maxlength="32" autocomplete="off" spellcheck="false" placeholder="00000000000000000000000000000000" @input="setAnswer($event.target.value)" /><button class="verify-button" type="submit">完成工单</button></div><div v-if="feedback" class="feedback" :class="feedback.ok ? 'ok' : 'wrong'"><span>{{ feedback.ok ? '✓' : '!' }}</span><p>{{ feedback.message }}</p><button v-if="feedback.ok" type="button" @click="goLobby">返回工单列表</button></div></form>
          </template>

          <div class="hex-keyboard" aria-label="十六进制屏幕键盘">
            <div class="keyboard-meta"><span>HEX KEYBOARD</span><button type="button" @click="keypad('clear')">清空</button><button type="button" @click="keypad('backspace')">⌫ 退格</button></div>
            <div class="key-row"><button v-for="key in '01234567'" :key="key" type="button" @click="keypad(key)">{{ key }}</button></div>
            <div class="key-row"><button v-for="key in '89ABCDEF'" :key="key" type="button" @click="keypad(key)">{{ key }}</button></div>
          </div>
        </article>
      </section>
    </main>

    <footer class="site-footer">
      <a href="https://github.com/senzi/MD5-Scribe" target="_blank" rel="noopener noreferrer" title="senzi/MD5-Scribe">GitHub</a>
      <i>|</i><span>MIT</span><i>|</i><span>vibecoding</span><i>|</i><span>play.md5.moe</span>
    </footer>

    <aside class="hint-drawer" aria-label="十六进制提示区">
      <div class="drawer-head"><div><span class="eyebrow">QUICK REFERENCE</span><h2>16 进制提示</h2></div></div>
      <p>灰色角标是该字符参与加法时可能对应的十进制值。</p>
      <div class="hex-reference">
        <div v-for="(hex, index) in '0123456789ABCDEF'" :key="hex" class="hex-ref-card">
          <span class="decimal-badge">{{ index }} · {{ index + 16 }}</span>
          <strong>{{ hex }}</strong>
          <code>{{ index.toString(2).padStart(4, '0') }}</code>
        </div>
      </div>
      <div class="drawer-tip"><span>进位提示</span><p>两位十六进制数相加达到 16 时，本列保留余数，并向左进 1。</p></div>
    </aside>
  </div>
</template>
