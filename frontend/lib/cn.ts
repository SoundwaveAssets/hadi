/** Concatène des classes conditionnelles sans dépendance externe (clsx non installé). */
export function cn(...classes: Array<string | false | null | undefined>): string {
  return classes.filter(Boolean).join(" ");
}
