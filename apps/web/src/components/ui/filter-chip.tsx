import * as React from "react"

import { cn } from "@/lib/utils"

type FilterChipProps = Omit<React.ComponentProps<"button">, "type"> & {
  active?: boolean
  // Nessun dato per questo filtro: tratteggiato e non cliccabile.
  empty?: boolean
}

function FilterChip({ active = false, empty = false, className, disabled, children, ...props }: FilterChipProps) {
  return (
    <button
      type="button"
      data-slot="filter-chip"
      aria-pressed={active}
      disabled={disabled || empty}
      className={cn(
        "inline-flex h-7 shrink-0 items-center justify-center gap-1.5 rounded-full border px-3 text-xs font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-default [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-3.5",
        empty
          ? "border-dashed border-border text-muted-foreground"
          : active
            ? "border-primary bg-primary text-primary-foreground"
            : "border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground disabled:opacity-60",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  )
}

export { FilterChip }
