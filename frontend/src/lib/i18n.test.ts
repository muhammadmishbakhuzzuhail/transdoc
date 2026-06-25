// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { act, renderHook } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { useI18n } from "./i18n"

describe("i18n", () => {
  it("translates per locale and falls back to the key", () => {
    const { result } = renderHook(() => useI18n())

    act(() => result.current.setLocale("en"))
    expect(result.current.t("translate")).toBe("Translate")

    act(() => result.current.setLocale("id"))
    expect(result.current.t("translate")).toBe("Terjemahkan")

    // an un-migrated key is never blank — it falls back to itself
    expect(result.current.t("definitely_missing_key")).toBe("definitely_missing_key")
  })

  it("persists the locale choice", () => {
    const { result } = renderHook(() => useI18n())
    act(() => result.current.setLocale("id"))
    expect(localStorage.getItem("transdoc-locale")).toBe("id")
  })
})
