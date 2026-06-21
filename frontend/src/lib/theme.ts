// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { useEffect, useState } from "react"

type Theme = "light" | "dark"

function initial(): Theme {
  const saved = localStorage.getItem("transdoc-theme")
  if (saved === "light" || saved === "dark") return saved
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"
}

/** Light/dark theme: applies `.dark` on <html>, persists the choice, defaults to the OS setting. */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(initial)
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark")
    localStorage.setItem("transdoc-theme", theme)
  }, [theme])
  return [theme, () => setTheme((t) => (t === "dark" ? "light" : "dark"))]
}
