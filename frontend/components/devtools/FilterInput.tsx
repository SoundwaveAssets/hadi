"use client";

import { Search, X } from "lucide-react";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/cn";

interface FilterInputProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
}

export function FilterInput({ value, onChange, placeholder, className }: FilterInputProps) {
  const t = useT();
  const label = placeholder ?? t("common.filter");
  return (
    <div className={cn("relative", className)}>
      <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none" aria-hidden="true" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={label}
        aria-label={label}
        className="h-8 w-full pl-8 pr-7 bg-surface border border-line rounded text-[13px] text-ink placeholder:text-ink-3 focus:border-accent focus:ring-1 focus:ring-accent/40 outline-none [&::-webkit-search-cancel-button]:hidden"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange("")}
          className="absolute right-1.5 top-1/2 -translate-y-1/2 p-0.5 rounded text-ink-3 hover:text-ink"
          aria-label={t("common.clear")}
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
