"use client";

import { Children, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes, forwardRef, isValidElement } from "react";
import type { LucideIcon } from "lucide-react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/cn";
import { Menu } from "./Menu";

/*
 * Contrôles de formulaire, registre outil : hauteur fixe de 32 px, angles
 * peu arrondis, libellé compact au-dessus, aide sur une ligne en dessous.
 * Un champ `mono` passe en chasse fixe : noms de dépôts, clés, identifiants,
 * URL, tout ce qui se copie-colle ou se compare caractère par caractère.
 */
const CONTROL_CLASSES =
  "w-full h-8 px-2.5 bg-surface border border-line rounded text-[13px] text-ink placeholder:text-ink-3 " +
  "focus:border-accent focus:ring-1 focus:ring-accent/40 outline-none transition-[border-color,box-shadow] " +
  "disabled:bg-surface-2 disabled:text-ink-3 disabled:cursor-not-allowed";

function Wrapper({
  label,
  hint,
  error,
  required,
  children,
}: {
  label?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="block min-w-0">
      {label && (
        <span className="block text-[12px] font-medium text-ink-2 mb-1 leading-tight">
          {label}
          {required && <span className="text-failure ml-0.5" aria-hidden="true">*</span>}
        </span>
      )}
      {children}
      {hint && !error && <p className="text-[11.5px] text-ink-3 mt-1 leading-snug">{hint}</p>}
      {error && <p className="text-[11.5px] text-failure mt-1 leading-snug">{error}</p>}
    </label>
  );
}

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  hint?: string;
  error?: string;
  icon?: LucideIcon;
  /** Chasse fixe : identifiants, clés, URL, hashes. */
  mono?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, hint, error, required, className, icon: Icon, mono, ...props }, ref) => (
    <Wrapper label={label} hint={hint} error={error} required={required}>
      <div className="relative">
        {Icon && <Icon className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-3 pointer-events-none" />}
        <input
          ref={ref}
          required={required}
          className={cn(
            CONTROL_CLASSES,
            Icon && "pl-8",
            mono && "font-mono text-[12.5px]",
            error && "border-failure focus:border-failure focus:ring-failure/30",
            className
          )}
          {...props}
        />
      </div>
    </Wrapper>
  )
);
Input.displayName = "Input";

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string;
  hint?: string;
  error?: string;
  mono?: boolean;
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(
  ({ label, hint, error, required, className, mono, ...props }, ref) => (
    <Wrapper label={label} hint={hint} error={error} required={required}>
      <textarea
        ref={ref}
        required={required}
        className={cn(
          CONTROL_CLASSES,
          "h-auto min-h-20 py-1.5 resize-y leading-snug",
          mono && "font-mono text-[12.5px]",
          error && "border-failure focus:border-failure focus:ring-failure/30",
          className
        )}
        {...props}
      />
    </Wrapper>
  )
);
Textarea.displayName = "Textarea";

interface SelectProps {
  label?: string;
  hint?: string;
  error?: string;
  required?: boolean;
  disabled?: boolean;
  name?: string;
  className?: string;
  value: string | number | readonly string[] | undefined;
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  /** Des `<option value>` comme pour un select natif. */
  children: ReactNode;
}

function readOptions(children: ReactNode): { value: string; label: ReactNode }[] {
  const options: { value: string; label: ReactNode }[] = [];
  Children.forEach(children, (child) => {
    if (!isValidElement<{ value?: string | number; children?: ReactNode }>(child)) return;
    options.push({ value: String(child.props.value ?? ""), label: child.props.children });
  });
  return options;
}

/*
 * Même signature qu'un `<select>` (value, onChange(e.target.value), enfants
 * `<option>`), mais rendu par notre Menu : la liste native ne suit ni le
 * thème sombre ni la densité du reste, et diffère d'un OS à l'autre.
 */
export function Select({ label, hint, error, required, disabled, name, className, value, onChange, children }: SelectProps) {
  const options = readOptions(children);
  const current = String(value ?? "");
  const selected = options.find((o) => o.value === current) ?? options[0];
  const pick = (next: string) => {
    if (next === current) return;
    onChange({ target: { value: next, name } } as unknown as React.ChangeEvent<HTMLSelectElement>);
  };

  return (
    <Wrapper label={label} hint={hint} error={error} required={required}>
      <Menu
        fullWidth
        trigger={({ onClick, isOpen }) => (
          <button
            type="button"
            onClick={onClick}
            disabled={disabled}
            aria-haspopup="listbox"
            aria-expanded={isOpen}
            className={cn(CONTROL_CLASSES, "flex items-center gap-2 text-left cursor-pointer", isOpen && "border-accent", className)}
          >
            <span className="flex-1 truncate">{selected?.label}</span>
            <ChevronDown className={cn("w-3.5 h-3.5 text-ink-3 flex-shrink-0 transition-transform", isOpen && "rotate-180")} aria-hidden="true" />
          </button>
        )}
      >
        <ul role="listbox" className="max-h-64 overflow-y-auto">
          {options.map((o) => {
            const isSelected = o.value === current;
            return (
              <li key={o.value} role="option" aria-selected={isSelected}>
                <button
                  type="button"
                  onClick={() => pick(o.value)}
                  className={cn(
                    "w-full flex items-center gap-2.5 h-8 pl-3 pr-3.5 text-[13px] text-left transition-colors",
                    isSelected ? "bg-accent-soft text-ink" : "text-ink-2 hover:bg-surface-2 hover:text-ink"
                  )}
                >
                  <Check className={cn("w-3.5 h-3.5 flex-shrink-0", isSelected ? "text-accent" : "invisible")} aria-hidden="true" />
                  <span className="truncate">{o.label}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </Menu>
    </Wrapper>
  );
}
