import axios from "axios";

// Origine relative, volontairement vide : le navigateur appelle /api sur sa
// PROPRE origine, et le serveur Next relaie vers l'API (voir next.config.ts).
// Une variable NEXT_PUBLIC_* serait figée dans le bundle à la compilation,
// donc gravée dans l'image : impossible à régler au déploiement.
export const API_BASE_URL = "";

export const TOKEN_STORAGE_KEY = "orchestrator_token";
export const USER_STORAGE_KEY = "orchestrator_user";
/** Session ouverte avec « garder la session ouverte » : pas de verrouillage par inactivité. */
export const REMEMBERED_STORAGE_KEY = "hadi_remembered";
/** Jeton d'installation (assistant), le temps de la session du navigateur. */
export const SETUP_TOKEN_STORAGE_KEY = "hadi_setup_token";

export const api = axios.create({ baseURL: API_BASE_URL });

api.interceptors.request.use((config) => {
  if (typeof window === "undefined") return config;
  const token = window.localStorage.getItem(TOKEN_STORAGE_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  if (config.url?.startsWith("/api/setup")) {
    const setupToken = window.sessionStorage.getItem(SETUP_TOKEN_STORAGE_KEY);
    if (setupToken) config.headers["X-Setup-Token"] = setupToken;
  }
  return config;
});

/** Code renvoyé par l'API quand une action exige de confirmer le mot de passe. */
export const PASSWORD_CONFIRMATION_REQUIRED = "password_confirmation_required";

/**
 * Demande de confirmation, fournie par l'interface (voir components/PasswordConfirmation).
 * Renvoie le mot de passe saisi, ou null si la personne renonce.
 */
type PasswordPrompt = (action: string) => Promise<string | null>;
let askPassword: PasswordPrompt | null = null;
export const setPasswordPrompt = (prompt: PasswordPrompt | null) => {
  askPassword = prompt;
};

const needsPassword = (error: unknown) =>
  axios.isAxiosError(error) &&
  error.response?.status === 401 &&
  (error.response.data as { detail?: { code?: string } })?.detail?.code === PASSWORD_CONFIRMATION_REQUIRED;

api.interceptors.response.use(
  (response) => {
    // Session prolongée : le nouveau jeton remplace l'ancien immédiatement.
    if (typeof window !== "undefined" && response.config.url === "/api/auth/refresh" && response.data?.access_token) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, response.data.access_token);
    }
    return response;
  },
  async (error) => {
    if (typeof window === "undefined") return Promise.reject(error);

    // Action privilégiée : on demande le mot de passe et on rejoue la requête
    // une seule fois. Surtout pas de déconnexion ici — la session est valide,
    // c'est la confirmation qui manquait.
    if (needsPassword(error) && askPassword && error.config && !error.config.headers?.["X-Confirm-Password"]) {
      const password = await askPassword(error.config.url ?? "");
      if (!password) return Promise.reject(error);
      error.config.headers = { ...error.config.headers, "X-Confirm-Password": password };
      return api.request(error.config);
    }

    if (axios.isAxiosError(error) && error.response?.status === 401 && window.location.pathname !== "/login") {
      window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      window.localStorage.removeItem(USER_STORAGE_KEY);
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

/** Télécharge un fichier servi par l'API et déclenche l'enregistrement côté navigateur. */
export async function download(path: string, filename: string, params?: Record<string, unknown>) {
  const response = await api.get(path, { params, responseType: "blob" });
  const url = window.URL.createObjectURL(response.data);
  const link = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}
