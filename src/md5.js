const MASK = 0xffffffffn

export const K = Array.from({ length: 64 }, (_, i) =>
  Number(BigInt(Math.floor(2 ** 32 * Math.abs(Math.sin(i + 1)))) & MASK),
)

export const S = [
  ...[7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22],
  ...[5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9, 14, 20],
  ...[4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23],
  ...[6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21],
]

export const M_IDX = [
  ...Array.from({ length: 16 }, (_, i) => i),
  ...Array.from({ length: 16 }, (_, i) => (5 * i + 1) % 16),
  ...Array.from({ length: 16 }, (_, i) => (3 * i + 5) % 16),
  ...Array.from({ length: 16 }, (_, i) => (7 * i) % 16),
]

const u32 = (value) => Number(BigInt(value) & MASK) >>> 0
const add32 = (...values) => Number(values.reduce((sum, value) => sum + BigInt(value >>> 0), 0n) & MASK) >>> 0

export function leftRotate(value, shift) {
  const x = value >>> 0
  if (shift === 0) return x
  return ((x << shift) | (x >>> (32 - shift))) >>> 0
}

export const F = (b, c, d) => ((b & c) | (~b & d)) >>> 0
export const G = (b, c, d) => ((b & d) | (c & ~d)) >>> 0
export const H = (b, c, d) => (b ^ c ^ d) >>> 0
export const I = (b, c, d) => (c ^ (b | ~d)) >>> 0

const functions = [F, G, H, I]
const names = ['F', 'G', 'H', 'I']
const atomNames = ['T1 (A + f)', 'T2 (T1 + M_j)', 'T3 (T2 + K_i)', 'ROT (Left Rotate)', 'B_new (ROT + B)']

function pad(bytes) {
  const length = Math.ceil((bytes.length + 9) / 64) * 64
  const padded = new Uint8Array(length)
  padded.set(bytes)
  padded[bytes.length] = 0x80
  let bits = BigInt(bytes.length) * 8n
  for (let i = 0; i < 8; i += 1) {
    padded[length - 8 + i] = Number(bits & 0xffn)
    bits >>= 8n
  }
  return padded
}

export function computeMd5(message) {
  const bytes = new TextEncoder().encode(message)
  const padded = pad(bytes)
  let A = 0x67452301
  let B = 0xefcdab89
  let C = 0x98badcfe
  let D = 0x10325476
  const steps = []

  for (let offset = 0; offset < padded.length; offset += 64) {
    const view = new DataView(padded.buffer, padded.byteOffset + offset, 64)
    const words = Array.from({ length: 16 }, (_, i) => view.getUint32(i * 4, true))
    let a = A
    let b = B
    let c = C
    let d = D

    for (let i = 0; i < 64; i += 1) {
      const globalIndex = steps.length
      const round = Math.floor(i / 16)
      const fValue = functions[round](b, c, d)
      const mj = words[M_IDX[i]]
      const t1 = add32(a, fValue)
      const t2 = add32(t1, mj)
      const t3 = add32(t2, K[i])
      const rotated = leftRotate(t3, S[i])
      const bNew = add32(rotated, b)
      steps.push({
        stepIndex: globalIndex,
        registersBefore: [a, b, c, d],
        registersAfter: [d, bNew, b, c],
        mj,
        mjIdx: M_IDX[i],
        ki: K[i],
        shift: S[i],
        logicFunc: names[round],
        fValue,
        correctAtoms: [t1, t2, t3, rotated, bNew],
        atomNames,
      })
      ;[a, b, c, d] = [d, bNew, b, c]
    }
    A = add32(A, a)
    B = add32(B, b)
    C = add32(C, c)
    D = add32(D, d)
  }

  const registers = [A, B, C, D]
  const digest = registers.map((word) => {
    const h = hex32(word)
    return `${h.slice(6, 8)}${h.slice(4, 6)}${h.slice(2, 4)}${h.slice(0, 2)}`
  }).join('').toLowerCase()

  return { message, messageHex: bytesToHex(bytes), paddedHex: bytesToHex(padded), registers, steps, digest }
}

export const hex32 = (value) => u32(value).toString(16).padStart(8, '0').toUpperCase()
export const bin32 = (value) => u32(value).toString(2).padStart(32, '0')
export const bytesToHex = (bytes) => Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0')).join('').toUpperCase()
export const diffBits = (a, b) => (u32(a) ^ u32(b)).toString(2).replaceAll('0', '').length
