# MD5-Scribe

MD5-Scribe is a local-first learning and verification tool for manual MD5 computation. The algorithm, progress, and error log all run in the browser, with no Python runtime, database, or backend service.

## Features

- Implements instrumented MD5 entirely in the browser.
- Limits input to 55 UTF-8 bytes so each exercise remains one block and 64 rounds.
- Provides a round console, printable worksheet, and validation of five intermediate values.
- Stores multiple independent challenges in `localStorage`, with task creation, switching, and deletion.
- Verifies final A/B/C/D little-endian byte ordering and digest concatenation.
- Builds a local error analysis, timeline, and audit log with Markdown download.
- Does not upload messages or progress while the app is running.

## Development

```bash
npm install
npm run dev
```

Open the Vite URL printed in the terminal, normally `http://localhost:5173`.

Do not serve the repository-root `index.html` with a plain static server; it is the Vite development entry. To check the production build, run:

```bash
npm run build
npm start
```

## Test and Build

```bash
npm test
npm run build
```

Production assets are emitted to `dist/`. The relative Vite base allows deployment on any static host. The production build registers a service worker so the app can reopen offline after its first successful load.

## Local Data

The task workspace is stored under `md5-scribe:workspace:v3` in browser `localStorage`. Legacy single-task data is migrated into the first challenge automatically. Markdown reports are generated as browser downloads and are never uploaded.

## Worksheet Flow

Each round verifies five atomic results:

1. `T1 = A + f`
2. `T2 = T1 + M_j`
3. `T3 = T2 + K_i`
4. `ROT = RotateLeft(T3, s)`
5. `B_new = ROT + B`

Worksheet buttons use the native print dialog, which can print directly or save as PDF. The first round includes a hexadecimal-to-binary reference table.
