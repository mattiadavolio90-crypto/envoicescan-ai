"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

type SelectProps = {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  disabled?: boolean;
  children?: React.ReactNode;
};

type SelectContextValue = {
  value: string;
  onValueChange: (v: string) => void;
};

const SelectContext = React.createContext<SelectContextValue>({
  value: "",
  onValueChange: () => {},
});

function Select({ value, defaultValue, onValueChange, disabled, children }: SelectProps) {
  const [internal, setInternal] = React.useState(defaultValue ?? "");
  const controlled = value !== undefined;
  const current = controlled ? (value ?? "") : internal;

  function handleChange(v: string) {
    if (!controlled) setInternal(v);
    onValueChange?.(v);
  }

  return (
    <SelectContext.Provider value={{ value: current, onValueChange: handleChange }}>
      <div data-disabled={disabled} className="relative">
        {children}
      </div>
    </SelectContext.Provider>
  );
}

type SelectTriggerProps = React.HTMLAttributes<HTMLButtonElement> & {
  className?: string;
};

function SelectTrigger({ className, children, ...props }: SelectTriggerProps) {
  return (
    <button
      type="button"
      className={cn(
        "flex w-full items-center justify-between gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm shadow-xs ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    >
      {children}
    </button>
  );
}

function SelectValue({ placeholder }: { placeholder?: string }) {
  const { value } = React.useContext(SelectContext);
  return <span className="truncate">{value || placeholder}</span>;
}

type SelectContentProps = {
  children?: React.ReactNode;
  className?: string;
};

// Shim no-op: l'API shadcn (SelectContent/SelectItem) e' mantenuta per
// compatibilita', ma il rendering reale avviene nel NativeSelect wrapper sotto.
// I componenti accettano le stesse props (SelectContentProps/SelectItemProps)
// ma non le usano qui.
function SelectContent(_props: SelectContentProps) {  // eslint-disable-line @typescript-eslint/no-unused-vars
  return null;
}

type SelectItemProps = {
  value: string;
  children?: React.ReactNode;
  className?: string;
};

function SelectItem(_props: SelectItemProps) {  // eslint-disable-line @typescript-eslint/no-unused-vars
  return null;
}

// ─── Native implementation ───────────────────────────────────────────────────
// The abstraction above is kept for API compatibility.
// The actual rendered element is a styled <select>.

type NativeSelectProps = {
  value?: string;
  defaultValue?: string;
  onValueChange?: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  className?: string;
  children?: React.ReactNode;
};

function NativeSelect({
  value,
  defaultValue,
  onValueChange,
  disabled,
  placeholder,
  className,
  children,
}: NativeSelectProps) {
  return (
    <select
      value={value ?? defaultValue ?? ""}
      disabled={disabled}
      onChange={(e) => onValueChange?.(e.target.value)}
      className={cn(
        "flex w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm shadow-xs ring-offset-background focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
    >
      {placeholder && (
        <option value="" disabled>
          {placeholder}
        </option>
      )}
      {children}
    </select>
  );
}

export {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
  NativeSelect,
};
