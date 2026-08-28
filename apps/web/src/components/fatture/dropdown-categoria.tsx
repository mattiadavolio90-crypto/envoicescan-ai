"use client";

import { useMemo } from "react";
import { ChevronDown, Loader2 } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuLabel,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { categoriaIcon } from "@/app/(app)/analisi-fatture/periodi";
import { SPESE_GENERALI_SET, CATEGORIA_NON_CLASSIFICATA } from "@/lib/categorie-spesa";


/**
 * Selettore di categoria, condiviso fra il tab Articoli (Analisi Fatture) e la
 * finestra Costi di gruppo (catena): la stessa riga si corregge da entrambe le
 * viste, quindi il menu deve essere lo stesso.
 *
 * Dropdown in portale (base-ui Menu): si apre ancorato alla cella senza scrollare
 * la pagina, quindi la riga NON salta fuori vista come col <select> nativo.
 *
 * "Da Classificare" NON è selezionabile, anche quando compare in `categorie` (la
 * lista da /api/fatture/categorie la include perché serve a FILTRARE): è uno stato
 * che solo l'AI può assegnare (CLAUDE.md §1), e tutti i backend lo rifiutano con 400
 * via normalizza_categoria_richiesta. Offrirlo era un'azione che non poteva riuscire.
 *
 * "📝 NOTE E DICITURE" NON è selezionabile: è ammessa solo su righe con totale_riga
 * == 0 (CLAUDE.md §2); su una riga con importo reale il worker la rifiuta con 422
 * (guardrail in services/routers/riparto.py). Stesso motivo di "Da Classificare":
 * offrirla era un'azione che quasi sempre non poteva riuscire.
 */
export function DropdownCategoria({
  value,
  categorie,
  onSelect,
  saving = false,
  daScegliere = false,
  compact = false,
}: {
  value: string;
  categorie: string[];
  onSelect: (categoria: string) => void;
  saving?: boolean;
  daScegliere?: boolean;
  compact?: boolean;
}) {
  const fbCats = useMemo(
    () =>
      categorie
        .filter(
          (c) =>
            !SPESE_GENERALI_SET.has(c.toUpperCase()) &&
            c !== CATEGORIA_NON_CLASSIFICATA &&
            c !== "📝 NOTE E DICITURE",
        )
        .sort((a, b) => a.localeCompare(b, "it", { sensitivity: "base" })),
    [categorie],
  );
  const sgCats = useMemo(
    () =>
      categorie
        .filter((c) => SPESE_GENERALI_SET.has(c.toUpperCase()))
        .sort((a, b) => a.localeCompare(b, "it", { sensitivity: "base" })),
    [categorie],
  );
  const icon = daScegliere ? "⚠️" : categoriaIcon(value);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        disabled={saving}
        className={`text-xs inline-flex items-center gap-1.5 hover:underline text-left disabled:opacity-60 ${
          daScegliere ? "text-rose-700 hover:text-rose-800" : "hover:text-primary"
        }`}
      >
        <span className={compact ? "text-sm leading-none" : "text-base leading-none"}>{icon}</span>
        <span className="font-medium">
          {daScegliere ? "Scegli categoria" : value || <em className="text-muted-foreground">N/D</em>}
        </span>
        {saving ? (
          <Loader2 className="size-3 animate-spin" />
        ) : (
          <ChevronDown className={`size-3 ${daScegliere ? "text-rose-500" : "text-muted-foreground"}`} />
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="max-h-80 min-w-52">
        {fbCats.length > 0 && (
          <DropdownMenuGroup>
            <DropdownMenuLabel>🥗 Food &amp; Beverage</DropdownMenuLabel>
            {fbCats.map((c) => (
              <DropdownMenuItem
                key={c}
                onClick={() => onSelect(c)}
                className={c === value ? "font-semibold text-primary" : ""}
              >
                <span className="text-base leading-none">{categoriaIcon(c)}</span>
                {c}
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
        )}
        {sgCats.length > 0 && (
          <DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>📊 Spese Generali</DropdownMenuLabel>
            {sgCats.map((c) => (
              <DropdownMenuItem
                key={c}
                onClick={() => onSelect(c)}
                className={c === value ? "font-semibold text-primary" : ""}
              >
                <span className="text-base leading-none">{categoriaIcon(c)}</span>
                {c}
              </DropdownMenuItem>
            ))}
          </DropdownMenuGroup>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
