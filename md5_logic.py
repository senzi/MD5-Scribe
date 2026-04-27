"""
MD5-Scribe Core Logic Module

Implements standard MD5 with full per-step instrumentation,
storing every atomic intermediate value for human verification.
"""

import struct
import math
import json
from typing import List, Tuple, Dict, Any

# MD5 constants K[i] = floor(2^32 * abs(sin(i+1)))
K = [int(2**32 * abs(math.sin(i + 1))) & 0xFFFFFFFF for i in range(64)]

# Shift amounts per round
S = (
    [7, 12, 17, 22] * 4 +
    [5, 9, 14, 20] * 4 +
    [4, 11, 16, 23] * 4 +
    [6, 10, 15, 21] * 4
)

# Message word index per step
M_IDX = (
    list(range(16)) +
    [(5*i + 1) % 16 for i in range(16)] +
    [(3*i + 5) % 16 for i in range(16)] +
    [(7*i) % 16 for i in range(16)]
)


def left_rotate(x: int, n: int) -> int:
    """32-bit left rotate."""
    x &= 0xFFFFFFFF
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def F(b: int, c: int, d: int) -> int:
    return ((b & c) | (~b & d)) & 0xFFFFFFFF


def G(b: int, c: int, d: int) -> int:
    return ((b & d) | (c & ~d)) & 0xFFFFFFFF


def H(b: int, c: int, d: int) -> int:
    return (b ^ c ^ d) & 0xFFFFFFFF


def I(b: int, c: int, d: int) -> int:
    return (c ^ (b | ~d)) & 0xFFFFFFFF


FUNC_BY_STEP = [F] * 16 + [G] * 16 + [H] * 16 + [I] * 16
FUNC_NAME_BY_STEP = ['F'] * 16 + ['G'] * 16 + ['H'] * 16 + ['I'] * 16


class MD5State:
    """
    Stateful MD5 engine that records every atomic intermediate
    so a human can verify step-by-step on paper.
    """

    def __init__(self):
        self.reset()

    def reset(self):
        self.A = 0x67452301
        self.B = 0xEFCDAB89
        self.C = 0x98BADCFE
        self.D = 0x10325476
        self.original_msg: bytes = b''
        self.padded_msg: bytes = b''
        self.steps: List[Dict[str, Any]] = []
        self.completed_steps: set = set()
        self.start_times: Dict[int, float] = {}
        self.end_times: Dict[int, float] = {}

    @property
    def registers(self) -> Tuple[int, int, int, int]:
        return (self.A, self.B, self.C, self.D)

    def _chunk_message(self, msg: bytes) -> List[bytes]:
        """Pad message and split into 64-byte chunks."""
        bit_len = (len(msg) * 8) & 0xFFFFFFFFFFFFFFFF
        # Append 0x80
        padded = msg + b'\x80'
        # Append 0x00 until length ≡ 56 (mod 64)
        while (len(padded) % 64) != 56:
            padded += b'\x00'
        # Append 64-bit little-endian length
        padded += struct.pack('<Q', bit_len)
        self.padded_msg = padded
        return [padded[i:i+64] for i in range(0, len(padded), 64)]

    def _process_chunk(self, chunk: bytes):
        """Process a single 64-byte chunk, recording all 64 steps."""
        # Unpack chunk into 16 little-endian 32-bit words
        M = list(struct.unpack('<16I', chunk))

        a, b, c, d = self.A, self.B, self.C, self.D

        for i in range(64):
            func = FUNC_BY_STEP[i]
            func_name = FUNC_NAME_BY_STEP[i]
            mj_idx = M_IDX[i]
            mj = M[mj_idx]
            ki = K[i]
            s = S[i]

            # --- Atomic computation with full instrumentation ---
            f_val = func(b, c, d) & 0xFFFFFFFF
            t1 = (a + f_val) & 0xFFFFFFFF
            t2 = (t1 + mj) & 0xFFFFFFFF
            t3 = (t2 + ki) & 0xFFFFFFFF
            rot = left_rotate(t3, s)
            b_new = (rot + b) & 0xFFFFFFFF

            # Store step data exactly as PRD specifies
            step_data = {
                "step_index": i,
                "registers_before": (a, b, c, d),
                "registers_after": (d, b_new, b, c),  # After rotation of variables
                "mj": mj,
                "mj_idx": mj_idx,
                "ki": ki,
                "s": s,
                "logic_func": func_name,
                "f_val": f_val,
                "correct_atoms": [t1, t2, t3, rot, b_new],
                "atom_names": ["T1 (A + f)", "T2 (T1 + M_j)", "T3 (T2 + K_i)", "ROT (Left Rotate)", "B_new (ROT + B)"]
            }
            self.steps.append(step_data)

            # Update registers for next step
            a, b, c, d = d, b_new, b, c

        # Add back to initial state
        self.A = (self.A + a) & 0xFFFFFFFF
        self.B = (self.B + b) & 0xFFFFFFFF
        self.C = (self.C + c) & 0xFFFFFFFF
        self.D = (self.D + d) & 0xFFFFFFFF

    def hash(self, msg: str | bytes) -> str:
        """Compute MD5 hash of message, recording all steps."""
        self.reset()
        if isinstance(msg, str):
            msg = msg.encode('utf-8')
        self.original_msg = msg
        chunks = self._chunk_message(msg)
        for chunk in chunks:
            self._process_chunk(chunk)
        # Return standard hex digest
        digest = b''.join(struct.pack('<I', x) for x in (self.A, self.B, self.C, self.D))
        return digest.hex()

    def get_step(self, step_index: int) -> Dict[str, Any]:
        if not (0 <= step_index < len(self.steps)):
            raise IndexError(f"Step {step_index} out of range (0-{len(self.steps)-1})")
        return self.steps[step_index]

    def get_final_digest(self) -> str:
        digest = b''.join(struct.pack('<I', x) for x in (self.A, self.B, self.C, self.D))
        return digest.hex()

    def get_atom_correct(self, step_index: int, atom_index: int) -> int:
        """Get the correct value for a specific atom."""
        step = self.get_step(step_index)
        return step["correct_atoms"][atom_index]

    def verify_atoms(self, step_index: int, answers: List[int]) -> List[Tuple[bool, int, int]]:
        """
        Verify a list of atom answers.
        Returns list of (is_correct, expected, actual) for each atom.
        """
        step = self.get_step(step_index)
        results = []
        for i, ans in enumerate(answers):
            expected = step["correct_atoms"][i]
            actual = ans & 0xFFFFFFFF
            results.append((expected == actual, expected, actual))
        return results

    def to_json(self, path: str):
        """Serialize state to JSON."""
        data = {
            "original_msg": self.original_msg.hex(),
            "padded_msg": self.padded_msg.hex(),
            "final_digest": self.get_final_digest(),
            "steps": self.steps,
            "completed_steps": list(self.completed_steps),
            "start_times": self.start_times,
            "end_times": self.end_times,
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def from_json(cls, path: str) -> "MD5State":
        """Deserialize state from JSON."""
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        state = cls()
        state.original_msg = bytes.fromhex(data["original_msg"])
        state.padded_msg = bytes.fromhex(data["padded_msg"])
        state.A, state.B, state.C, state.D = data["steps"][-1]["registers_after"] if data["steps"] else (0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476)
        # Actually recalculate properly
        state.hash(bytes.fromhex(data["original_msg"]))
        state.completed_steps = set(data.get("completed_steps", []))
        state.start_times = {int(k): v for k, v in data.get("start_times", {}).items()}
        state.end_times = {int(k): v for k, v in data.get("end_times", {}).items()}
        return state


def hex32(x: int) -> str:
    """Format a 32-bit int as 8-digit uppercase hex."""
    return f"{x & 0xFFFFFFFF:08X}"


def bin32(x: int) -> str:
    """Format a 32-bit int as 32-bit binary."""
    return f"{x & 0xFFFFFFFF:032b}"


def hex_to_binary_table() -> Dict[str, str]:
    """0-F to 4-bit binary mapping."""
    return {f"{i:X}": f"{i:04b}" for i in range(16)}


if __name__ == "__main__":
    # Quick sanity check
    state = MD5State()
    result = state.hash("hello")
    print(f"MD5('hello') = {result}")
    assert result == "5d41402abc4b2a76b9719d911017c592", "MD5 mismatch!"
    print("Sanity check passed.")
