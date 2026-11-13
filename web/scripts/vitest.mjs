// Runs vitest (same arguments) from its path with an uppercase drive letter.
// vitest 5 on Windows loads a second copy of itself when it is started through a lowercase
// drive path (VS Code opens folders as c:\..., and npm builds the bin path from that), and
// every test file then fails with "Vitest failed to find the current suite".
// Elsewhere this is the same as running `vitest`.
import path from 'node:path'
import { pathToFileURL } from 'node:url'

const bin = path
  .resolve(import.meta.dirname, '../node_modules/vitest/vitest.mjs')
  .replace(/^[a-z]:/, (drive) => drive.toUpperCase())

await import(pathToFileURL(bin).href)
