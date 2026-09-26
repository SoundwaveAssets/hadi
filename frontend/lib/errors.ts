/** Extrait le message d'erreur `detail` renvoyé par l'API FastAPI, avec repli sur un message générique. */
export function extractError(err: unknown, fallback: string): string {
  if (typeof err === "object" && err !== null && "response" in err) {
    const detail = (err as { response?: { data?: { detail?: unknown } } }).response?.data?.detail;
    if (typeof detail === "string" && detail) return detail;
    // 422 : FastAPI renvoie une liste {loc, msg} par champ invalide.
    if (Array.isArray(detail) && detail.length > 0) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) => {
          const field = Array.isArray(d.loc) ? d.loc.filter((x) => x !== "body").join(".") : "";
          return field ? `${field}: ${d.msg ?? ""}` : d.msg ?? "";
        })
        .join(" · ");
    }
  }
  return fallback;
}
