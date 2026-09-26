"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import axios from "axios";
import { Loader2 } from "lucide-react";
import { api, TOKEN_STORAGE_KEY } from "@/lib/api";
import { useT } from "@/lib/i18n";

export default function Home() {
  const t = useT();
  const router = useRouter();

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const response = await api.get("/api/health");

        if (response.data.setup_complete) {
          // L'installation est terminée : direction le login si aucune session
          // active n'est trouvée, sinon le dashboard.
          const hasToken = Boolean(window.localStorage.getItem(TOKEN_STORAGE_KEY));
          router.push(hasToken ? "/dashboard" : "/login");
        } else {
          router.push("/setup");
        }
      } catch (error) {
        if (axios.isAxiosError(error) && error.response?.status === 503) {
          router.push("/setup");
        } else {
          console.error("L'API backend ne semble pas être en cours d'exécution.", error);
        }
      }
    };

    checkStatus();
  }, [router]);

  return (
    <main className="min-h-screen bg-page flex flex-col items-center justify-center">
      <Loader2 className="w-10 h-10 text-accent animate-spin mb-4" />
      <p className="text-ink-3 font-medium animate-pulse">{t("setup.checking")}</p>
    </main>
  );
}
