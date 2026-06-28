// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { act } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import { setLocale } from "@/lib/i18n"

// Mock the API layer: these tests exercise the SegmentRow autosave/TM/mode logic, not the network.
const postCorrection = vi.fn(async (_b: unknown) => ({ ok: true }))
const getAlternatives = vi.fn(async (_b: unknown) => ["an alternative rendering"])
vi.mock("@/lib/api", () => ({
  getReview: vi.fn(),
  getHealth: vi.fn(async () => ({ styles: ["general", "professional"] })),
  postCorrection: (b: unknown) => postCorrection(b),
  getAlternatives: (b: unknown) => getAlternatives(b),
  getRephrasings: vi.fn(async () => []),
  getSynonyms: vi.fn(async () => []),
  acceptGlossarySuggestion: vi.fn(async () => ({ ok: true })),
  previewUrl: () => "blob:preview",
}))

import { getReview } from "@/lib/api"
import { ReviewView } from "./ReviewView"

const SEG = {
  block_id: "p0-r0",
  page: 0,
  bbox: null,
  source: "Hello world",
  translation: "Halo dunia",
  flags: [],
}

function payload(over: Record<string, unknown> = {}) {
  return {
    src_lang: "en",
    tgt_lang: "id",
    page_sizes: {},
    segments: [SEG],
    glossary_suggestions: [],
    fuzzy_suggestions: [],
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  act(() => setLocale("en"))
})

describe("ReviewView / SegmentRow", () => {
  it("autosaves the latest edited text on blur", async () => {
    vi.mocked(getReview).mockResolvedValue(payload())
    render(<ReviewView jid="j1" />)

    const ta = await screen.findByDisplayValue("Halo dunia")
    fireEvent.change(ta, { target: { value: "Halo dunia baru" } })
    fireEvent.blur(ta)

    await waitFor(() => expect(postCorrection).toHaveBeenCalledTimes(1))
    expect(postCorrection).toHaveBeenCalledWith(
      expect.objectContaining({ source: "Hello world", fix: "Halo dunia baru" }),
    )
  })

  it("does NOT save when the text is unchanged on blur (no-op guard)", async () => {
    vi.mocked(getReview).mockResolvedValue(payload())
    render(<ReviewView jid="j1" />)

    const ta = await screen.findByDisplayValue("Halo dunia")
    fireEvent.blur(ta)

    await Promise.resolve()
    expect(postCorrection).not.toHaveBeenCalled()
  })

  it("fills and saves a TM match in one click", async () => {
    vi.mocked(getReview).mockResolvedValue(payload({
      fuzzy_suggestions: [{
        source: "Hello world",
        match_source: "Hello world",
        match_translation: "Halo, dunia!",
        score: 0.95,
      }],
    }))
    render(<ReviewView jid="j1" />)

    const tm = await screen.findByRole("button", { name: /TM 95%/i })
    fireEvent.click(tm)

    await waitFor(() => expect(postCorrection).toHaveBeenCalledWith(
      expect.objectContaining({ fix: "Halo, dunia!" }),
    ))
    expect(screen.getByDisplayValue("Halo, dunia!")).toBeInTheDocument()
  })

  it("clears on-screen alternatives when the suggestion mode changes (stale guard)", async () => {
    vi.mocked(getReview).mockResolvedValue(payload())
    render(<ReviewView jid="j1" />)
    await screen.findByDisplayValue("Halo dunia")

    fireEvent.click(screen.getByRole("button", { name: /alternatives/i }))
    expect(await screen.findByText("an alternative rendering")).toBeInTheDocument()

    // switching mode invalidates results fetched for the previous mode
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "professional" } })
    await waitFor(() =>
      expect(screen.queryByText("an alternative rendering")).not.toBeInTheDocument())
  })
})
