# MD5-Scribe

MD5-Scribe 是一个本地优先的桌面网页游戏，用来逐步学习和手算 MD5。它把单个消息块的计算拆成 64 轮，每轮 6 道单一题目，共计 384 个进度格。

在线版本：[play.md5.moe](https://play.md5.moe)

## 主要功能

- 在浏览器中运行完整且可追踪的 MD5 算法，不需要后端、数据库或 Python 环境。
- 将消息限制为 55 个 UTF-8 bytes，保证每个练习固定为一个 512-bit 消息块和 64 轮计算。
- 每次只展示一道题，使用可折叠工单矩阵记录全部 `64 × 6` 个步骤。
- 首次验证通过显示绿色；出现过错误显示橙色；未开始显示灰色。
- 为逻辑函数、十六进制加法、循环左移和最终摘要提供不同的交互模板。
- 支持进位标记、十六进制草稿、32 位二进制草稿、移位指针以及自动 4bit 分组。
- 移位草稿支持 `0`、`1` 和上下方向键输入，并在填写后自动移动焦点。
- 只校验最终答案；草稿和指针都是可选辅助，不影响验证结果。
- 提供两行十六进制屏幕键盘，以及常驻的十六进制、二进制参考栏。
- 使用浏览器 `localStorage` 保存多个独立工单，并支持 JSON 导入和导出。
- 已完成工单再次打开最终摘要页时，会自动恢复验证通过的 MD5 结果。
- 字符串、进度、尝试次数和错误记录始终保存在当前设备。

## 游戏流程

每一轮 MD5 计算拆成六道题：

1. `f = F/G/H/I(B, C, D)`
2. `T1 = A + f`
3. `T2 = T1 + M_j`
4. `T3 = T2 + K_i`
5. `ROT = RotateLeft(T3, s)`
6. `B' = ROT + B`

完成全部 384 道题后，需要将 A/B/C/D 分别按小端字节序输出，再拼接得到最终 128-bit MD5 摘要。

## 开发运行

```bash
npm install
npm run dev
```

打开终端中 Vite 给出的本地地址，通常是 `http://localhost:5173`。

构建并预览生产版本：

```bash
npm run build
npm start
```

生产文件生成在 `dist/`。Vite 使用相对基础路径，可以部署到静态托管服务。生产版本还会注册 Service Worker，首次成功加载后可以离线重新打开。

## 测试

```bash
npm test
npm run build
```

测试覆盖 RFC 1321 标准向量、完整 64 轮计算记录、无符号 32 位辅助函数、工作区迁移、多工单存储，以及 JSON 导入导出。

如需测试最后一步和最终摘要页面，可以导入 [`test/fixtures/near-final-workspace.json`](test/fixtures/near-final-workspace.json)。该测试工单使用字符串 `abc`，导入后会停在最后一道计算题：

- 最后一轮答案：`C08226B3`
- 最终摘要：`900150983CD24FB0D6963F7D28E17F72`

导入工作区会替换浏览器中的现有进度。如需保留当前工单，请先执行 JSON 导出。

## 本地数据

工作区保存在浏览器 `localStorage` 的 `md5-scribe:workspace:v3` 键中。JSON 导出使用带版本号的 `md5-scribe-workspace` 格式。旧版单任务数据和早期流程进度会自动迁移。

## Flask 归档版本

最初的 Flask 实现保存在 [`archive/flask-version`](https://github.com/senzi/MD5-Scribe/tree/archive/flask-version) 分支。

## 许可证

[MIT](LICENSE)
