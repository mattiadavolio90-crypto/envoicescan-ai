"use client";

import { Component, type ReactNode } from "react";

type Props = { children: ReactNode; fallback?: ReactNode };
type State = { hasError: boolean };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        this.props.fallback ?? (
          <div className="rounded-lg border border-rose-500/40 bg-rose-500/5 p-6 text-center space-y-1">
            <p className="text-sm font-semibold text-rose-700 dark:text-rose-400">Errore nel caricamento del componente</p>
            <p className="text-xs text-muted-foreground">Ricarica la pagina o contatta il supporto se il problema persiste.</p>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
