"use client";

import { useMemo, useState } from "react";
import { Controller, useForm, useWatch, type Control } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { z } from "zod";
import { toast } from "sonner";
import { Download, FileCode2, GitBranch, MoreHorizontal, Pencil, Plus, RefreshCw, Trash2 } from "lucide-react";
import {
  SECURITY_CRITERIA,
  downloadScaffold,
  useCreatePipelineConfig,
  useDeletePipelineConfig,
  useJenkinsCredentials,
  usePipelineConfigs,
  useUpdatePipelineConfig,
  type Forge,
  type PipelineConfig,
  type PipelineConfigInput,
} from "@/lib/api";
import { useT, type MessageKey } from "@/lib/i18n";
import { extractError } from "@/lib/errors";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { Input, Select } from "@/components/ui/Field";
import { IconButton } from "@/components/ui/IconButton";
import { Menu, MenuItem } from "@/components/ui/Menu";
import { Switch } from "@/components/ui/Switch";
import { DataTable, type ColumnDef } from "@/components/ui/DataTable";
import { cn } from "@/lib/cn";

const FORGES: { value: Forge; label: string }[] = [
  { value: "gitea", label: "Gitea" },
  { value: "github", label: "GitHub" },
  { value: "gitlab", label: "GitLab" },
];

export default function PipelineConfigsPage() {
  const t = useT();
  const { data: pipelines = [], isLoading, isError } = usePipelineConfigs();
  const update = useUpdatePipelineConfig();
  const remove = useDeletePipelineConfig();
  const download = useMutation({
    mutationFn: ({ config, kind }: { config: PipelineConfig; kind: "jenkinsfile" | "application-yaml" }) => downloadScaffold(config, kind),
    onError: (err, { kind }) => toast.error(extractError(err, `${t("common.export")} ${kind}`)),
  });
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<PipelineConfig | null>(null);

  const customisations = (p: PipelineConfig): MessageKey[] => {
    const keys: MessageKey[] = [];
    if (p.jenkins_job_name || p.sonarqube_project_key || p.argocd_app_name || p.docker_image_name) keys.push("repos.mappings");
    if (p.anomaly_review_threshold !== null || p.anomaly_block_threshold !== null || p.ai_observation_mode !== null || p.security_criterion !== null) keys.push("repos.thresholds");
    if (p.git_branch || p.manifest_path) keys.push("repos.deploymentSection");
    if (p.auto_create_jenkins_job || p.auto_create_argocd_app || p.auto_create_sonarqube_project) keys.push("repos.provisioning");
    return keys;
  };

  const columns = useMemo<ColumnDef<PipelineConfig, unknown>[]>(
    () => [
      {
        accessorKey: "repository",
        header: t("common.repository"),
        meta: { width: "30%" },
        cell: ({ row: { original: p } }) => (
          <div className="flex items-center gap-2 min-w-0">
            <span className="font-medium text-ink truncate">{p.repository}</span>
            <span className="text-[11px] text-ink-3 whitespace-nowrap">{FORGES.find((f) => f.value === p.vcs_provider)?.label ?? p.vcs_provider}</span>
            {!p.webhook_secret && <Badge tone="failure">{t("repos.secretMissing")}</Badge>}
          </div>
        ),
      },
      {
        id: "configuration",
        header: t("repos.configuration"),
        enableSorting: false,
        meta: { width: "30%" },
        cell: ({ row: { original: p } }) => {
          const custom = customisations(p);
          return <span className="text-ink-3 text-xs">{custom.length === 0 ? t("repos.defaults") : custom.map((k) => t(k)).join(" · ")}</span>;
        },
      },
      {
        accessorKey: "is_active",
        header: t("common.status"),
        meta: { width: "28%" },
        cell: ({ row: { original: p } }) => (
          <div className="flex items-center gap-2.5">
            <Switch
              checked={p.is_active}
              onChange={() => update.mutate({ id: p.id, is_active: !p.is_active }, { onError: (err) => toast.error(extractError(err, t("common.toggleError"))) })}
              label={`${p.is_active ? t("common.disable") : t("common.enable")} ${p.repository}`}
            />
            <span className={cn("text-xs font-medium", p.is_active ? "text-success" : "text-ink-3")}>{p.is_active ? t("common.active") : t("common.disabled")}</span>
            {p.is_active && !p.decision_engine_enabled && <Badge tone="unstable">{t("repos.noEvaluation")}</Badge>}
          </div>
        ),
      },
      {
        id: "actions",
        header: t("common.actions"),
        enableSorting: false,
        meta: { align: "right", width: "12%" },
        cell: ({ row: { original: p } }) => (
          <div className="flex justify-end gap-0.5">
            <IconButton icon={Pencil} label={t("common.edit")} onClick={() => setEditing(p)} />
            <Menu trigger={({ onClick }) => <IconButton icon={MoreHorizontal} label={t("common.more")} onClick={onClick} />}>
              <MenuItem icon={Download} onClick={() => download.mutate({ config: p, kind: "jenkinsfile" })}>{t("repos.downloadJenkinsfile")}</MenuItem>
              <MenuItem icon={FileCode2} onClick={() => download.mutate({ config: p, kind: "application-yaml" })}>{t("repos.downloadManifest")}</MenuItem>
              <div className="border-t border-line mt-1 pt-1">
                <MenuItem
                  icon={Trash2}
                  danger
                  onClick={() => {
                    if (!window.confirm(t("repos.confirmDelete", { name: p.repository }))) return;
                    remove.mutate(p.id, { onError: (err) => toast.error(extractError(err, t("common.deleteError"))) });
                  }}
                >
                  {t("common.delete")}
                </MenuItem>
              </div>
            </Menu>
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps -- les mutations sont stables entre rendus
    [t]
  );

  return (
    <div className="space-y-4">
      <PageHeader title={t("page.repositories")} actions={<Button icon={Plus} onClick={() => setShowForm(true)}>{t("repos.add")}</Button>} />
      {isError ? (
        <EmptyState icon={GitBranch} title={t("pipelines.loadError")} />
      ) : !isLoading && pipelines.length === 0 ? (
        <EmptyState icon={GitBranch} title={t("repos.empty")} description={t("repos.emptyHint")} />
      ) : (
        <DataTable columns={columns} data={pipelines} rowKey={(p) => p.id} isLoading={isLoading} />
      )}
      {showForm && <PipelineFormModal onClose={() => setShowForm(false)} />}
      {editing && <PipelineFormModal existing={editing} onClose={() => setEditing(null)} />}
    </div>
  );
}

function Badge({ tone, children }: { tone: "failure" | "unstable"; children: React.ReactNode }) {
  return (
    <span className={cn("inline-flex items-center h-5 px-2 rounded text-[11px] font-medium whitespace-nowrap", tone === "failure" ? "bg-failure-soft text-failure" : "bg-unstable-soft text-unstable")}>
      {children}
    </span>
  );
}

// --- formulaire ---------------------------------------------------------------

const optionalText = z.string().trim();
const optionalThreshold = z.union([z.number().min(0).max(1), z.nan()]).transform((v) => (Number.isNaN(v) ? null : v));

const schema = z.object({
  repository: z.string().trim().min(1),
  vcs_provider: z.enum(["gitea", "github", "gitlab"]),
  webhook_secret: z.string(),
  jenkins_job_name: optionalText,
  sonarqube_project_key: optionalText,
  argocd_app_name: optionalText,
  docker_image_name: optionalText,
  git_repo_url: optionalText,
  git_branch: optionalText,
  manifest_path: optionalText,
  jenkins_credentials_id: optionalText,
  k8s_namespace: optionalText,
  auto_create_sonarqube_project: z.boolean(),
  auto_create_jenkins_job: z.boolean(),
  auto_create_argocd_app: z.boolean(),
  security_criterion: z.enum(["inherit", "new_code", "quality_gate", "total"]),
  anomaly_review_threshold: optionalThreshold,
  anomaly_block_threshold: optionalThreshold,
  ai_observation_mode: z.enum(["inherit", "true", "false"]),
  decision_engine_enabled: z.boolean(),
});

type FormInput = z.input<typeof schema>;
type FormOutput = z.output<typeof schema>;

function toForm(existing?: PipelineConfig): FormInput {
  return {
    repository: existing?.repository ?? "",
    vcs_provider: existing?.vcs_provider ?? "gitea",
    webhook_secret: "",
    jenkins_job_name: existing?.jenkins_job_name ?? "",
    sonarqube_project_key: existing?.sonarqube_project_key ?? "",
    argocd_app_name: existing?.argocd_app_name ?? "",
    docker_image_name: existing?.docker_image_name ?? "",
    git_repo_url: existing?.git_repo_url ?? "",
    git_branch: existing?.git_branch ?? "",
    manifest_path: existing?.manifest_path ?? "",
    jenkins_credentials_id: existing?.jenkins_credentials_id ?? "",
    k8s_namespace: existing?.k8s_namespace ?? "",
    auto_create_sonarqube_project: existing?.auto_create_sonarqube_project ?? false,
    auto_create_jenkins_job: existing?.auto_create_jenkins_job ?? false,
    auto_create_argocd_app: existing?.auto_create_argocd_app ?? false,
    security_criterion: existing?.security_criterion ?? "inherit",
    anomaly_review_threshold: existing?.anomaly_review_threshold ?? NaN,
    anomaly_block_threshold: existing?.anomaly_block_threshold ?? NaN,
    ai_observation_mode: existing?.ai_observation_mode == null ? "inherit" : existing.ai_observation_mode ? "true" : "false",
    decision_engine_enabled: existing?.decision_engine_enabled ?? true,
  };
}

/**
 * Secret de Webhook prêt à coller dans la forge. Tiré dans le navigateur
 * (`crypto.getRandomValues`) : il n'a aucune raison de transiter par le
 * serveur avant même d'être choisi, et la même valeur doit de toute façon
 * être saisie des deux côtés par la personne qui configure le dépôt.
 */
function generateSecret(): string {
  const octets = crypto.getRandomValues(new Uint8Array(24));
  return Array.from(octets, (o) => o.toString(16).padStart(2, "0")).join("");
}

/** Champ vide = « comme le dépôt » côté API : on envoie null, jamais une chaîne vide. */
const orNull = (value: string) => value || null;

function toPayload(values: FormOutput): PipelineConfigInput {
  return {
    repository: values.repository,
    vcs_provider: values.vcs_provider,
    jenkins_job_name: orNull(values.jenkins_job_name),
    sonarqube_project_key: orNull(values.sonarqube_project_key),
    argocd_app_name: orNull(values.argocd_app_name),
    docker_image_name: orNull(values.docker_image_name),
    git_repo_url: orNull(values.git_repo_url),
    git_branch: orNull(values.git_branch),
    manifest_path: orNull(values.manifest_path),
    jenkins_credentials_id: orNull(values.jenkins_credentials_id),
    k8s_namespace: orNull(values.k8s_namespace),
    auto_create_sonarqube_project: values.auto_create_sonarqube_project,
    auto_create_jenkins_job: values.auto_create_jenkins_job,
    auto_create_argocd_app: values.auto_create_argocd_app,
    security_criterion: values.security_criterion === "inherit" ? null : values.security_criterion,
    anomaly_review_threshold: values.anomaly_review_threshold,
    anomaly_block_threshold: values.anomaly_block_threshold,
    ai_observation_mode: values.ai_observation_mode === "inherit" ? null : values.ai_observation_mode === "true",
    decision_engine_enabled: values.decision_engine_enabled,
    ...(values.webhook_secret ? { webhook_secret: values.webhook_secret } : {}),
  };
}


function Section({ title, children }: { title: MessageKey; children: React.ReactNode }) {
  const t = useT();
  return (
    <div className="border-t border-line pt-4">
      <p className="text-xs font-medium text-ink-3 uppercase tracking-wide mb-3">{t(title)}</p>
      {children}
    </div>
  );
}

type ToggleName = "auto_create_sonarqube_project" | "auto_create_jenkins_job" | "auto_create_argocd_app" | "decision_engine_enabled";

function Toggle({ control, name, label, hint }: { control: Control<FormInput, unknown, FormOutput>; name: ToggleName; label: MessageKey; hint?: MessageKey }) {
  const t = useT();
  return (
    <Controller
      control={control}
      name={name}
      render={({ field }) => (
        <div className={cn("flex items-center justify-between py-2", name === "decision_engine_enabled" && !field.value && "-mx-3 px-3 rounded-lg bg-critical-soft")}>
          <div>
            <p className="text-sm font-medium text-ink">{t(label)}</p>
            {hint && <p className="text-xs text-ink-3">{t(hint)}</p>}
          </div>
          <Switch checked={Boolean(field.value)} onChange={() => field.onChange(!field.value)} label={t(label)} />
        </div>
      )}
    />
  );
}

function PipelineFormModal({ existing, onClose }: { existing?: PipelineConfig; onClose: () => void }) {
  const t = useT();
  const create = useCreatePipelineConfig();
  const update = useUpdatePipelineConfig();

  const fullSchema = schema.superRefine((v, ctx) => {
    if (!existing && !v.webhook_secret) ctx.addIssue({ code: "custom", path: ["webhook_secret"], message: t("repos.secretRequired") });
    if ((v.auto_create_jenkins_job || v.auto_create_argocd_app) && !v.git_repo_url) ctx.addIssue({ code: "custom", path: ["git_repo_url"], message: t("repos.gitUrlRequired") });
  });
  const form = useForm<FormInput, unknown, FormOutput>({ resolver: zodResolver(fullSchema), defaultValues: toForm(existing) });
  const { register, control, setValue, formState: { errors } } = form;
  const watched = useWatch({ control });
  const autoJenkins = Boolean(watched.auto_create_jenkins_job);
  // Chargés seulement quand le job Jenkins est à créer : c'est là que la liste sert.
  const { data: credentials = [] } = useJenkinsCredentials(autoJenkins);
  const repositoryPlaceholder = watched.repository || t("repos.sameAsRepoPlaceholder");

  const submit = form.handleSubmit((values) => {
    const payload = toPayload(values);
    const onError = (err: unknown) => toast.error(extractError(err, t("repos.saveError")));
    if (existing) {
      update.mutate({ id: existing.id, ...payload }, { onSuccess: () => { toast.success(t("common.savedOk")); onClose(); }, onError });
    } else {
      create.mutate(payload, {
        onSuccess: (created) => {
          if (created.warnings.length) toast.warning(t("repos.savedWithWarnings"), { description: created.warnings.join("\n"), duration: 10_000 });
          else toast.success(t("common.savedOk"));
          onClose();
        },
        onError,
      });
    }
  });

  return (
    <Modal onClose={onClose} title={existing ? `${t("common.edit")} ${existing.repository}` : t("repos.add")} size="lg">
      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-[1fr_9rem] gap-3">
          <Input label={t("repos.name")} {...register("repository")} placeholder="mon-projet" error={errors.repository?.message} required disabled={!!existing} autoFocus={!existing} mono />
          <Controller
            control={control}
            name="vcs_provider"
            render={({ field }) => (
              <Select label={t("repos.forge")} value={field.value} onChange={(e) => field.onChange(e.target.value)}>
                {FORGES.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
              </Select>
            )}
          />
        </div>
        <div className="space-y-1.5">
          <Input type="text" label={t("repos.secret")} {...register("webhook_secret")} placeholder={existing ? t("integrations.keepSecret") : t("repos.secretPlaceholder")} error={errors.webhook_secret?.message} required={!existing} mono />
          <div className="flex items-center gap-3">
            <button type="button" onClick={() => setValue("webhook_secret", generateSecret(), { shouldValidate: true })} className="inline-flex items-center gap-1 text-xs text-accent hover:text-accent-hover">
              <RefreshCw className="w-3 h-3" /> {t("repos.secretGenerate")}
            </button>
            <span className="text-[11.5px] text-ink-3">{t("repos.secretGenerateHint")}</span>
          </div>
        </div>

        <Section title="repos.mappingsSection">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label={t("repos.jenkinsJob")} {...register("jenkins_job_name")} placeholder={repositoryPlaceholder} mono />
            <Input label={t("repos.sonarKey")} {...register("sonarqube_project_key")} placeholder={repositoryPlaceholder} mono />
            <Input label={t("repos.argocdApp")} {...register("argocd_app_name")} placeholder={repositoryPlaceholder} mono />
            <Input label={t("repos.image")} {...register("docker_image_name")} placeholder={repositoryPlaceholder} mono />
          </div>
        </Section>

        <Section title="repos.deploymentSection">
          <div className="space-y-3">
            <Input label={t("repos.gitUrl")} {...register("git_repo_url")} placeholder="http://host.docker.internal:3000/mon-org/mon-projet.git" error={errors.git_repo_url?.message} mono />
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <Input label={t("repos.branch")} {...register("git_branch")} placeholder="main" mono />
              <Input label={t("repos.manifestPath")} {...register("manifest_path")} placeholder="application.yaml" mono />
            </div>
          </div>
        </Section>

        <Section title="repos.provisioning">
          <Toggle control={control} name="auto_create_sonarqube_project" label="repos.autoSonar" />
          <Toggle control={control} name="auto_create_jenkins_job" label="repos.autoJenkins" />
          {autoJenkins && (
            <Controller
              control={control}
              name="jenkins_credentials_id"
              render={({ field }) => (
                <Select label={t("repos.jenkinsCredential")} value={field.value ?? ""} onChange={(e) => field.onChange(e.target.value)}>
                  <option value="">{t("common.none")}</option>
                  {credentials.map((c) => <option key={c.id} value={c.id}>{c.id} ({c.typeName}{c.description ? ` · ${c.description}` : ""})</option>)}
                </Select>
              )}
            />
          )}
          <Toggle control={control} name="auto_create_argocd_app" label="repos.autoArgocd" />
          {watched.auto_create_argocd_app && <Input label={t("repos.namespace")} {...register("k8s_namespace")} placeholder="default" />}
        </Section>

        <Section title="repos.engineSection">
          <Toggle control={control} name="decision_engine_enabled" label="repos.engineEnabled" hint="repos.engineEnabledHint" />
          <div className="mb-3">
            <Controller
              control={control}
              name="security_criterion"
              render={({ field }) => (
                <Select label={t("settings.security.title")} hint={t("repos.securityCriterionHint")} value={field.value} onChange={(e) => field.onChange(e.target.value)}>
                  <option value="inherit">{t("repos.inherit")}</option>
                  {SECURITY_CRITERIA.map((key) => (
                    <option key={key} value={key}>{t(`settings.security.${key}` as MessageKey)}</option>
                  ))}
                </Select>
              )}
            />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <Input label={t("settings.thresholds.review")} type="number" step="0.05" min={0} max={1} {...register("anomaly_review_threshold", { valueAsNumber: true })} placeholder="0.5" error={errors.anomaly_review_threshold?.message} />
            <Input label={t("settings.thresholds.block")} type="number" step="0.05" min={0} max={1} {...register("anomaly_block_threshold", { valueAsNumber: true })} placeholder="0.8" error={errors.anomaly_block_threshold?.message} />
          </div>
          <div className="mt-3">
            <Controller
              control={control}
              name="ai_observation_mode"
              render={({ field }) => (
                <Select label={t("repos.observation")} value={field.value} onChange={(e) => field.onChange(e.target.value)}>
                  <option value="inherit">{t("repos.inherit")}</option>
                  <option value="true">{t("repos.observationOn")}</option>
                  <option value="false">{t("repos.observationOff")}</option>
                </Select>
              )}
            />
          </div>
        </Section>

        <Button type="submit" isLoading={create.isPending || update.isPending} className="w-full">
          {existing ? t("common.saveChanges") : t("repos.save")}
        </Button>
      </form>
    </Modal>
  );
}
