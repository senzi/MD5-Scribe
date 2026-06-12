import test from 'node:test'
import assert from 'node:assert/strict'
import { F, G, H, I, bin32, computeMd5, hex32, leftRotate } from '../src/md5.js'

const vectors = [
  ['', 'd41d8cd98f00b204e9800998ecf8427e'],
  ['a', '0cc175b9c0f1b6a831c399e269772661'],
  ['abc', '900150983cd24fb0d6963f7d28e17f72'],
  ['message digest', 'f96b697d7cb7938d525a2f31aaf161d0'],
  ['abcdefghijklmnopqrstuvwxyz', 'c3fcd3d76192e4007dfb496cca67e13b'],
  ['ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', 'd174ab98d277d9f5a5611c2c9f419d9f'],
]

test('matches RFC 1321 vectors', () => {
  for (const [message, expected] of vectors) assert.equal(computeMd5(message).digest, expected)
})

test('records the complete single-block calculation', () => {
  const result = computeMd5('abc')
  assert.equal(result.steps.length, 64)
  assert.equal(result.paddedHex.length, 128)
  assert.deepEqual(result.steps[0].registersAfter, result.steps[1].registersBefore)
  assert.equal(result.steps[63].logicFunc, 'I')
  assert.equal(result.steps[0].correctAtoms.length, 5)
})

test('32-bit helpers keep unsigned semantics', () => {
  assert.equal(leftRotate(0x80000000, 1), 1)
  assert.equal(F(0xffffffff, 0xffffffff, 0), 0xffffffff)
  assert.equal(G(0, 0xffffffff, 0), 0xffffffff)
  assert.equal(H(0xffffffff, 0xffffffff, 0), 0)
  assert.equal(I(0, 0xffffffff, 0xffffffff), 0xffffffff)
  assert.equal(hex32(0x123), '00000123')
  assert.equal(bin32(0xffffffff), '1'.repeat(32))
})
