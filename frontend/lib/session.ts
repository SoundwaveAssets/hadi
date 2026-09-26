"use client";

import { useEffect, useRef } from "react";
import { api, REMEMBERED_STORAGE_KEY } from "@/lib/api";

interface SessionPolicy {
  idle_timeout_minutes: number;
  session_minutes: number;
  sudo_minutes: number;
  remember_me_days: number;
}

/** Session ouverte volontairement pour plusieurs jours : pas de verrouillage. */
function sessionGardeeOuverte(): boolean {
  try {
    return window.localStorage.getItem(REMEMBERED_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

/** Ce qui compte comme « quelqu'un est là » : une action délibérée, pas un simple rendu. */
const ACTIVITY_EVENTS = ["pointerdown", "keydown", "wheel", "touchstart"] as const;
const CHECK_INTERVAL_MS = 30_000;

/**
 * Verrouillage par inactivité, et prolongation tant que la personne travaille.
 *
 * Le scénario visé est banal : un administrateur laisse son tableau de bord
 * ouvert et s'absente. Sa session donnait accès à tout pendant huit heures.
 * Désormais la session est courte, prolongée uniquement pendant qu'on s'en
 * sert, et l'écran se verrouille après un délai d'inactivité fixé par
 * l'instance (ORCHESTRATOR_IDLE_TIMEOUT_MINUTES, 0 pour désactiver).
 */
export function useIdleLock(onExpire: () => void) {
  // Refs initialisées à zéro puis posées dans l'effet : lire l'horloge ou
  // écrire une ref pendant le rendu n'est pas permis (règles du compilateur React).
  const lastActivity = useRef(0);
  const lastRefresh = useRef(0);
  const expire = useRef(onExpire);

  useEffect(() => {
    expire.current = onExpire;
  }, [onExpire]);

  useEffect(() => {
    let cancelled = false;
    lastActivity.current = Date.now();
    lastRefresh.current = Date.now();
    const touch = () => {
      lastActivity.current = Date.now();
    };
    for (const event of ACTIVITY_EVENTS) window.addEventListener(event, touch, { passive: true });

    let timer: ReturnType<typeof setInterval> | undefined;

    api
      .get<SessionPolicy>("/api/auth/session-policy")
      .then(({ data }) => {
        if (cancelled) return;
        const idleMs = sessionGardeeOuverte() ? 0 : data.idle_timeout_minutes * 60_000;
        // On prolonge à mi-vie de la session : jamais au dernier moment, pour
        // qu'une requête lente ou un onglet en arrière-plan ne fasse pas
        // expirer une session pourtant active.
        const refreshMs = Math.max(60_000, (data.session_minutes * 60_000) / 2);

        timer = setInterval(() => {
          const inactivité = Date.now() - lastActivity.current;
          if (idleMs > 0 && inactivité >= idleMs) {
            expire.current();
            return;
          }
          if (inactivité < refreshMs && Date.now() - lastRefresh.current >= refreshMs) {
            lastRefresh.current = Date.now();
            api.post("/api/auth/refresh").catch(() => undefined);
          }
        }, CHECK_INTERVAL_MS);
      })
      .catch(() => undefined); // instance plus ancienne : pas de verrouillage, pas d'erreur visible

    return () => {
      cancelled = true;
      for (const event of ACTIVITY_EVENTS) window.removeEventListener(event, touch);
      if (timer) clearInterval(timer);
    };
  }, []);
}
