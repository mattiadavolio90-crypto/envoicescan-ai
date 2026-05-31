"use client";

import { useState, useRef, useEffect } from "react";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { type SnapshotDate, fmtData } from "@/lib/inventario";

interface Props {
  value: string; // YYYY-MM-DD
  snapshots: SnapshotDate[];
  onChange: (iso: string) => void;
}

const GIORNI = ["Lu", "Ma", "Me", "Gi", "Ve", "Sa", "Do"];
const MESI = [
  "Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
  "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre",
];

function toISO(d: Date) {
  return d.toISOString().split("T")[0];
}

function parseISO(s: string) {
  const [y, m, d] = s.split("-").map(Number);
  return new Date(y, m - 1, d);
}

export function InventarioDatePicker({ value, snapshots, onChange }: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const snapshotSet = new Set(snapshots.map(s => s.data_inventario));
  const selected = parseISO(value);

  const [navYear, setNavYear] = useState(selected.getFullYear());
  const [navMonth, setNavMonth] = useState(selected.getMonth());

  // Sync nav when value changes externally
  useEffect(() => {
    const d = parseISO(value);
    setNavYear(d.getFullYear());
    setNavMonth(d.getMonth());
  }, [value]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  function prevMonth() {
    if (navMonth === 0) { setNavYear(y => y - 1); setNavMonth(11); }
    else setNavMonth(m => m - 1);
  }
  function nextMonth() {
    if (navMonth === 11) { setNavYear(y => y + 1); setNavMonth(0); }
    else setNavMonth(m => m + 1);
  }

  function buildDays() {
    const firstDay = new Date(navYear, navMonth, 1);
    // Mon=0 offset
    const startOffset = (firstDay.getDay() + 6) % 7;
    const daysInMonth = new Date(navYear, navMonth + 1, 0).getDate();
    const cells: (number | null)[] = Array(startOffset).fill(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(d);
    // pad to full weeks
    while (cells.length % 7 !== 0) cells.push(null);
    return cells;
  }

  function selectDay(day: number) {
    const iso = `${navYear}-${String(navMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    onChange(iso);
    setOpen(false);
  }

  const today = toISO(new Date());
  const cells = buildDays();

  return (
    <div ref={ref} className="relative">
      {/* Trigger */}
      <button
        onClick={() => setOpen(v => !v)}
        className="h-10 rounded-md border border-input bg-background px-3 text-sm focus:outline-none focus:ring-2 focus:ring-sky-500 focus:border-sky-500 flex items-center gap-2 min-w-[130px]"
      >
        <span>{fmtData(value)}</span>
        {snapshotSet.has(value) && (
          <span className="size-2 rounded-full bg-sky-400 shrink-0" title="Inventario esistente" />
        )}
      </button>

      {/* Dropdown calendar */}
      {open && (
        <div className="absolute z-50 mt-1 rounded-lg border border-border bg-popover shadow-lg p-3 w-[280px]">
          {/* Header nav */}
          <div className="flex items-center justify-between mb-2">
            <button onClick={prevMonth} className="p-1 rounded hover:bg-accent transition-colors">
              <ChevronLeft className="size-4" />
            </button>
            <span className="text-sm font-semibold">
              {MESI[navMonth]} {navYear}
            </span>
            <button onClick={nextMonth} className="p-1 rounded hover:bg-accent transition-colors">
              <ChevronRight className="size-4" />
            </button>
          </div>

          {/* Day headers */}
          <div className="grid grid-cols-7 mb-1">
            {GIORNI.map(g => (
              <div key={g} className="text-center text-xs font-medium text-muted-foreground py-1">
                {g}
              </div>
            ))}
          </div>

          {/* Day cells */}
          <div className="grid grid-cols-7 gap-y-0.5">
            {cells.map((day, i) => {
              if (!day) return <div key={i} />;
              const iso = `${navYear}-${String(navMonth + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
              const isSelected = iso === value;
              const isToday = iso === today;
              const hasSnapshot = snapshotSet.has(iso);

              return (
                <button
                  key={i}
                  onClick={() => selectDay(day)}
                  className={[
                    "relative flex flex-col items-center justify-center rounded-md text-sm h-9 w-full transition-colors",
                    isSelected
                      ? "bg-sky-500 text-white font-semibold"
                      : isToday
                      ? "border border-sky-400 text-sky-400 hover:bg-accent"
                      : "hover:bg-accent",
                  ].join(" ")}
                >
                  {day}
                  {hasSnapshot && !isSelected && (
                    <span className="absolute bottom-1 left-1/2 -translate-x-1/2 size-1 rounded-full bg-sky-400" />
                  )}
                  {hasSnapshot && isSelected && (
                    <span className="absolute bottom-1 left-1/2 -translate-x-1/2 size-1 rounded-full bg-white/70" />
                  )}
                </button>
              );
            })}
          </div>

          {/* Legend */}
          <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-border">
            <span className="size-2 rounded-full bg-sky-400 shrink-0" />
            <span className="text-xs text-muted-foreground">Inventario esistente</span>
          </div>
        </div>
      )}
    </div>
  );
}
