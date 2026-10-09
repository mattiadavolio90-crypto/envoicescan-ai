import * as React from "react"

import { cn } from "@/lib/utils"

type UnderlineTab<T extends string> = {
  value: T
  label: React.ReactNode
  title?: string
}

type UnderlineTabsProps<T extends string> = {
  value: T
  onChange: (value: T) => void
  tabs: UnderlineTab<T>[]
  className?: string
}

function UnderlineTabs<T extends string>({ value, onChange, tabs, className }: UnderlineTabsProps<T>) {
  return (
    <div data-slot="underline-tabs" className={cn("flex gap-1 border-b border-border", className)}>
      {tabs.map((t) => (
        <button
          key={t.value}
          type="button"
          title={t.title}
          aria-current={t.value === value ? "page" : undefined}
          onClick={() => onChange(t.value)}
          className={cn(
            "-mb-px inline-flex items-center gap-1.5 border-b-2 px-4 py-2 text-sm font-medium transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50 [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-3.5",
            t.value === value
              ? "border-primary text-foreground"
              : "border-transparent text-muted-foreground hover:text-foreground",
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}

export { UnderlineTabs }
export type { UnderlineTab }
