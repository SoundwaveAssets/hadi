"use client";

import { ButtonHTMLAttributes, forwardRef } from "react";
import { Loader2, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "danger-ghost" | "dark";
type Size = "sm" | "md";

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-accent-solid text-white border-transparent hover:bg-accent-solid-hover disabled:hover:bg-accent-solid",
  secondary: "bg-surface text-ink-2 border-line-2 hover:bg-surface-2 hover:text-ink disabled:hover:bg-surface",
  ghost: "text-ink-2 border-transparent hover:bg-surface-2 hover:text-ink disabled:hover:bg-transparent",
  danger: "bg-critical-solid text-white border-transparent hover:opacity-90 disabled:hover:opacity-100",
  "danger-ghost": "text-failure border-transparent hover:bg-failure-soft disabled:hover:bg-transparent",
  dark: "bg-ink text-page border-transparent hover:opacity-90 disabled:hover:opacity-100",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "h-7 text-[12px] px-2.5 gap-1.5 rounded",
  md: "h-8 text-[13px] px-3 gap-2 rounded",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  icon?: LucideIcon;
  isLoading?: boolean;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", icon: Icon, isLoading, disabled, className, children, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || isLoading}
        className={cn(
          "inline-flex items-center justify-center font-medium border transition-colors whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed",
          VARIANT_CLASSES[variant],
          SIZE_CLASSES[size],
          className
        )}
        {...props}
      >
        {isLoading ? (
          <Loader2 className={cn("animate-spin", size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4")} />
        ) : (
          Icon && <Icon className={size === "sm" ? "w-3.5 h-3.5" : "w-4 h-4"} />
        )}
        {children}
      </button>
    );
  }
);
Button.displayName = "Button";
