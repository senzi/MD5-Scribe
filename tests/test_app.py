"""
Integration tests for the Flask app (app.py)
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import tests.mock_flask as mock_flask

import importlib.util
_app_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app.py")
_spec = importlib.util.spec_from_file_location("app", _app_path)
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)
sys.modules["app"] = app


class TestClient:
    def __init__(self):
        self.client = app.app.test_client()
        self.client.testing = True

    def post_init(self, message="test"):
        return self.client.post("/init", data={"message": message}, follow_redirects=True)

    def get_step(self, step_id):
        return self.client.get(f"/step/{step_id}")

    def get_print(self, step_id):
        return self.client.get(f"/step/{step_id}/print")

    def get_verify(self, step_id):
        return self.client.get(f"/step/{step_id}/verify")

    def post_verify(self, step_id, atoms):
        data = {f"atom_{i}": atoms[i] for i in range(len(atoms))}
        return self.client.post(f"/step/{step_id}/verify", data=data, follow_redirects=True)

    def get_report(self):
        return self.client.get("/report")

    def get_markdown_report(self):
        return self.client.get("/report/markdown")

    def get_final_print(self):
        return self.client.get("/final/print")

    def get_final_verify(self):
        return self.client.get("/final/verify")

    def post_final_verify(self, digest):
        return self.client.post("/final/verify", data={"digest": digest}, follow_redirects=True)

    def get_api_state(self):
        return self.client.get("/api/state")


def test_home_page():
    client = TestClient()
    rv = client.client.get("/")
    assert rv.status_code == 200
    assert b"MD5-Scribe" in rv.data
    print("OK test_home_page")


def test_init_state():
    client = TestClient()
    rv = client.post_init("hello")
    assert rv.status_code == 200
    assert b"Step 0" in rv.data or b"step" in rv.data.lower()
    print("OK test_init_state")


def test_step_routes():
    client = TestClient()
    client.post_init("step_test")

    rv = client.get_step(0)
    assert rv.status_code == 200
    assert b"Step 0" in rv.data

    rv = client.get_print(0)
    assert rv.status_code == 200
    assert "手算工单".encode() in rv.data

    rv = client.get_verify(0)
    assert rv.status_code == 200
    assert "输入您的手算结果".encode() in rv.data
    print("OK test_step_routes")


def test_verify_correct_atoms():
    client = TestClient()
    client.post_init("verify_correct")
    state = app.get_state()
    correct = state.steps[0]["correct_atoms"]
    hex_answers = [f"{v:08X}" for v in correct]
    rv = client.post_verify(0, hex_answers)
    assert rv.status_code == 200
    assert "正确".encode() in rv.data or b"Step 1" in rv.data
    print("OK test_verify_correct_atoms")


def test_verify_wrong_atoms():
    client = TestClient()
    client.post_init("verify_wrong")
    wrong = ["00000000"] * 5
    rv = client.post_verify(0, wrong)
    assert rv.status_code == 200
    assert "错误".encode() in rv.data
    print("OK test_verify_wrong_atoms")


def test_step_unlocking():
    client = TestClient()
    client.post_init("unlock")
    rv = client.get_step(1)
    assert rv.status_code == 200
    assert "未解锁".encode() in rv.data or b"locked" in rv.data.lower()
    state = app.get_state()
    correct = [f"{v:08X}" for v in state.steps[0]["correct_atoms"]]
    client.post_verify(0, correct)
    rv = client.get_step(1)
    assert rv.status_code == 200
    assert "未解锁".encode() not in rv.data
    print("OK test_step_unlocking")


def test_report_page():
    client = TestClient()
    client.post_init("report_test")
    rv = client.get_report()
    assert rv.status_code == 200
    assert "计算报告".encode() in rv.data
    assert os.path.exists(app.REPORT_PATH)
    print("OK test_report_page")


def test_markdown_report_route():
    client = TestClient()
    client.post_init("markdown_report")
    rv = client.get_markdown_report()
    assert rv.status_code == 200
    assert b"MD5-Scribe Final Report" in rv.data
    assert os.path.exists(app.REPORT_PATH)
    print("OK test_markdown_report_route")


def test_log_file_initialized():
    client = TestClient()
    client.post_init("log_init")
    assert os.path.exists(app.LOG_PATH)
    with open(app.LOG_PATH, "r", encoding="utf-8") as f:
        assert json.load(f) == []
    print("OK test_log_file_initialized")


def test_final_print_requires_completed_rounds():
    client = TestClient()
    client.post_init("final_locked")
    rv = client.get_final_print()
    assert rv.status_code in (200, 302)
    assert "请先完成全部".encode() in rv.data or rv.status_code == 302
    print("OK test_final_print_requires_completed_rounds")


def test_final_verify_correct_digest():
    client = TestClient()
    client.post_init("final_digest")
    state = app.get_state()
    state.completed_steps = set(range(len(state.steps)))
    digest = state.get_final_digest()
    rv = client.post_final_verify(digest.upper())
    assert rv.status_code == 200
    assert "计算报告".encode() in rv.data
    assert app.get_state().final_verified is True
    print("OK test_final_verify_correct_digest")


def test_final_verify_wrong_digest():
    client = TestClient()
    client.post_init("final_wrong")
    state = app.get_state()
    state.completed_steps = set(range(len(state.steps)))
    rv = client.post_final_verify("0" * 32)
    assert rv.status_code == 200
    assert "结果不匹配".encode() in rv.data
    assert app.get_state().final_verified is False
    with open(app.LOG_PATH, "r", encoding="utf-8") as f:
        logs = json.load(f)
    assert logs[-1]["atom_name"] == "Final MD5 digest"
    print("OK test_final_verify_wrong_digest")


def test_api_state():
    client = TestClient()
    client.post_init("api_test")
    rv = client.get_api_state()
    assert rv.status_code == 200
    data = json.loads(rv.data)
    assert data["steps_total"] == 64
    print("OK test_api_state")


def test_verify_hex_prefix():
    client = TestClient()
    client.post_init("hex_prefix")
    state = app.get_state()
    correct = [f"0x{v:08X}" for v in state.steps[0]["correct_atoms"]]
    rv = client.post_verify(0, correct)
    assert rv.status_code == 200
    assert "正确".encode() in rv.data or b"Step 1" in rv.data
    print("OK test_verify_hex_prefix")


def test_verify_decimal_input():
    client = TestClient()
    client.post_init("decimal")
    state = app.get_state()
    correct = [str(v) for v in state.steps[0]["correct_atoms"]]
    rv = client.post_verify(0, correct)
    assert rv.status_code == 200
    assert "正确".encode() in rv.data or b"Step 1" in rv.data
    print("OK test_verify_decimal_input")


def test_session_isolation():
    client1 = TestClient()
    client1.post_init("session_a")
    state_a = app.get_state()
    client2 = TestClient()
    client2.post_init("session_b")
    state_b = app.get_state()
    assert state_a.original_msg != state_b.original_msg
    print("OK test_session_isolation")


if __name__ == "__main__":
    test_home_page()
    test_init_state()
    test_step_routes()
    test_verify_correct_atoms()
    test_verify_wrong_atoms()
    test_step_unlocking()
    test_report_page()
    test_markdown_report_route()
    test_log_file_initialized()
    test_final_print_requires_completed_rounds()
    test_final_verify_correct_digest()
    test_final_verify_wrong_digest()
    test_api_state()
    test_verify_hex_prefix()
    test_verify_decimal_input()
    test_session_isolation()
    print("\n=== All app integration tests passed! ===")
