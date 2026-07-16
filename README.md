# MD5-Scribe

MD5-Scribe is a local-first desktop web game for learning MD5 by hand. It turns a single-block MD5 calculation into 64 rounds and 6 focused questions per round, for a total of 384 progress cells.

Live site: [play.md5.moe](https://play.md5.moe)

## Highlights

- Runs the complete instrumented MD5 algorithm in the browser—no backend, database, or Python runtime.
- Limits each message to 55 UTF-8 bytes so an exercise always remains one 512-bit block with 64 rounds.
- Shows one question at a time and tracks all `64 × 6` steps in a collapsible worksheet matrix.
- Marks a first-attempt pass green, any question with an incorrect attempt orange, and untouched questions gray.
- Provides dedicated interaction templates for Boolean functions, hexadecimal addition, rotation, and the final digest.
- Supports carry marks, hexadecimal scratch cells, 32-bit binary scratch work, a rotation pointer, and automatic 4-bit grouping.
- Accepts `0`/`1` and arrow-key input in the rotation editor, with automatic focus movement.
- Checks only the final answer; scratch work and pointer marks are optional and never affect validation.
- Includes a two-row hexadecimal screen keyboard and a persistent hexadecimal/binary reference sidebar.
- Stores multiple independent challenges in browser `localStorage` and supports JSON export/import.
- Restores the verified final MD5 value automatically when reopening a completed challenge.
- Keeps messages, progress, attempts, and logs on the current device.

## Game Flow

Each MD5 round is split into six questions:

1. `f = F/G/H/I(B, C, D)`
2. `T1 = A + f`
3. `T2 = T1 + M_j`
4. `T3 = T2 + K_i`
5. `ROT = RotateLeft(T3, s)`
6. `B' = ROT + B`

After all 384 questions are complete, the game asks the player to serialize A/B/C/D in little-endian byte order and concatenate the final 128-bit MD5 digest.

## Development

```bash
npm install
npm run dev
```

Open the Vite URL shown in the terminal, normally `http://localhost:5173`.

Build and preview the production version:

```bash
npm run build
npm start
```

The production assets are emitted to `dist/`. Vite uses a relative base path, so the build can be served by a static host. The production app also registers a service worker for offline reopening after the first successful load.

## Tests

```bash
npm test
npm run build
```

The test suite covers RFC 1321 vectors, the instrumented 64-round calculation, unsigned 32-bit helpers, workspace migration, multiple challenges, and JSON import/export.

For final-screen testing, import [`test/fixtures/near-final-workspace.json`](test/fixtures/near-final-workspace.json). It opens the `abc` challenge at the final calculation question:

- Last round answer: `C08226B3`
- Final digest: `900150983CD24FB0D6963F7D28E17F72`

Importing a workspace replaces the current browser workspace, so export existing progress first if it needs to be preserved.

## Local Data

The workspace is stored under `md5-scribe:workspace:v3` in browser `localStorage`. JSON exports use the versioned `md5-scribe-workspace` format. Legacy single-task data and progress from the earlier workflow are migrated automatically.

## Previous Flask Version

The original Flask implementation is preserved in the [`archive/flask-version`](https://github.com/senzi/MD5-Scribe/tree/archive/flask-version) branch.

## License

[MIT](LICENSE)
