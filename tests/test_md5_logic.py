"""
Unit tests for md5_logic.py

Tests:
  - Standard MD5 vectors
  - Per-step atomic value correctness
  - State serialization
  - Verification logic
"""

import sys
import os
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from md5_logic import MD5State, left_rotate, F, G, H, I, hex32, bin32, hex_to_binary_table

# Known MD5 test vectors
TEST_VECTORS = [
    ("", "d41d8cd98f00b204e9800998ecf8427e"),
    ("a", "0cc175b9c0f1b6a831c399e269772661"),
    ("abc", "900150983cd24fb0d6963f7d28e17f72"),
    ("message digest", "f96b697d7cb7938d525a2f31aaf161d0"),
    ("abcdefghijklmnopqrstuvwxyz", "c3fcd3d76192e4007dfb496cca67e13b"),
    ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
     "d174ab98d277d9f5a5611c2c9f419d9f"),
    ("12345678901234567890123456789012345678901234567890123456789012345678901234567890",
     "57edf4a22be3c955ac49da2e2107b67a"),
]


def test_standard_vectors():
    """MD5 must match standard RFC 1321 test vectors."""
    state = MD5State()
    for msg, expected in TEST_VECTORS:
        result = state.hash(msg)
        assert result == expected, f"MD5('{msg}') = {result}, expected {expected}"
    print("✓ test_standard_vectors passed")


def test_padding_single_block():
    """A short message should produce exactly one 64-byte block after padding."""
    state = MD5State()
    state.hash("abc")
    assert len(state.padded_msg) == 64, f"Expected 64 bytes, got {len(state.padded_msg)}"
    print("✓ test_padding_single_block passed")


def test_padding_multi_block():
    """A long message (e.g. 448 bits) should produce two 64-byte blocks."""
    state = MD5State()
    # 55 bytes = 440 bits, plus 0x80 + 7 zeroes + 8 length = 448 bits = 56 bytes,
    # then needs another block for the length. Wait, 55 bytes pads to 64 (one block).
    # 56 bytes = 448 bits, pads to 120 bytes (one full + 56) — no, 56 + 1 + 7 = 64.
    # Let's use 57 bytes which should produce 2 blocks.
    state.hash("a" * 57)
    assert len(state.padded_msg) == 128, f"Expected 128 bytes, got {len(state.padded_msg)}"
    print("✓ test_padding_multi_block passed")


def test_step_count():
    """A single block should produce exactly 64 steps."""
    state = MD5State()
    state.hash("test")
    assert len(state.steps) == 64, f"Expected 64 steps, got {len(state.steps)}"
    print("✓ test_step_count passed")


def test_step_data_structure():
    """Each step must contain all required keys."""
    state = MD5State()
    state.hash("x")
    required_keys = {
        "step_index", "registers_before", "registers_after",
        "mj", "mj_idx", "ki", "s", "logic_func",
        "f_val", "correct_atoms", "atom_names"
    }
    for i, step in enumerate(state.steps):
        missing = required_keys - set(step.keys())
        assert not missing, f"Step {i} missing keys: {missing}"
    print("✓ test_step_data_structure passed")


def test_atom_count():
    """Each step must have exactly 5 correct atoms."""
    state = MD5State()
    state.hash("y")
    for i, step in enumerate(state.steps):
        assert len(step["correct_atoms"]) == 5, f"Step {i}: expected 5 atoms, got {len(step['correct_atoms'])}"
        assert len(step["atom_names"]) == 5, f"Step {i}: expected 5 names, got {len(step['atom_names'])}"
    print("✓ test_atom_count passed")


def test_round_functions_sequence():
    """Steps 0-15 use F, 16-31 use G, 32-47 use H, 48-63 use I."""
    state = MD5State()
    state.hash("z")
    for i in range(64):
        expected = ['F'] * 16 + ['G'] * 16 + ['H'] * 16 + ['I'] * 16
        assert state.steps[i]["logic_func"] == expected[i], f"Step {i}: expected {expected[i]}"
    print("✓ test_round_functions_sequence passed")


def test_left_rotate():
    """Left rotate must work correctly."""
    assert left_rotate(0x80000000, 1) == 0x00000001, "Rotate 0x80000000 left by 1"
    assert left_rotate(0x00000001, 1) == 0x00000002, "Rotate 0x1 left by 1"
    assert left_rotate(0xFFFFFFFF, 5) == 0xFFFFFFFF, "Rotate all-1s by any amount"
    assert left_rotate(0x12345678, 0) == 0x12345678, "Rotate by 0"
    print("✓ test_left_rotate passed")


def test_logic_functions():
    """Logic functions F, G, H, I must match MD5 spec."""
    # F(B,C,D) = (B & C) | (~B & D)
    assert F(0xFFFFFFFF, 0xFFFFFFFF, 0x00000000) == 0xFFFFFFFF
    assert F(0x00000000, 0xFFFFFFFF, 0xFFFFFFFF) == 0xFFFFFFFF
    assert F(0xFFFFFFFF, 0x00000000, 0xFFFFFFFF) == 0x00000000

    # G(B,C,D) = (B & D) | (C & ~D)
    assert G(0xFFFFFFFF, 0x00000000, 0xFFFFFFFF) == 0xFFFFFFFF
    assert G(0x00000000, 0xFFFFFFFF, 0x00000000) == 0xFFFFFFFF

    # H(B,C,D) = B ^ C ^ D
    assert H(0xFFFFFFFF, 0x00000000, 0x00000000) == 0xFFFFFFFF
    assert H(0xFFFFFFFF, 0xFFFFFFFF, 0x00000000) == 0x00000000

    # I(B,C,D) = C ^ (B | ~D)
    assert I(0x00000000, 0xFFFFFFFF, 0xFFFFFFFF) == 0xFFFFFFFF
    print("✓ test_logic_functions passed")


def test_verify_atoms_correct():
    """Verifying with correct answers should return all True."""
    state = MD5State()
    state.hash("verify")
    answers = state.steps[0]["correct_atoms"]
    results = state.verify_atoms(0, answers)
    assert all(r[0] for r in results), "All atoms should be correct"
    print("✓ test_verify_atoms_correct passed")


def test_verify_atoms_wrong():
    """Verifying with wrong answers should return some False."""
    state = MD5State()
    state.hash("verify")
    answers = [x + 1 for x in state.steps[0]["correct_atoms"]]
    results = state.verify_atoms(0, answers)
    assert any(not r[0] for r in results), "Some atoms should be wrong"
    print("✓ test_verify_atoms_wrong passed")


def test_hex32_format():
    """hex32 must produce 8-digit uppercase hex."""
    assert hex32(0) == "00000000"
    assert hex32(0x123) == "00000123"
    assert hex32(0xFFFFFFFF) == "FFFFFFFF"
    print("✓ test_hex32_format passed")


def test_bin32_format():
    """bin32 must produce 32-bit binary."""
    assert bin32(0) == "0" * 32
    assert len(bin32(0x12345678)) == 32
    assert bin32(0xFFFFFFFF) == "1" * 32
    print("✓ test_bin32_format passed")


def test_state_serialization():
    """State should survive round-trip JSON serialization."""
    state = MD5State()
    state.hash("serialize")
    state.completed_steps = {0, 1, 2}

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        path = f.name

    try:
        state.to_json(path)
        restored = MD5State.from_json(path)
        assert restored.get_final_digest() == state.get_final_digest()
        assert restored.completed_steps == state.completed_steps
    finally:
        os.unlink(path)

    print("✓ test_state_serialization passed")


def test_atom_correctness_consistency():
    """Recomputing the same message should yield identical atoms."""
    state1 = MD5State()
    state1.hash("consistency")
    state2 = MD5State()
    state2.hash("consistency")

    for i in range(64):
        assert state1.steps[i]["correct_atoms"] == state2.steps[i]["correct_atoms"], \
            f"Step {i} atoms differ"
    print("✓ test_atom_correctness_consistency passed")


def test_registers_after_update():
    """After each step, registers_before of step n+1 should match registers_after of step n."""
    state = MD5State()
    state.hash("chain")
    for i in range(63):
        after = state.steps[i]["registers_after"]
        before_next = state.steps[i + 1]["registers_before"]
        assert after == before_next, f"Step {i} -> {i+1} register chain broken"
    print("✓ test_registers_after_update passed")


if __name__ == "__main__":
    test_standard_vectors()
    test_padding_single_block()
    test_padding_multi_block()
    test_step_count()
    test_step_data_structure()
    test_atom_count()
    test_round_functions_sequence()
    test_left_rotate()
    test_logic_functions()
    test_verify_atoms_correct()
    test_verify_atoms_wrong()
    test_hex32_format()
    test_bin32_format()
    test_state_serialization()
    test_atom_correctness_consistency()
    test_registers_after_update()
    print("\n=== All md5_logic tests passed! ===")
