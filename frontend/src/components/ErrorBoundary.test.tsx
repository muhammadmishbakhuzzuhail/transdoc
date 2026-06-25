// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { ErrorBoundary } from "./ErrorBoundary"

function Boom(): never {
  throw new Error("kaboom")
}

describe("ErrorBoundary", () => {
  it("renders its children when nothing throws", () => {
    render(
      <ErrorBoundary>
        <div>healthy child</div>
      </ErrorBoundary>,
    )
    expect(screen.getByText("healthy child")).toBeInTheDocument()
  })

  it("shows a recoverable fallback (not a blank page) on a render throw", () => {
    // React logs the caught error to console.error — silence it for a clean test run
    vi.spyOn(console, "error").mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <Boom />
      </ErrorBoundary>,
    )
    expect(screen.getByText("Something broke")).toBeInTheDocument()
    expect(screen.getByText("kaboom")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /reload/i })).toBeInTheDocument()
  })
})
