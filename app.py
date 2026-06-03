"""
MD5-Scribe Flask Application

Routes:
  GET  /                         -> Input form
  POST /init                     -> Initialize MD5 state
  GET  /step/<n>                 -> Control panel for step n
  GET  /step/<n>/print           -> Printable worksheet (PDF mode)
  GET  /step/<n>/verify          -> Verification form
  POST /step/<n>/verify          -> Submit answers
  GET  /final/print              -> Final digest worksheet
  GET  /final/verify             -> Final digest verification form
  POST /final/verify             -> Submit final digest
  GET  /report                   -> Final report
  GET  /report/markdown          -> Markdown final report
"""

import os
import json
import time
from datetime import datetime
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify, Response
)
from md5_logic import MD5State, hex32, bin32, hex_to_binary_table

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.jinja_env.globals["zip"] = zip

# In-memory store for active sessions (in production, use Redis or DB)
STATE_STORE: dict = {}
CURRENT_STATE_ID = "current"
MAX_SINGLE_BLOCK_MESSAGE_BYTES = 55
STATE_PATH = "current_state.json"
LOG_PATH = "session_log.json"
REPORT_PATH = "final_report.md"

# --- Helpers ---

def get_state_id() -> str:
    return session.get("state_id")

def get_state() -> MD5State | None:
    sid = get_state_id()
    if sid and sid in STATE_STORE:
        return STATE_STORE[sid]
    state = load_current_state()
    if state is not None:
        session["state_id"] = CURRENT_STATE_ID
        STATE_STORE[CURRENT_STATE_ID] = state
        return state
    return None

def save_state(state: MD5State):
    state.updated_at = time.time()
    sid = get_state_id() or CURRENT_STATE_ID
    session["state_id"] = sid
    if sid:
        STATE_STORE[sid] = state
    persist_current_state(state)

def ensure_state() -> MD5State:
    state = get_state()
    if state is None:
        raise RuntimeError("No active MD5 session. Please start from the home page.")
    return state


def load_current_state() -> MD5State | None:
    if not os.path.exists(STATE_PATH):
        return None
    try:
        return MD5State.from_json(STATE_PATH)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def persist_current_state(state: MD5State):
    try:
        state.to_json(STATE_PATH)
    except OSError:
        pass


def clear_current_state():
    STATE_STORE.pop(CURRENT_STATE_ID, None)
    session.pop("state_id", None)
    for path in (STATE_PATH, LOG_PATH, REPORT_PATH):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            pass

def log_entry(step_index: int, expected: int, actual: int, atom_name: str):
    """Append verification attempt to session_log.json."""
    try:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "step_index": step_index,
            "atom_name": atom_name,
            "expected": hex32(expected),
            "actual": hex32(actual),
            "diff_bits": bin(expected ^ actual).count("1"),
        }
        logs = []
        try:
            with open(LOG_PATH, "r", encoding="utf-8") as f:
                logs = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logs = []
        logs.append(entry)
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
    except OSError:
        pass  # Fail silently if filesystem restricts writes


def log_digest_entry(expected: str, actual: str):
    """Append final digest verification failure to session_log.json."""
    try:
        diff_bits = None
        if len(actual) == 32 and all(c in "0123456789abcdef" for c in actual):
            diff_bits = bin(int(expected, 16) ^ int(actual, 16)).count("1")
        logs = load_logs()
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "step_index": "final",
            "atom_name": "Final MD5 digest",
            "expected": expected.upper(),
            "actual": actual.upper(),
            "diff_bits": diff_bits if diff_bits is not None else "格式错误",
        })
        with open(LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(logs, f, indent=2, ensure_ascii=False)
    except OSError:
        pass


def reset_runtime_artifacts():
    for path in (LOG_PATH, REPORT_PATH):
        try:
            if path == LOG_PATH:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2, ensure_ascii=False)
            elif os.path.exists(path):
                os.remove(path)
        except OSError:
            pass


def load_logs():
    try:
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def analyze_error_counts(logs):
    error_counts = {"加法": 0, "逻辑函数": 0, "循环左移": 0, "最终拼接": 0, "其他": 0}
    for log in logs:
        name = log.get("atom_name", "")
        if "A + f" in name or "T1 +" in name or "T2 +" in name or "ROT + B" in name:
            error_counts["加法"] += 1
        elif "Final" in name or "digest" in name.lower() or "MD5" in name:
            error_counts["最终拼接"] += 1
        elif "f" in name.lower() or "Func" in name:
            error_counts["逻辑函数"] += 1
        elif "Rotate" in name or "ROT" in name:
            error_counts["循环左移"] += 1
        else:
            error_counts["其他"] += 1
    return error_counts


def build_timeline(state: MD5State):
    timeline = []
    for i in range(len(state.steps)):
        if (
            i in state.start_times
            or i in state.print_times
            or i in state.verify_open_times
            or i in state.verify_submit_times
            or i in state.completed_steps
        ):
            start_t = state.start_times.get(i) or state.verify_open_times.get(i)
            end_t = state.end_times.get(i)
            duration = round(end_t - start_t, 2) if start_t and end_t else None
            timeline.append({
                "step": i,
                "duration": duration,
                "completed": i in state.completed_steps,
                "printed_at": state.print_times.get(i),
                "verify_opened_at": state.verify_open_times.get(i),
                "submitted_at": state.verify_submit_times.get(i),
                "completed_at": state.end_times.get(i),
            })
    return timeline


def write_markdown_report(state: MD5State, logs, error_counts, timeline):
    total = len(state.steps)
    lines = [
        "# MD5-Scribe Final Report",
        "",
        f"- Original message: `{state.original_msg.decode('utf-8', errors='replace')}`",
        f"- Final digest: `{state.get_final_digest()}`",
        f"- Completed rounds: {len(state.completed_steps)} / {total}",
        f"- Final digest verification: {'completed' if state.final_verified else 'not completed'}",
        f"- Total logged errors: {len(logs)}",
        "",
        "## Error Analysis",
        "",
    ]
    for name, count in error_counts.items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## Timeline", ""])
    if timeline:
        lines.append("| Step | Completed | Duration | Events |")
        lines.append("| --- | --- | --- | --- |")
        for item in timeline:
            duration = f"{item['duration']}s" if item["duration"] is not None else "in progress / not completed"
            events = []
            if item.get("printed_at"):
                events.append(f"printed {format_time(item['printed_at'])}")
            if item.get("verify_opened_at"):
                events.append(f"verify opened {format_time(item['verify_opened_at'])}")
            if item.get("submitted_at"):
                events.append(f"submitted {format_time(item['submitted_at'])}")
            lines.append(
                f"| {item['step']} | {'yes' if item['completed'] else 'no'} | "
                f"{duration} | {'; '.join(events)} |"
            )
    else:
        lines.append("No timing data recorded.")
    lines.extend(["", "## Audit Trail", ""])
    if logs:
        lines.append("| Time | Step | Operation | Expected | Actual | Diff Bits |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        for log in logs:
            lines.append(
                f"| {log.get('timestamp', '')} | {log.get('step_index', '')} | "
                f"{log.get('atom_name', '')} | `{log.get('expected', '')}` | "
                f"`{log.get('actual', '')}` | {log.get('diff_bits', '')} |"
            )
    else:
        lines.append("No incorrect attempts were logged.")
    lines.extend(["", "## Final Registers", ""])
    for row in final_register_rows(state):
        lines.append(f"- {row['name']}: `{row['word']}`")

    markdown = "\n".join(lines) + "\n"
    try:
        with open(REPORT_PATH, "w", encoding="utf-8") as f:
            f.write(markdown)
    except OSError:
        pass
    return markdown


def all_rounds_completed(state: MD5State) -> bool:
    return state.completed_steps == set(range(len(state.steps)))


def first_incomplete_step(state: MD5State) -> int:
    for step_id in range(len(state.steps)):
        if step_id not in state.completed_steps:
            return step_id
    return max(len(state.steps) - 1, 0)


def final_register_rows(state: MD5State):
    return [
        {"name": name, "word": hex32(reg)}
        for name, reg in zip(["A", "B", "C", "D"], state.registers)
    ]


def normalize_digest(raw: str) -> str:
    return "".join(raw.strip().split()).lower().removeprefix("0x")


def format_time(ts):
    if not ts:
        return ""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")

# --- Routes ---

@app.route("/")
def index():
    state = get_state()
    next_step = first_incomplete_step(state) if state else 0
    return render_template(
        "index.html",
        current_state=state,
        next_step=next_step,
        max_message_bytes=MAX_SINGLE_BLOCK_MESSAGE_BYTES,
        format_time=format_time,
    )


@app.route("/init", methods=["POST"])
def init_state():
    msg = request.form.get("message", "")
    if not msg:
        flash("请输入一个非空字符串。", "error")
        return redirect(url_for("index"))
    msg_bytes = msg.encode("utf-8")
    if len(msg_bytes) > MAX_SINGLE_BLOCK_MESSAGE_BYTES:
        flash(
            f"当前训练模式只支持单个 MD5 消息块：原始消息最多 {MAX_SINGLE_BLOCK_MESSAGE_BYTES} bytes，当前为 {len(msg_bytes)} bytes。",
            "error",
        )
        return redirect(url_for("index"))

    state = MD5State()
    state.hash(msg)

    clear_current_state()
    sid = CURRENT_STATE_ID
    session["state_id"] = sid
    STATE_STORE[sid] = state

    reset_runtime_artifacts()
    save_state(state)

    return redirect(url_for("step_control", step_id=0))


@app.route("/step/<int:step_id>")
def step_control(step_id: int):
    state = ensure_state()
    total = len(state.steps)
    if not (0 <= step_id < total):
        flash("无效的步骤编号。", "error")
        return redirect(url_for("index"))

    # Determine unlocked steps (step 0 always unlocked, n+1 unlocked after n is completed)
    unlocked = {0} | {s + 1 for s in state.completed_steps}
    is_unlocked = step_id in unlocked

    step_data = state.get_step(step_id)

    return render_template(
        "step.html",
        step_id=step_id,
        total=total,
        is_unlocked=is_unlocked,
        completed=state.completed_steps,
        step_data=step_data,
        registers=step_data["registers_before"],
        hex32=hex32,
        bin32=bin32,
        message=state.original_msg.decode('utf-8', errors='replace'),
    )


@app.route("/step/<int:step_id>/print")
def step_print(step_id: int):
    state = ensure_state()
    total = len(state.steps)
    if not (0 <= step_id < total):
        flash("无效的步骤编号。", "error")
        return redirect(url_for("index"))

    step_data = state.get_step(step_id)
    hex_bin_map = hex_to_binary_table()
    state.print_times[step_id] = time.time()
    save_state(state)

    return render_template(
        "print.html",
        step_id=step_id,
        total=total,
        step_data=step_data,
        registers=step_data["registers_before"],
        hex32=hex32,
        bin32=bin32,
        hex_bin_map=hex_bin_map,
        message=state.original_msg.decode('utf-8', errors='replace'),
    )


@app.route("/step/<int:step_id>/verify", methods=["GET", "POST"])
def step_verify(step_id: int):
    state = ensure_state()
    total = len(state.steps)
    if not (0 <= step_id < total):
        flash("无效的步骤编号。", "error")
        return redirect(url_for("index"))

    # Check unlock status
    unlocked = {0} | {s + 1 for s in state.completed_steps}
    is_unlocked = step_id in unlocked
    if not is_unlocked:
        flash(f"步骤 {step_id} 尚未解锁，请先完成前面的步骤。", "error")
        return redirect(url_for("step_control", step_id=step_id))

    step_data = state.get_step(step_id)

    if request.method == "POST":
        state.verify_submit_times[step_id] = time.time()
        save_state(state)
        # Parse submitted atom answers
        answers = []
        errors = []
        raw_answers = []
        for i in range(5):
            field_name = f"atom_{i}"
            raw = request.form.get(field_name, "").strip().upper()
            raw_answers.append(raw)
            if not raw:
                errors.append(f"原子运算 {i+1} 未填写。")
                answers.append(0)
                continue
            if len(raw) != 8 or any(c not in "0123456789ABCDEF" for c in raw):
                errors.append(f"原子运算 {i+1} 需要填写 8 位十六进制符号。")
                answers.append(0)
                continue
            val = int(raw, 16)
            answers.append(val & 0xFFFFFFFF)

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "verify.html",
                step_id=step_id,
                total=total,
                step_data=step_data,
                registers=step_data["registers_before"],
                hex32=hex32,
                bin32=bin32,
                answers=answers,
                raw_answers=raw_answers,
                verification=None,
                message=state.original_msg.decode('utf-8', errors='replace'),
            )

        # Verify each atom
        results = state.verify_atoms(step_id, answers)
        all_correct = all(r[0] for r in results)

        # Log every attempt
        for i, (ok, expected, actual) in enumerate(results):
            if not ok:
                log_entry(step_id, expected, actual, step_data["atom_names"][i])

        hex_bin_map = hex_to_binary_table()
        if all_correct:
            state.completed_steps.add(step_id)
            # Record timing
            if step_id in state.start_times:
                state.end_times[step_id] = time.time()
            save_state(state)
            flash("🎉 全部原子运算正确！步骤已解锁。", "success")
            next_step = step_id + 1
            if next_step < total:
                return redirect(url_for("step_control", step_id=next_step))
            else:
                return redirect(url_for("final_verify"))

        # Build detailed per-atom feedback
        verification = []
        for i, (ok, expected, actual) in enumerate(results):
            feedback = {
                "ok": ok,
                "name": step_data["atom_names"][i],
                "expected_hex": hex32(expected),
                "actual_hex": hex32(actual),
                "expected_bin": bin32(expected),
                "actual_bin": bin32(actual),
                "diff_positions": [],
            }
            if not ok:
                exp_str = feedback["expected_hex"]
                act_str = feedback["actual_hex"]
                for pos, (e, a) in enumerate(zip(exp_str, act_str)):
                    if e != a:
                        feedback["diff_positions"].append({
                            "pos": pos,
                            "expected": e,
                            "actual": a,
                            "expected_bin": hex_bin_map.get(e, ""),
                            "actual_bin": hex_bin_map.get(a, ""),
                        })
            verification.append(feedback)

        return render_template(
            "verify.html",
            step_id=step_id,
            total=total,
            step_data=step_data,
            registers=step_data["registers_before"],
            hex32=hex32,
            bin32=bin32,
            answers=answers,
            raw_answers=[hex32(a) for a in answers],
            verification=verification,
            message=state.original_msg.decode('utf-8', errors='replace'),
        )

    # GET
    # Record start time for this step if not already recorded
    if step_id not in state.start_times:
        state.start_times[step_id] = time.time()
    state.verify_open_times[step_id] = time.time()
    save_state(state)

    return render_template(
        "verify.html",
        step_id=step_id,
        total=total,
        step_data=step_data,
        registers=step_data["registers_before"],
        hex32=hex32,
        bin32=bin32,
        answers=[],
        raw_answers=[],
        verification=None,
        message=state.original_msg.decode('utf-8', errors='replace'),
    )


@app.route("/final/print")
def final_print():
    state = ensure_state()
    if not all_rounds_completed(state):
        flash(f"请先完成全部 {len(state.steps)} 轮步骤，再生成最终摘要工单。", "error")
        return redirect(url_for("step_control", step_id=first_incomplete_step(state)))

    state.final_print_time = time.time()
    save_state(state)

    return render_template(
        "final_print.html",
        registers=state.registers,
        register_rows=final_register_rows(state),
        hex32=hex32,
        message=state.original_msg.decode('utf-8', errors='replace'),
    )


@app.route("/final/verify", methods=["GET", "POST"])
def final_verify():
    state = ensure_state()
    if not all_rounds_completed(state):
        flash(f"请先完成全部 {len(state.steps)} 轮步骤，再验证最终 MD5。", "error")
        return redirect(url_for("step_control", step_id=first_incomplete_step(state)))

    expected = state.get_final_digest()
    actual = ""
    verification = None

    if request.method == "POST":
        state.final_verify_submit_time = time.time()
        save_state(state)
        actual = normalize_digest(request.form.get("digest", ""))
        is_hex = len(actual) == 32 and all(c in "0123456789abcdef" for c in actual)
        ok = is_hex and actual == expected
        verification = {"ok": ok, "format_ok": is_hex, "actual": actual.upper()}

        if ok:
            state.final_verified = True
            save_state(state)
            flash("最终 MD5 拼接正确！", "success")
            return redirect(url_for("final_report"))
        log_digest_entry(expected, actual)
    else:
        state.final_verify_open_time = time.time()
        save_state(state)

    return render_template(
        "final_verify.html",
        register_rows=final_register_rows(state),
        last_step_id=len(state.steps) - 1,
        hex32=hex32,
        answer=actual.upper(),
        verification=verification,
        message=state.original_msg.decode('utf-8', errors='replace'),
    )


@app.route("/report")
def final_report():
    state = ensure_state()
    total = len(state.steps)

    logs = load_logs()
    error_counts = analyze_error_counts(logs)
    timeline = build_timeline(state)
    write_markdown_report(state, logs, error_counts, timeline)

    return render_template(
        "report.html",
        total=total,
        completed=len(state.completed_steps),
        logs=logs,
        error_counts=error_counts,
        timeline=timeline,
        final_digest=state.get_final_digest(),
        final_verified=state.final_verified,
        format_time=format_time,
        message=state.original_msg.decode('utf-8', errors='replace'),
    )


@app.route("/report/markdown")
def markdown_report():
    state = ensure_state()
    logs = load_logs()
    error_counts = analyze_error_counts(logs)
    timeline = build_timeline(state)
    markdown = write_markdown_report(state, logs, error_counts, timeline)
    return Response(markdown, content_type="text/markdown; charset=utf-8")


@app.route("/api/state")
@app.route("/api/state")
def api_state():
    """Debug endpoint to inspect current state."""
    state = get_state()
    if state is None:
        return jsonify({"error": "No active state"}), 404
    return jsonify({
        "steps_total": len(state.steps),
        "completed": list(state.completed_steps),
        "final_verified": state.final_verified,
        "final_digest": state.get_final_digest(),
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)
