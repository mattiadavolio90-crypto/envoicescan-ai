import * as React from "react"

import { cn } from "@/lib/utils"

type SegmentedOption<T extends string> = {
  value: T
  label: React.ReactNode
  title?: string
}

type SegmentedControlProps<T extends string> = {
  value: T
  onChange: (value: T) => void
  options: SegmentedOption<T>[]
  className?: string
  "aria-label"?: string
}

function SegmentedControl<T extends string>({
  value,
  onChange,
  options,
  className,
  "aria-label": ariaLabel,
}: SegmentedControlProps<T>) {
  return (
    <div
      role="group"
      aria-label={ariaLabel}
      data-slot="segmented-control"
      className={cn("inline-flex h-7 items-stretch rounded-full border border-border bg-background p-0.5", className)}
    >
      {options.map((o) => {
        const attivo = o.value === value
        return (
          <button
            key={o.value}
            type="button"
            title={o.title}
            aria-pressed={attivo}
            onClick={() => onChange(o.value)}
            className={cn(
              "inline-flex items-center justify-center gap-1 rounded-full px-3 text-xs font-medium whitespace-nowrap transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-3",
              attivo ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:bg-muted hover:text-foreground",
            )}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

export { SegmentedControl }
export type { SegmentedOption }
