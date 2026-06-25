// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { act, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { setLocale } from "@/lib/i18n"
import { Hero } from "./Hero"

describe("Hero i18n", () => {
  it("renders English then switches to Indonesian via the locale store", () => {
    act(() => setLocale("en"))
    render(<Hero />)
    expect(screen.getByText(/keep the layout/i)).toBeInTheDocument()

    // useSyncExternalStore makes the live component track the locale change
    act(() => setLocale("id"))
    expect(screen.getByText(/tata letak tetap utuh/i)).toBeInTheDocument()
  })
})
