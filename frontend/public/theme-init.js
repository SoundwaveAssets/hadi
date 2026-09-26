// Chargé de façon bloquante dans <head> avant le premier rendu : pose
// data-theme sur <html> d'après la préférence enregistrée, pour éviter le
// flash clair -> sombre. Même clé que contexts/ThemeContext.tsx.
(function () {
  try {
    var t = localStorage.getItem("orchestrator_theme");
    if (t === "dark" || t === "light") document.documentElement.setAttribute("data-theme", t);
  } catch {}
})();
