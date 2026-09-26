"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { KeyRound } from "lucide-react";
import { setPasswordPrompt } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { Modal } from "@/components/ui/Modal";
import { Input } from "@/components/ui/Field";
import { Button } from "@/components/ui/Button";

/**
 * Confirmation du mot de passe avant une action privilégiée.
 *
 * Monté une fois pour tout le tableau de bord : c'est le client HTTP qui la
 * déclenche quand l'API réclame une confirmation, sans que chaque formulaire
 * ait à s'en occuper. Répond au poste laissé ouvert : une session valide ne
 * suffit plus pour créer un jeton de service ou réinitialiser un mot de passe.
 */
export function PasswordConfirmation() {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const resolver = useRef<((value: string | null) => void) | null>(null);

  const close = useCallback((value: string | null) => {
    resolver.current?.(value);
    resolver.current = null;
    setPassword("");
    setOpen(false);
  }, []);

  useEffect(() => {
    setPasswordPrompt(
      () =>
        new Promise<string | null>((resolve) => {
          resolver.current = resolve;
          setOpen(true);
        })
    );
    return () => setPasswordPrompt(null);
  }, []);

  if (!open) return null;

  return (
    <Modal title={t("sudo.title")} onClose={() => close(null)} size="sm">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (password) close(password);
        }}
        className="space-y-3.5"
      >
        <p className="text-[12.5px] text-ink-2">{t("sudo.explain")}</p>
        <Input type="password" label={t("common.password")} icon={KeyRound} value={password} onChange={(e) => setPassword(e.target.value)} autoFocus autoComplete="current-password" />
        <div className="flex gap-2 justify-end">
          <Button type="button" variant="secondary" onClick={() => close(null)}>{t("common.cancel")}</Button>
          <Button type="submit" disabled={!password}>{t("common.confirm")}</Button>
        </div>
      </form>
    </Modal>
  );
}
