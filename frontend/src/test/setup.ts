// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import "@testing-library/jest-dom/vitest"
import { cleanup } from "@testing-library/react"
import { afterEach } from "vitest"

// jsdom in this setup doesn't expose a working Storage — provide a minimal in-memory localStorage
// so the theme/locale persistence paths run.
if (typeof globalThis.localStorage === "undefined" ||
    typeof globalThis.localStorage.getItem !== "function") {
  const store = new Map<string, string>()
  globalThis.localStorage = {
    getItem: (k) => (store.has(k) ? store.get(k)! : null),
    setItem: (k, v) => { store.set(k, String(v)) },
    removeItem: (k) => { store.delete(k) },
    clear: () => { store.clear() },
    key: (i) => [...store.keys()][i] ?? null,
    get length() { return store.size },
  } as Storage
}

// Unmount React trees + reset persisted state between tests so they don't leak.
afterEach(() => {
  cleanup()
  localStorage.clear()
})
