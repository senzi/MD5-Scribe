# MD5-Scribe

MD5-Scribe 是一个用于学习和校验 MD5 手算过程的人机协作系统。它会生成可打印工单，并通过网页表单逐轮验证手算结果。

## 功能

- 根据输入消息生成 MD5 的 64 轮计算步骤。
- 为每一轮提供可打印的手算工单。
- 在学习者需要手算的位置隐藏中间值，保留填写空间。
- 逐轮验证 5 个原子计算结果：
  - `T1 = A + f`
  - `T2 = T1 + M_j`
  - `T3 = T2 + K_i`
  - `ROT = RotateLeft(T3, s)`
  - `B_new = ROT + B`
- 验证输入限制为 8 位十六进制字符，并提供跟随页面滚动的浮动十六进制键盘，方便快速录入。
- 提供最终摘要工单与最终验证步骤，用于检查 `A/B/C/D` 的小端字节序转换和最终摘要拼接。
- 仅在第一张打印工单中附带十六进制/二进制对照表。

## 安装

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 运行

```bash
python app.py
```

然后打开：

```text
http://localhost:5000
```

## 测试

```bash
python -m pytest
```

核心 MD5 逻辑也可以单独运行测试：

```bash
python tests/test_md5_logic.py
```

## 工单说明

打印工单面向纸笔手算设计。`f`、`T1`、`T2`、`T3`、`ROT` 和 `B_new` 等结果会留空，由学习者手动填写。步骤 05 提供两组 32 位格子：第一组用于先把 `T3` 转成二进制，第二组用于重新排列循环左移后的 `ROT` 位。位格从左到右按 bit 31 到 bit 0 排列，便于按每 4 bit 合并成一个十六进制符号。

完成全部 64 轮后，最终工单会展示最终的 `A`、`B`、`C`、`D` 寄存器，并预留空间让学习者按字节反转每个 32 位字，再拼接出最终 128 位 MD5 摘要。

运行时任务状态和验证产物会写入本地的 `current_state.json`、`session_log.json` 和 `final_report.md`；这些文件均被 Git 忽略。
