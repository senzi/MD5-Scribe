<script setup>
import { computed, nextTick, reactive, ref } from 'vue'
import { bin32, computeMd5, diffBits, hex32 } from './md5.js'
import { loadWorkspace, saveWorkspace } from './storage.js'

const MAX_BYTES = 55
const encoder = new TextEncoder()
const saved = loadWorkspace()
const initialParams = new URLSearchParams(globalThis.location.search)
const initialPrintMode = initialParams.get('print')
const initialTaskId = initialParams.get('task')
const initialStep = Number.parseInt(initialParams.get('step') || '0', 10)
const tasks = ref(saved.tasks)
const activeTaskId = ref(tasks.value.some((item) => item.id === initialTaskId) ? initialTaskId : saved.activeTaskId)
const task = ref(tasks.value.find((item) => item.id === activeTaskId.value) || null)
const result = computed(() => task.value ? computeMd5(task.value.message) : null)
const page = ref(initialPrintMode === 'final' ? 'final-print' : initialPrintMode === 'step' ? 'print' : 'home')
const stepId = ref(Number.isInteger(initialStep) && initialStep >= 0 && initialStep < 64 ? initialStep : 0)
const messageInput = ref('')
const notice = ref('')
const answers = reactive(['', '', '', '', ''])
const verification = ref(null)
const digestAnswer = ref('')
const digestVerification = ref(null)
const activeInput = ref(0)
const verificationResult = ref(null)
const digestVerificationResult = ref(null)

const messageBytes = computed(() => encoder.encode(messageInput.value).length)
const completed = computed(() => new Set(task.value?.completedSteps || []))
const allCompleted = computed(() => result.value && completed.value.size === result.value.steps.length)
const currentStep = computed(() => result.value?.steps[stepId.value])
const nextStep = computed(() => {
  if (!result.value) return 0
  return result.value.steps.findIndex((_, index) => !completed.value.has(index)) < 0
    ? result.value.steps.length - 1
    : result.value.steps.findIndex((_, index) => !completed.value.has(index))
})
const isUnlocked = computed(() => stepId.value === 0 || completed.value.has(stepId.value - 1))
const errorCounts = computed(() => {
  const counts = {}
  for (const log of task.value?.logs || []) counts[log.atomName] = (counts[log.atomName] || 0) + 1
  return counts
})

function persist() {
  if (!task.value) return
  task.value.updatedAt = Date.now()
  const index = tasks.value.findIndex((item) => item.id === task.value.id)
  if (index >= 0) tasks.value[index] = task.value
  else tasks.value.push(task.value)
  activeTaskId.value = task.value.id
  saveWorkspace(tasks.value, activeTaskId.value)
}

function formatTime(value) {
  return value ? new Intl.DateTimeFormat('zh-CN', { dateStyle: 'short', timeStyle: 'medium' }).format(value) : '未记录'
}

function formatHexBytes(hex) {
  return hex.match(/.{1,2}/g)?.join(' ') || ''
}

function startTask() {
  if (!messageInput.value) return
  if (messageBytes.value > MAX_BYTES) {
    notice.value = `只支持单个 MD5 消息块，请将消息缩短到 ${MAX_BYTES} bytes 以内。`
    return
  }
  const now = Date.now()
  task.value = {
    id: globalThis.crypto?.randomUUID?.() || `task-${now}-${Math.random().toString(16).slice(2)}`,
    message: messageInput.value,
    completedSteps: [],
    logs: [],
    createdAt: now,
    updatedAt: now,
    startTimes: { 0: now },
    endTimes: {},
    printTimes: {},
    verifyOpenTimes: {},
    verifySubmitTimes: {},
    finalVerified: false,
    finalPrintTime: null,
    finalVerifyOpenTime: null,
    finalVerifySubmitTime: null,
  }
  tasks.value.push(task.value)
  activeTaskId.value = task.value.id
  saveWorkspace(tasks.value, activeTaskId.value)
  messageInput.value = ''
  notice.value = ''
  openStep(0)
}

function selectTask(taskId) {
  const selected = tasks.value.find((item) => item.id === taskId)
  if (!selected) return
  task.value = selected
  activeTaskId.value = selected.id
  saveWorkspace(tasks.value, activeTaskId.value)
  notice.value = ''
  goHome()
}

function deleteTask(taskId) {
  tasks.value = tasks.value.filter((item) => item.id !== taskId)
  if (activeTaskId.value === taskId) {
    task.value = tasks.value[0] || null
    activeTaskId.value = task.value?.id || null
  }
  saveWorkspace(tasks.value, activeTaskId.value)
  page.value = 'home'
  notice.value = '本地任务已删除。'
}

function goHome() {
  page.value = 'home'
  verification.value = null
  digestVerification.value = null
}

function openStep(index) {
  if (!result.value || index < 0 || index >= result.value.steps.length) return
  stepId.value = index
  task.value.startTimes[index] ||= Date.now()
  persist()
  page.value = 'step'
}

function openVerify(index = stepId.value) {
  openStep(index)
  if (!isUnlocked.value) return
  answers.splice(0, 5, '', '', '', '', '')
  verification.value = null
  task.value.verifyOpenTimes[index] = Date.now()
  persist()
  page.value = 'verify'
}

function sanitize(value, length = 8) {
  return value.toUpperCase().replace(/[^0-9A-F]/g, '').slice(0, length)
}

function setAnswer(index, value) {
  answers[index] = sanitize(value)
  activeInput.value = index
  if (answers[index].length === 8 && index < 4) activeInput.value = index + 1
}

function keypad(key) {
  const index = activeInput.value
  if (key === 'backspace') answers[index] = answers[index].slice(0, -1)
  else if (key === 'clear') answers[index] = ''
  else if (key === 'next') activeInput.value = (index + 1) % 5
  else setAnswer(index, answers[index] + key)
}

async function focusResult(elementRef) {
  await nextTick()
  const element = elementRef.value
  if (!element) return
  element.scrollIntoView({ behavior: 'smooth', block: 'start' })
  element.focus({ preventScroll: true })
}

async function verifyStep() {
  const formatOk = answers.every((answer) => /^[0-9A-F]{8}$/.test(answer))
  if (!formatOk) {
    notice.value = '每项都需要填写恰好 8 位十六进制符号。'
    return
  }
  notice.value = ''
  const checked = currentStep.value.correctAtoms.map((expected, index) => {
    const actual = Number.parseInt(answers[index], 16) >>> 0
    const ok = expected === actual
    if (!ok) {
      task.value.logs.push({
        timestamp: new Date().toISOString(),
        stepIndex: stepId.value,
        atomName: currentStep.value.atomNames[index],
        expected: hex32(expected),
        actual: hex32(actual),
        diffBits: diffBits(expected, actual),
      })
    }
    return { ok, name: currentStep.value.atomNames[index], expected, actual }
  })
  verification.value = checked
  task.value.verifySubmitTimes[stepId.value] = Date.now()
  if (checked.every((item) => item.ok)) {
    if (!completed.value.has(stepId.value)) task.value.completedSteps.push(stepId.value)
    task.value.completedSteps.sort((a, b) => a - b)
    task.value.endTimes[stepId.value] = Date.now()
  }
  persist()
  await focusResult(verificationResult)
}

function continueAfterVerify() {
  if (!verification.value?.every((item) => item.ok)) return
  if (stepId.value < result.value.steps.length - 1) openStep(stepId.value + 1)
  else openFinalVerify()
}

function recordPrint(final = false) {
  if (final && !allCompleted.value) {
    notice.value = '请先完成全部 64 轮。'
    return false
  }
  if (final) task.value.finalPrintTime = Date.now()
  else task.value.printTimes[stepId.value] = Date.now()
  persist()
  return true
}

function getPrintUrl(final = false) {
  if (!task.value) return '#'
  const url = new URL(globalThis.location.href)
  url.search = ''
  url.hash = ''
  url.searchParams.set('print', final ? 'final' : 'step')
  url.searchParams.set('task', task.value.id)
  if (!final) url.searchParams.set('step', String(stepId.value))
  return url.toString()
}

function requestPrint() {
  globalThis.print()
}

function closePrintWindow() {
  globalThis.close()
}

function openFinalVerify() {
  if (!allCompleted.value) {
    notice.value = '请先完成全部 64 轮。'
    openStep(nextStep.value)
    return
  }
  task.value.finalVerifyOpenTime ||= Date.now()
  persist()
  digestVerification.value = null
  page.value = 'final-verify'
}

async function verifyDigest() {
  const normalized = sanitize(digestAnswer.value, 32)
  digestAnswer.value = normalized
  const formatOk = /^[0-9A-F]{32}$/.test(normalized)
  const ok = formatOk && normalized.toLowerCase() === result.value.digest
  digestVerification.value = { ok, formatOk }
  task.value.finalVerifySubmitTime = Date.now()
  task.value.finalVerified = ok
  if (!ok && formatOk) {
    task.value.logs.push({
      timestamp: new Date().toISOString(),
      stepIndex: 'Final',
      atomName: 'Final MD5 digest',
      expected: result.value.digest.toUpperCase(),
      actual: normalized,
      diffBits: null,
    })
  }
  persist()
  if (ok) page.value = 'report'
  else await focusResult(digestVerificationResult)
}

function registerRows() {
  return result.value.registers.map((word, index) => ({
    name: ['A', 'B', 'C', 'D'][index],
    word: hex32(word),
    output: hex32(word).match(/../g).reverse().join(''),
  }))
}

function timeline() {
  return result.value.steps.map((_, index) => ({
    step: index,
    completed: completed.value.has(index),
    duration: task.value.endTimes[index] && task.value.startTimes[index]
      ? ((task.value.endTimes[index] - task.value.startTimes[index]) / 1000).toFixed(1)
      : null,
  }))
}

function markdownReport() {
  const counts = Object.entries(errorCounts.value).map(([name, count]) => `- ${name}: ${count}`).join('\n') || '- 无错误'
  const logs = task.value.logs.map((log) => `| ${log.timestamp} | ${log.stepIndex} | ${log.atomName} | ${log.expected} | ${log.actual} |`).join('\n') || '| - | - | 无错误 | - | - |'
  return `# MD5-Scribe Final Report\n\n- 原始消息: \`${task.value.message}\`\n- 最终 MD5: \`${result.value.digest}\`\n- 完成轮数: ${completed.value.size} / ${result.value.steps.length}\n- 最终验证: ${task.value.finalVerified ? '已完成' : '未完成'}\n- 创建时间: ${formatTime(task.value.createdAt)}\n\n## 错误类型\n\n${counts}\n\n## 审计日志\n\n| 时间 | Step | 运算 | 预期值 | 实际值 |\n|---|---:|---|---|---|\n${logs}\n`
}

function downloadReport() {
  const blob = new Blob([markdownReport()], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `md5-scribe-${Date.now()}.md`
  anchor.click()
  URL.revokeObjectURL(url)
}
</script>

<template>
  <nav v-if="page !== 'print' && page !== 'final-print'" class="navbar no-print">
    <button class="brand-button" @click="goHome">
      <span class="logo">MD5-Scribe</span>
      <span class="tagline">本地优先 · 64 轮手算验证</span>
    </button>
    <div class="nav-links">
      <button @click="goHome">首页</button>
      <button v-if="task" @click="openStep(nextStep)">当前任务</button>
      <button v-if="task" @click="page = 'report'">报告</button>
    </div>
  </nav>

  <main class="container" :class="{ 'print-container': page === 'print' || page === 'final-print' }">
    <div v-if="notice" class="flash flash-error no-print">{{ notice }}</div>

    <template v-if="page === 'home'">
      <div class="hero">
        <div class="local-badge">数据仅保存在此浏览器</div>
        <h1>MD5-Scribe</h1>
        <p class="subtitle">一步一步，手算并验证 MD5 的 64 轮逻辑运算</p>
      </div>

      <div v-if="tasks.length" class="card task-list-card">
        <div class="section-heading"><div><h2>本地挑战</h2><p>{{ tasks.length }} 个独立任务，进度分别保存在此浏览器。</p></div></div>
        <div class="task-list">
          <article v-for="item in tasks" :key="item.id" class="task-row" :class="{ 'is-active': item.id === activeTaskId }">
            <button type="button" class="task-select" @click="selectTask(item.id)">
              <span class="task-message mono">{{ item.message }}</span>
              <span class="task-progress">{{ item.completedSteps.length }} / 64 轮</span>
              <span class="task-updated">{{ formatTime(item.updatedAt) }}</span>
            </button>
            <button type="button" class="btn btn-small btn-secondary" @click="deleteTask(item.id)">删除</button>
          </article>
        </div>
        <div v-if="task" class="actions compact-actions">
          <button type="button" class="btn btn-primary" @click="task.finalVerified ? page = 'report' : allCompleted ? openFinalVerify() : openStep(nextStep)">
            {{ task.finalVerified ? '查看当前报告' : allCompleted ? '继续当前最终验证' : `继续当前 Step ${nextStep}` }}
          </button>
        </div>
      </div>

      <div class="card input-card">
        <h2>开始新的挑战</h2>
        <form class="input-form" @submit.prevent="startTask">
          <div class="form-group">
            <label for="message">输入字符串</label>
            <input id="message" v-model="messageInput" type="text" placeholder="例如: hello" required autofocus />
            <div class="message-meter">
              <div class="message-meter-meta"><span>单块容量</span><span><strong>{{ messageBytes }}</strong> / {{ MAX_BYTES }} bytes</span></div>
              <div class="message-meter-track"><div class="message-meter-fill" :class="{ 'is-rich': messageBytes >= 44, 'is-over': messageBytes > MAX_BYTES }" :style="{ width: `${Math.min(messageBytes / MAX_BYTES * 100, 100)}%` }"></div></div>
              <div class="message-meter-hint">消息按 UTF-8 字节计数，单块练习最多 55 bytes。</div>
            </div>
          </div>
          <button class="btn btn-primary" :disabled="messageBytes > MAX_BYTES">初始化并开始</button>
        </form>
      </div>

      <div class="info-grid">
        <div class="info-card"><h3>1. 浏览器计算</h3><p>MD5 填充、64 轮运算和校验全部在当前设备完成。</p></div>
        <div class="info-card"><h3>2. 打印工单</h3><p>每轮都可使用浏览器打印或另存为 PDF。</p></div>
        <div class="info-card"><h3>3. 自动恢复</h3><p>刷新或离线重开后，从 localStorage 恢复进度。</p></div>
        <div class="info-card"><h3>4. 本地导出</h3><p>最终审计报告直接下载为 Markdown 文件。</p></div>
      </div>
    </template>

    <template v-else-if="page === 'step' && currentStep">
      <div class="step-header">
        <div class="progress-bar"><div class="progress-fill" :style="{ width: `${(stepId + 1) / result.steps.length * 100}%` }"></div></div>
        <div class="step-meta"><span class="step-label">Step {{ stepId }} / {{ result.steps.length - 1 }}</span><span class="step-status" :class="completed.has(stepId) ? 'status-completed' : isUnlocked ? 'status-unlocked' : 'status-locked'">{{ completed.has(stepId) ? '已完成' : isUnlocked ? '已解锁' : '未解锁' }}</span></div>
      </div>
      <div class="card"><h2>原始消息</h2><div class="data-row"><span class="data-label">字符串:</span><span class="data-value mono">{{ task.message }}</span></div><div class="data-row"><span class="data-label">Hex:</span><span class="data-value mono small wrap-anywhere">{{ result.messageHex }}</span></div></div>
      <div class="card"><h2>本轮寄存器状态（输入）</h2><div class="registers-grid"><div v-for="(reg, index) in currentStep.registersBefore" :key="index" class="register-box"><div class="reg-name">{{ ['A','B','C','D'][index] }}</div><div class="reg-hex">{{ hex32(reg) }}</div><div class="reg-bin"><span>{{ bin32(reg).slice(0,16) }}</span><span>{{ bin32(reg).slice(16) }}</span></div></div></div></div>
      <div class="card"><h2>本轮运算参数</h2><div class="params-grid"><div class="param-box"><div class="param-label">逻辑函数</div><div class="param-value">{{ currentStep.logicFunc }}</div></div><div class="param-box"><div class="param-label">M_j 索引</div><div class="param-value">{{ currentStep.mjIdx }}</div></div><div class="param-box"><div class="param-label">M_j 值</div><div class="param-value mono">{{ hex32(currentStep.mj) }}</div></div><div class="param-box"><div class="param-label">K_i</div><div class="param-value mono">{{ hex32(currentStep.ki) }}</div></div><div class="param-box"><div class="param-label">左移 s</div><div class="param-value">{{ currentStep.shift }}</div></div></div></div>
      <div class="actions"><a class="btn btn-secondary" :href="getPrintUrl(false)" target="_blank" rel="noopener" @click="recordPrint(false)">查看打印工单</a><button class="btn" :class="isUnlocked ? 'btn-primary' : 'btn-disabled'" :disabled="!isUnlocked" @click="openVerify()">开始验证</button></div>
      <div class="step-nav"><button v-if="stepId > 0" class="btn btn-small" @click="openStep(stepId - 1)">← 上一步</button><button v-if="stepId < result.steps.length - 1" class="btn btn-small" @click="openStep(stepId + 1)">下一步 →</button><button v-else class="btn btn-small btn-accent" @click="openFinalVerify">验证最终 MD5</button></div>
    </template>

    <template v-else-if="page === 'verify' && currentStep">
      <div class="step-header"><div class="progress-bar"><div class="progress-fill" :style="{ width: `${(stepId + 1) / result.steps.length * 100}%` }"></div></div><div class="step-meta"><span class="step-label">Step {{ stepId }} / {{ result.steps.length - 1 }} — 验证</span></div></div>
      <div class="card"><h2>运算参数</h2><div class="params-grid"><div class="param-box"><div class="param-label">函数</div><div class="param-value">{{ currentStep.logicFunc }}</div></div><div class="param-box"><div class="param-label">M_j</div><div class="param-value mono">{{ hex32(currentStep.mj) }}</div></div><div class="param-box"><div class="param-label">K_i</div><div class="param-value mono">{{ hex32(currentStep.ki) }}</div></div><div class="param-box"><div class="param-label">s</div><div class="param-value">{{ currentStep.shift }}</div></div></div></div>
      <div v-if="verification" ref="verificationResult" class="card verification-result" tabindex="-1" role="status" aria-live="polite"><h2>验证结果</h2><div v-for="item in verification" :key="item.name" class="atom-check" :class="item.ok ? 'atom-ok' : 'atom-error'"><div class="atom-header"><span class="atom-name">{{ item.name }}</span><span class="atom-badge" :class="item.ok ? 'badge-ok' : 'badge-error'">{{ item.ok ? '正确' : '错误' }}</span></div><div v-if="!item.ok" class="atom-detail"><div class="compare-row"><span class="compare-label">预期:</span><span class="compare-hex mono">{{ hex32(item.expected) }}</span><span class="compare-bin mono small">{{ bin32(item.expected) }}</span></div><div class="compare-row"><span class="compare-label">实际:</span><span class="compare-hex mono error">{{ hex32(item.actual) }}</span><span class="compare-bin mono small error">{{ bin32(item.actual) }}</span></div></div></div><button v-if="verification.every(item => item.ok)" class="btn btn-primary result-next" @click="continueAfterVerify">{{ stepId === result.steps.length - 1 ? '进入最终验证' : '进入下一轮' }}</button></div>
      <div class="card verify-form-card"><h2>输入您的手算结果</h2><form class="verify-form" @submit.prevent="verifyStep"><div v-for="(name, index) in currentStep.atomNames" :key="name" class="form-group atom-group"><label :for="`atom-${index}`">{{ name }}</label><input :id="`atom-${index}`" type="text" :value="answers[index]" class="mono input-hex" :class="{ 'input-active': activeInput === index }" maxlength="8" placeholder="8 位十六进制" autocomplete="off" autocapitalize="characters" spellcheck="false" @focus="activeInput = index" @input="setAnswer(index, $event.target.value)" /><small>请输入 32 位结果的 8 位十六进制表示</small></div><div class="form-actions"><button class="btn btn-primary">提交验证</button><a class="btn btn-secondary" :href="getPrintUrl(false)" target="_blank" rel="noopener" @click="recordPrint(false)">查看打印工单</a></div></form></div>
      <div class="hex-keypad"><div class="hex-keypad-title">HEX</div><div class="hex-keypad-grid"><button v-for="key in '0123456789ABCDEF'" :key="key" class="hex-key" @click="keypad(key)">{{ key }}</button></div><div class="hex-keypad-actions"><button class="hex-key hex-key-wide" @click="keypad('backspace')">←</button><button class="hex-key hex-key-wide" @click="keypad('clear')">清空</button><button class="hex-key hex-key-wide" @click="keypad('next')">下个</button></div></div>
      <div class="step-nav"><button class="btn btn-small" @click="openStep(stepId)">控制台</button></div>
    </template>

    <template v-else-if="page === 'print' && currentStep">
      <div class="print-controls no-print">
        <h2>打印工单预览</h2>
        <p>请使用浏览器“打印为 PDF”功能保存此工单。Step 0 包含单独的参考附录页。</p>
        <button type="button" class="btn btn-primary" @click="requestPrint">立即打印</button>
      </div>

      <div class="print-page">
        <div class="print-header">
          <div class="print-title">MD5-Scribe 手算工单</div>
          <div class="print-meta">
            <span>Step: <strong>{{ stepId }} / {{ result.steps.length - 1 }}</strong></span>
            <span>函数: <strong>{{ currentStep.logicFunc }}</strong></span>
            <span>s = <strong>{{ currentStep.shift }}</strong></span>
          </div>
        </div>

        <div class="print-section print-message-section">
          <div class="print-section-heading">
            <h3>原始消息</h3>
            <span>{{ Array.from(task.message).length }} 字符 · {{ result.messageHex.length / 2 }} bytes</span>
          </div>
          <div class="message-display-grid">
            <div class="message-display-row message-text-row">
              <span class="message-kind">字符串</span>
              <div class="message-text"><span class="message-quote">“</span>{{ task.message }}<span class="message-quote">”</span></div>
            </div>
            <div class="message-display-row message-hex-row">
              <span class="message-kind">UTF-8 Hex</span>
              <div class="message-hex mono">{{ formatHexBytes(result.messageHex) }}</div>
            </div>
          </div>
        </div>

        <div class="print-section">
          <h3>本轮输入寄存器</h3>
          <div class="registers-compact">
            <div v-for="(reg, index) in currentStep.registersBefore" :key="index" class="reg-col">
              <div class="reg-col-name">{{ ['A', 'B', 'C', 'D'][index] }}</div>
              <div class="reg-col-hex">{{ hex32(reg) }}</div>
              <div class="reg-col-bin">
                <span>{{ bin32(reg).slice(0, 16) }}</span>
                <span>{{ bin32(reg).slice(16) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div class="print-section">
          <h3>常量与消息字</h3>
          <div class="const-grid">
            <div>M_j[{{ currentStep.mjIdx }}] = <span class="mono">{{ hex32(currentStep.mj) }}</span></div>
            <div>K_i = <span class="mono">{{ hex32(currentStep.ki) }}</span></div>
            <div>s = <span class="mono">{{ currentStep.shift }}</span> 位</div>
          </div>
        </div>

        <div class="worksheet-block">
          <div class="ws-title">步骤 01 — 逻辑函数 f = {{ currentStep.logicFunc }}(B, C, D)</div>
          <div class="ws-subtitle">B, C, D 的二进制/十六进制对照</div>
          <table class="bit-table">
            <tbody>
              <tr>
                <th aria-label="寄存器"></th>
                <th v-for="index in 32" :key="index" class="bit-index">{{ 32 - index }}</th>
              </tr>
              <tr v-for="(registerIndex, rowIndex) in [1, 2, 3]" :key="registerIndex">
                <td class="reg-label">{{ ['B', 'C', 'D'][rowIndex] }}</td>
                <td v-for="(bit, bitIndex) in bin32(currentStep.registersBefore[registerIndex])" :key="bitIndex" class="bit-cell">{{ bit }}</td>
              </tr>
              <tr class="result-row">
                <td class="reg-label">f</td>
                <td v-for="index in 32" :key="index" class="bit-cell result"></td>
              </tr>
            </tbody>
          </table>
          <div class="hex-grid f-hex-grid">
            <div class="hex-row">
              <span>f (Hex):</span>
              <div v-for="index in 8" :key="index" class="hex-box"><div class="hex-char"></div></div>
            </div>
          </div>
        </div>

        <div class="worksheet-block">
          <div class="ws-title">步骤 02 — 累加 T1 = A + f</div>
          <div class="addition-layout">
            <div class="add-row"><span class="add-label">A</span><div v-for="(char, index) in hex32(currentStep.registersBefore[0])" :key="index" class="hex-char-disp">{{ char }}</div></div>
            <div class="add-row"><span class="add-label">+ f</span><div v-for="index in 8" :key="index" class="hex-box"><div class="hex-char"></div></div></div>
            <div class="add-divider"></div>
            <div class="add-row result"><span class="add-label">T1</span><div v-for="index in 8" :key="index" class="hex-box"><div class="hex-char"></div></div></div>
          </div>
        </div>
      </div>

      <div class="print-page worksheet-continuation">
        <div class="print-header continuation-header">
          <div class="print-title">MD5-Scribe 手算工单 · 续页</div>
          <div class="print-meta"><span>Step: <strong>{{ stepId }} / {{ result.steps.length - 1 }}</strong></span></div>
        </div>
        <div class="worksheet-block">
          <div class="ws-title">步骤 03 — 消息字累加 T2 = T1 + M_j</div>
          <div class="addition-layout">
            <div class="add-row"><span class="add-label">T1</span><div v-for="index in 8" :key="index" class="hex-box"><div class="hex-char"></div></div></div>
            <div class="add-row"><span class="add-label">+ M_j</span><div v-for="(char, index) in hex32(currentStep.mj)" :key="index" class="hex-char-disp">{{ char }}</div></div>
            <div class="add-divider"></div>
            <div class="add-row result"><span class="add-label">T2</span><div v-for="index in 8" :key="index" class="hex-box"><div class="hex-char"></div></div></div>
          </div>
        </div>

        <div class="worksheet-block">
          <div class="ws-title">步骤 04 — 常量累加 T3 = T2 + K_i</div>
          <div class="addition-layout">
            <div class="add-row"><span class="add-label">T2</span><div v-for="index in 8" :key="index" class="hex-box"><div class="hex-char"></div></div></div>
            <div class="add-row"><span class="add-label">+ K_i</span><div v-for="(char, index) in hex32(currentStep.ki)" :key="index" class="hex-char-disp">{{ char }}</div></div>
            <div class="add-divider"></div>
            <div class="add-row result"><span class="add-label">T3</span><div v-for="index in 8" :key="index" class="hex-box"><div class="hex-char"></div></div></div>
          </div>
        </div>

        <div class="worksheet-block">
          <div class="ws-title">步骤 05 — 循环左移 ROT = RotateLeft(T3, {{ currentStep.shift }})</div>
          <div class="bit-grid-label">T3 (Binary):</div>
          <div class="bit-grid-32 bit-grid-spacious">
            <div v-for="index in 32" :key="index" class="bit-slot"><div class="bit-pos">{{ 32 - index }}</div><div class="bit-value"></div></div>
          </div>
          <div class="rotate-instruction">将 T3 的 32 位二进制向左循环移动 <strong>{{ currentStep.shift }}</strong> 位。在下方格子中重新排列各位。</div>
          <div class="bit-grid-label">ROT (Binary):</div>
          <div class="bit-grid-32 bit-grid-spacious">
            <div v-for="index in 32" :key="index" class="bit-slot"><div class="bit-pos">{{ 32 - index }}</div><div class="bit-value"></div></div>
          </div>
          <div class="hex-row-result"><span>ROT (Hex):</span><div v-for="index in 8" :key="index" class="hex-box"><div class="hex-char"></div></div></div>
        </div>

        <div class="worksheet-block">
          <div class="ws-title">步骤 06 — 最终结果 B_new = ROT + B</div>
          <div class="addition-layout">
            <div class="add-row"><span class="add-label">ROT</span><div v-for="index in 8" :key="index" class="hex-box"><div class="hex-char"></div></div></div>
            <div class="add-row"><span class="add-label">+ B</span><div v-for="(char, index) in hex32(currentStep.registersBefore[1])" :key="index" class="hex-char-disp">{{ char }}</div></div>
            <div class="add-divider"></div>
            <div class="add-row result"><span class="add-label">B_new</span><div v-for="index in 8" :key="index" class="hex-box"><div class="hex-char"></div></div></div>
          </div>
        </div>
      </div>

      <div v-if="stepId === 0" class="print-page reference-page">
        <div class="print-header"><div class="print-title">附录 — 十六进制-二进制对照表</div></div>
        <div class="ref-grid">
          <div v-for="index in 16" :key="index" class="ref-item">
            <div class="ref-hex">{{ (index - 1).toString(16).toUpperCase() }}</div>
            <div class="ref-bin">{{ (index - 1).toString(2).padStart(4, '0') }}</div>
          </div>
        </div>
        <div class="ref-notes">
          <h4>逻辑函数速查</h4>
          <div class="func-ref">
            <div><strong>F(B,C,D)</strong> = (B ∧ C) ∨ (¬B ∧ D)</div>
            <div><strong>G(B,C,D)</strong> = (B ∧ D) ∨ (C ∧ ¬D)</div>
            <div><strong>H(B,C,D)</strong> = B ⊕ C ⊕ D</div>
            <div><strong>I(B,C,D)</strong> = C ⊕ (B ∨ ¬D)</div>
          </div>
        </div>
      </div>

      <div class="actions no-print"><button type="button" class="btn btn-primary" @click="requestPrint">再次打印</button><button type="button" class="btn btn-secondary" @click="closePrintWindow">关闭此页</button></div>
    </template>

    <template v-else-if="page === 'final-print'">
      <div class="print-controls no-print"><h2>最终 MD5 工单预览</h2><p>请使用浏览器“打印为 PDF”功能保存此工单。</p><button type="button" class="btn btn-primary" @click="requestPrint">立即打印</button></div>
      <div class="print-page">
        <div class="print-header"><div class="print-title">MD5-Scribe 最终摘要工单</div></div>
        <div class="print-section print-message-section">
          <div class="print-section-heading"><h3>原始消息</h3><span>{{ Array.from(task.message).length }} 字符 · {{ result.messageHex.length / 2 }} bytes</span></div>
          <div class="message-display-grid">
            <div class="message-display-row message-text-row"><span class="message-kind">字符串</span><div class="message-text"><span class="message-quote">“</span>{{ task.message }}<span class="message-quote">”</span></div></div>
            <div class="message-display-row message-hex-row"><span class="message-kind">UTF-8 Hex</span><div class="message-hex mono">{{ formatHexBytes(result.messageHex) }}</div></div>
          </div>
        </div>
        <div class="print-section"><h3>最终 A/B/C/D 寄存器</h3><div class="final-register-grid"><div v-for="row in registerRows()" :key="row.name" class="summary-item"><div class="summary-label">{{ row.name }}</div><div class="summary-value mono">{{ row.word }}</div></div></div></div>
        <div class="worksheet-block">
          <div class="ws-title">步骤 01 — 将每个 32 位寄存器按字节反序</div>
          <div class="final-byte-table">
            <div v-for="row in registerRows()" :key="row.name" class="final-byte-row">
              <span class="add-label">{{ row.name }}</span>
              <div v-for="(byte, index) in row.word.match(/../g)" :key="index" class="hex-char-disp">{{ byte }}</div>
              <span class="byte-arrow">→</span>
              <div v-for="index in 4" :key="index" class="hex-box"><div class="hex-char"></div></div>
            </div>
          </div>
        </div>
        <div class="worksheet-block"><div class="ws-title">步骤 02 — 按 A, B, C, D 的输出字节顺序拼接最终 MD5</div><div class="digest-grid"><div v-for="index in 32" :key="index" class="hex-box"><div class="hex-char"></div></div></div></div>
      </div>
      <div class="actions no-print"><button type="button" class="btn btn-primary" @click="requestPrint">再次打印</button><button type="button" class="btn btn-secondary" @click="closePrintWindow">关闭此页</button></div>
    </template>

    <template v-else-if="page === 'final-verify'">
      <div class="hero"><h1>最终 MD5 验证</h1><p class="subtitle">将最终 A/B/C/D 按 little-endian 字节顺序拼接。</p></div>
      <div class="card"><h2>最终寄存器</h2><div class="summary-grid"><div v-for="row in registerRows()" :key="row.name" class="summary-item"><div class="summary-label">{{ row.name }}</div><div class="summary-value mono">{{ row.word }}</div></div></div></div>
      <div v-if="digestVerification" ref="digestVerificationResult" class="card verification-result" tabindex="-1" role="status" aria-live="polite"><div class="atom-check" :class="digestVerification.ok ? 'atom-ok' : 'atom-error'"><div class="atom-header"><span class="atom-name">最终 MD5</span><span class="atom-badge" :class="digestVerification.ok ? 'badge-ok' : 'badge-error'">{{ digestVerification.ok ? '正确' : '错误' }}</span></div><p v-if="!digestVerification.ok">{{ digestVerification.formatOk ? '结果不匹配，请检查寄存器内部字节反序与 A/B/C/D 拼接顺序。' : '请输入 32 位十六进制字符串。' }}</p></div></div>
      <div class="card verify-form-card"><form class="verify-form" @submit.prevent="verifyDigest"><div class="form-group atom-group"><label for="digest">MD5 Digest</label><input id="digest" v-model="digestAnswer" type="text" class="mono input-hex digest-input" maxlength="32" placeholder="32 位十六进制" autocomplete="off" autocapitalize="characters" spellcheck="false" @input="digestAnswer = sanitize(digestAnswer, 32)" /><small>例如 A=01234567 在输出中写作 67452301。</small></div><div class="form-actions"><button class="btn btn-primary">提交验证</button><a class="btn btn-secondary" :href="getPrintUrl(true)" target="_blank" rel="noopener" @click="recordPrint(true)">查看最终工单</a></div></form></div>
    </template>

    <template v-else-if="page === 'report' && task">
      <div class="hero"><h1>计算报告</h1><p class="subtitle">保存在此设备上的 MD5 手算验证审计踪迹</p></div>
      <div class="card"><h2>摘要</h2><div class="summary-grid"><div class="summary-item"><div class="summary-label">原始消息</div><div class="summary-value">{{ task.message }}</div></div><div class="summary-item"><div class="summary-label">最终 Hash</div><div class="summary-value mono wrap-anywhere">{{ result.digest }}</div></div><div class="summary-item"><div class="summary-label">完成轮数</div><div class="summary-value">{{ completed.size }} / {{ result.steps.length }}</div></div><div class="summary-item"><div class="summary-label">最终验证</div><div class="summary-value">{{ task.finalVerified ? '已完成' : '未完成' }}</div></div><div class="summary-item"><div class="summary-label">错误记录</div><div class="summary-value">{{ task.logs.length }}</div></div></div></div>
      <div class="card"><h2>错误类型分析</h2><div v-if="Object.keys(errorCounts).length" class="chart-bars"><div v-for="(count,name) in errorCounts" :key="name" class="bar-row"><span class="bar-label">{{ name }}</span><div class="bar-track"><div class="bar-fill" :style="{ width: `${count / task.logs.length * 100}%` }"></div></div><span class="bar-count">{{ count }}</span></div></div><p v-else>全程零错误。</p></div>
      <div class="card"><h2>时间线</h2><div class="timeline"><div v-for="item in timeline()" :key="item.step" class="timeline-item" :class="item.completed ? 'completed' : 'incomplete'"><span class="tl-step">Step {{ item.step }}</span><span class="tl-duration">{{ item.duration ? `${item.duration}s` : '未完成' }}</span><span v-if="item.completed" class="tl-status">✓</span></div></div></div>
      <div class="card"><h2>审计日志</h2><div v-if="task.logs.length" class="log-table-wrapper"><table class="log-table"><thead><tr><th>时间</th><th>Step</th><th>运算</th><th>预期值</th><th>实际值</th><th>差异位数</th></tr></thead><tbody><tr v-for="(log,index) in task.logs" :key="index"><td>{{ formatTime(Date.parse(log.timestamp)) }}</td><td>{{ log.stepIndex }}</td><td>{{ log.atomName }}</td><td class="mono">{{ log.expected }}</td><td class="mono error">{{ log.actual }}</td><td>{{ log.diffBits ?? '-' }}</td></tr></tbody></table></div><p v-else>暂无错误日志。</p></div>
      <div class="actions"><a v-if="allCompleted" class="btn btn-secondary" :href="getPrintUrl(true)" target="_blank" rel="noopener" @click="recordPrint(true)">查看最终工单</a><button v-else class="btn btn-disabled" disabled>请先完成全部轮次</button><button class="btn btn-secondary" @click="allCompleted && openFinalVerify()">最终验证</button><button class="btn btn-secondary" @click="downloadReport">下载 Markdown</button><button class="btn btn-primary" @click="goHome">返回首页</button></div>
    </template>
  </main>

  <footer v-if="page !== 'print' && page !== 'final-print'" class="footer no-print"><p>MD5-Scribe · Local-first · 数据不离开浏览器</p></footer>
</template>
