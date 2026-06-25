// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Muhammad Mishbakhuz Zuhail
import { Component, type ErrorInfo, type ReactNode } from "react"

/** App-level error boundary: a single render throw (a malformed review payload, an unexpected
 *  undefined in a .map, …) would otherwise unmount the whole tree to a blank page. Catch it and
 *  show a recoverable card with the error text instead. */
export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // eslint-disable-next-line no-console
    console.error("transdoc UI crashed:", error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="mx-auto mt-16 max-w-lg rounded-lg border border-destructive/40 bg-card p-6">
        <h2 className="mb-2 text-lg font-semibold text-destructive">Something broke</h2>
        <p className="mb-3 text-sm text-muted-foreground">
          The interface hit an unexpected error. Your files are unaffected — reload to continue.
        </p>
        <pre className="mb-4 max-h-40 overflow-auto rounded bg-muted p-2 text-xs text-muted-foreground">
          {this.state.error.message}
        </pre>
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90"
        >
          Reload
        </button>
      </div>
    )
  }
}
