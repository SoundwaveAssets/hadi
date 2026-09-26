"use client";

import { Check, ChevronDown, GitBranch } from "lucide-react";
import { useRepositories } from "@/lib/api";
import { Menu } from "@/components/ui/Menu";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/cn";

const ALL = "";

/**
 * Sélecteur « Tous les dépôts / un dépôt précis », partagé par Vue d'ensemble,
 * Exécutions et Décisions. Alimenté par /api/decisions/repositories : la
 * liste des dépôts ENREGISTRÉS, pour qu'un dépôt fraîchement créé apparaisse
 * immédiatement.
 *
 * Menu maison plutôt qu'un `<select>` natif : la liste déroulante d'un select
 * est dessinée par le système, pas par la page, surlignage bleu vif, liseré
 * de focus arrondi, police et fond hors charte, et rien de tout ça n'est
 * stylable. Sur une interface sombre, l'écart saute aux yeux.
 */
export function RepositorySelector({
  value,
  onChange,
}: {
  value: string;
  onChange: (repository: string) => void;
}) {
  const t = useT();
  // Le hook partagé, pas une requête refaite ici : deux appels au même
  // endpoint avec deux clés de cache différentes, c'est deux vérités.
  const { data: repositories = [] } = useRepositories();

  if (repositories.length === 0) return null;

  const options = [ALL, ...repositories.map((r) => r.repository)];
  const label = value === ALL ? t("common.all") : value;

  return (
    <Menu
      trigger={({ onClick, isOpen }) => (
        <button
          type="button"
          onClick={onClick}
          aria-haspopup="listbox"
          aria-expanded={isOpen}
          className={cn(
            "inline-flex items-center gap-2 h-8 pl-2.5 pr-2 rounded border text-[13px] transition-colors",
            "bg-surface text-ink-2 border-line hover:border-line-2 hover:text-ink",
            isOpen && "border-accent text-ink"
          )}
        >
          <GitBranch className="w-3.5 h-3.5 text-ink-3 flex-shrink-0" aria-hidden="true" />
          <span className={cn("max-w-[18ch] truncate", value !== ALL && "font-mono")}>{label}</span>
          <ChevronDown
            className={cn("w-3.5 h-3.5 text-ink-3 flex-shrink-0 transition-transform", isOpen && "rotate-180")}
            aria-hidden="true"
          />
        </button>
      )}
    >
      <ul role="listbox" aria-label={t("common.repository")} className="max-h-72 overflow-y-auto">
        {options.map((option) => {
          const isSelected = option === value;
          const isAll = option === ALL;
          return (
            <li key={option || "__all"} role="option" aria-selected={isSelected}>
              <button
                type="button"
                onClick={() => onChange(option)}
                className={cn(
                  "w-full flex items-center gap-2.5 h-8 pl-3 pr-3.5 text-[13px] text-left transition-colors",
                  isSelected ? "bg-accent-soft text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                  isAll && "border-b border-line"
                )}
              >
                <Check
                  className={cn("w-3.5 h-3.5 flex-shrink-0", isSelected ? "text-accent" : "invisible")}
                  aria-hidden="true"
                />
                <span className={cn("truncate", !isAll && "font-mono")}>{isAll ? t("common.all") : option}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </Menu>
  );
}
