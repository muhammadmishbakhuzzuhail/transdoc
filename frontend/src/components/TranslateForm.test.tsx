// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { fireEvent, render, screen } from "@testing-library/react"
import { act } from "react"
import { describe, expect, it, vi } from "vitest"
import { setLocale } from "@/lib/i18n"
import { TranslateForm } from "./TranslateForm"

describe("TranslateForm drop zone a11y", () => {
  it("exposes the drop zone as a keyboard-operable button", () => {
    act(() => setLocale("en"))
    render(<TranslateForm health={null} busy={false} onSubmit={() => {}} />)

    const zone = screen.getByRole("button", { name: /drop a document/i })
    expect(zone).toHaveAttribute("tabindex", "0")

    // Enter triggers the hidden file input's click (keyboard parity with mouse)
    const input = document.querySelector('input[type="file"]') as HTMLInputElement
    const click = vi.spyOn(input, "click").mockImplementation(() => {})
    fireEvent.keyDown(zone, { key: "Enter" })
    expect(click).toHaveBeenCalled()
  })
})
