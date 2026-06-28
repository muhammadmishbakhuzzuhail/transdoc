// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { render, screen } from "@testing-library/react"
import { act } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { setLocale } from "@/lib/i18n"

const getBatch = vi.fn()
vi.mock("@/lib/api", () => ({
  getBatch: (id: string) => getBatch(id),
  downloadUrl: (id: string) => `/api/download/${id}`,
}))

import { BatchView } from "./BatchView"

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
  act(() => setLocale("en"))
})
afterEach(() => {
  vi.runOnlyPendingTimers()
  vi.useRealTimers()
})

describe("BatchView", () => {
  it("renders a row per job and a download once a job is done", async () => {
    getBatch.mockResolvedValue({
      batch_id: "b1",
      jobs: [
        { job_id: "a", filename: "one.pdf", status: "done", progress: 1 },
        { job_id: "b", filename: "two.pdf", status: "running", progress: 0.5 },
      ],
    })
    render(<BatchView bid="b1" />)
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })   // flush the immediate first tick

    expect(screen.getByText("one.pdf")).toBeInTheDocument()
    expect(screen.getByText("two.pdf")).toBeInTheDocument()
    const dl = screen.getAllByRole("link", { name: /download translation/i })
    expect(dl).toHaveLength(1)
    expect(dl[0]).toHaveAttribute("href", "/api/download/a")
  })

  it("keeps polling on an empty job list, then stops once all jobs are terminal", async () => {
    // first tick: empty list ([].every === true must NOT stop the interval)
    getBatch.mockResolvedValueOnce({ batch_id: "b1", jobs: [] })
    // later ticks: a single done job -> interval should clear
    getBatch.mockResolvedValue({
      batch_id: "b1",
      jobs: [{ job_id: "a", filename: "one.pdf", status: "done", progress: 1 }],
    })
    const clearSpy = vi.spyOn(globalThis, "clearInterval")

    render(<BatchView bid="b1" />)
    // flush the initial tick (empty) — must not have cleared yet
    await act(async () => { await vi.advanceTimersByTimeAsync(0) })
    expect(clearSpy).not.toHaveBeenCalled()

    // next interval fire resolves to a terminal job -> polling stops
    await act(async () => { await vi.advanceTimersByTimeAsync(1000) })
    expect(screen.getByText("one.pdf")).toBeInTheDocument()
    expect(clearSpy).toHaveBeenCalled()
  })
})
