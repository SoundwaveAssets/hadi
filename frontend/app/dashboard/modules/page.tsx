"use client";

import { toast } from "sonner";
import { Blocks, Lock, ShieldCheck } from "lucide-react";
import { useToggleModule } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { extractError } from "@/lib/errors";
import { useModules, type ModuleInfo } from "@/contexts/ModulesContext";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card } from "@/components/ui/Card";
import { CenteredSpinner } from "@/components/ui/Spinner";
import { Switch } from "@/components/ui/Switch";

export default function ModulesPage() {
  const t = useT();
  const { modules, isLoading } = useModules();
  const toggle = useToggleModule();
  const categories = Array.from(new Set(modules.map((m) => m.category)));

  const onToggle = (module: ModuleInfo) =>
    toggle.mutate(module.key, { onError: (err) => toast.error(extractError(err, t("modules.toggleError"))) });

  return (
    <div className="space-y-4 pb-6">
      <PageHeader title={t("page.modules")} />
      {isLoading ? (
        <CenteredSpinner className="py-12" />
      ) : (
        categories.map((category) => (
          <div key={category} className="space-y-3">
            <h3 className="text-xs font-semibold text-ink-3 uppercase tracking-wide px-1">{category}</h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {modules
                .filter((m) => m.category === category)
                .map((module) => (
                  <ModuleCard
                    key={module.key}
                    module={module}
                    isToggling={toggle.isPending && toggle.variables === module.key}
                    onToggle={() => onToggle(module)}
                  />
                ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

function ModuleCard({ module, isToggling, onToggle }: { module: ModuleInfo; isToggling: boolean; onToggle: () => void }) {
  const t = useT();
  return (
    <Card className="p-5 flex items-start justify-between gap-4">
      <div className="flex items-start gap-3 min-w-0">
        <div className={`p-2 rounded flex-shrink-0 ${module.is_active ? "bg-accent-soft text-accent" : "bg-surface-2 text-ink-3"}`}>
          <Blocks className="w-4 h-4" />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-1.5 flex-wrap">
            <h4 className="text-sm font-semibold text-ink">{module.name}</h4>
            {module.is_core && (
              <span className="inline-flex items-center gap-1 text-[10px] font-medium text-ink-3 bg-surface-2 px-1.5 py-0.5 rounded">
                <Lock className="w-2.5 h-2.5" /> {t("modules.core")}
              </span>
            )}
          </div>
          <p className="text-xs text-ink-3 mt-1">{module.description}</p>
        </div>
      </div>

      {module.is_core ? (
        <span className="flex items-center gap-1 text-xs font-medium text-good flex-shrink-0" title={t("modules.alwaysOn")}>
          <ShieldCheck className="w-4 h-4" />
        </span>
      ) : (
        <Switch
          checked={module.is_active}
          onChange={onToggle}
          disabled={isToggling}
          label={`${module.is_active ? t("common.disable") : t("common.enable")} ${module.name}`}
        />
      )}
    </Card>
  );
}
