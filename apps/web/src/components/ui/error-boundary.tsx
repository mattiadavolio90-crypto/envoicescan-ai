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
          <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-6 text-center space-y-1">
            <p className="text-sm font-semibold text-destructive">Errore nel caricamento del componente</p>
            <p className="text-xs text-muted-foreground">Ricarica la pagina o contatta il supporto se il problema persiste.</p>
          </div>
        )
      );
    }
    return this.props.children;
  }
}
