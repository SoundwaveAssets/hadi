/** Formes renvoyées par l'API, partagées par les pages et les hooks. */

export type UserRole = "developer" | "admin" | "security_officer" | "direction";
export type Forge = "gitea" | "github" | "gitlab";
export type ToolKey = Forge | "jenkins" | "sonarqube" | "argocd";

export interface Page<T> {
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

export type IdentitySource = "mapped" | "forge" | "git-author";

export interface Pipeline {
  id: number;
  repository: string;
  branch: string;
  commit_id: string;
  commit_message: string;
  /** Identité résolue du pusher : compte Hadi relié, sinon login de forge, sinon nom d'auteur Git. */
  author: string;
  commit_author: string | null;
  identity_source: IdentitySource | null;
  status: string;
  created_at: string;
  jenkins_build_number: number | null;
  execution_log: string | null;
}

export interface AuditEntry {
  id: number;
  timestamp: string;
  repository_name: string;
  developer_username: string;
  developer_identity_source: IdentitySource | null;
  commit_hash: string;
  decision: string;
  justification: string;
  ai_anomaly_score: number | null;
  ai_explanation: string | null;
  sonarqube_vulnerabilities: number | null;
  sonarqube_metrics: string | null;
  approved_by: string | null;
  four_eyes_approved_by: string | null;
  supersedes_audit_id: number | null;
  entry_hash: string;
}

/** Instantané SonarQube conservé dans l'audit (sonarqube_metrics, JSON). */
export interface SonarMetrics {
  vulnerabilities?: number;
  bugs?: number;
  security_rating?: string | null;
  reliability_rating?: string | null;
  maintainability_rating?: string | null;
  security_hotspots_reviewed?: number | null;
  coverage?: number | null;
  duplicated_lines_density?: number | null;
  lines_of_code?: number;
}

export interface Stage {
  name: string;
  status: string;
  duration_ms: number | null;
}

/** Réponse de /pipelines/{id}/stages : les étapes seules, pour un suivi rapproché. */
export interface PipelineStages {
  pipeline_id: number;
  status: string;
  jenkins_build_number: number | null;
  stages: Stage[];
}

export interface PipelineLogs {
  pipeline_id: number;
  jenkins_console: string | null;
  stages: Stage[];
  execution_log: string | null;
  notes: string[];
}

export interface Summary {
  pipelines_total: number;
  pipeline_status_counts: Record<string, number>;
  decision_counts: Record<string, number>;
}

export interface DayActivity {
  date: string;
  total: number;
  deployed: number;
  blocked: number;
}

export interface User {
  id: number;
  username: string;
  email: string | null;
  role: UserRole;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
}

export interface ForgeIdentity {
  id: number;
  user_id: number;
  provider: Forge;
  login: string;
  external_id: string | null;
  created_at: string;
}

export interface ApiToken {
  id: number;
  name: string;
  token_prefix: string;
  role: UserRole;
  created_by: string;
  created_at: string;
  last_used_at: string | null;
  is_revoked: boolean;
}

export type PolicyType = "deployment_window" | "reinforced_repository";

export interface CompliancePolicy {
  id: number;
  name: string;
  policy_type: PolicyType;
  is_active: boolean;
  created_by: string;
  allowed_days: string | null;
  allowed_start_hour: number | null;
  allowed_end_hour: number | null;
  repository_scope: string | null;
  repository_pattern: string | null;
}

export interface PipelineConfig {
  id: number;
  repository: string;
  vcs_provider: Forge;
  is_active: boolean;
  webhook_secret: boolean;
  jenkins_job_name: string | null;
  sonarqube_project_key: string | null;
  argocd_app_name: string | null;
  docker_image_name: string | null;
  git_repo_url: string | null;
  git_branch: string | null;
  manifest_path: string | null;
  jenkins_credentials_id: string | null;
  k8s_namespace: string | null;
  auto_create_sonarqube_project: boolean;
  auto_create_jenkins_job: boolean;
  auto_create_argocd_app: boolean;
  security_criterion: SecurityCriterion | null;
  anomaly_review_threshold: number | null;
  anomaly_block_threshold: number | null;
  ai_observation_mode: boolean | null;
  decision_engine_enabled: boolean;
  created_by: string;
}

export interface JenkinsCredential {
  id: string;
  description: string;
  typeName: string;
}

/** Configuration des outils, secrets masqués (booléen « configuré »). */
export interface ToolConfig {
  gitea_url?: string | null;
  gitea_token?: boolean;
  github_url?: string | null;
  github_token?: boolean;
  gitlab_url?: string | null;
  gitlab_token?: boolean;
  jenkins_url?: string | null;
  jenkins_user?: string | null;
  jenkins_token?: boolean;
  sonarqube_url?: string | null;
  sonarqube_token?: boolean;
  argocd_url?: string | null;
  argocd_token?: boolean;
  security_criterion?: SecurityCriterion;
  ai_observation_mode?: boolean;
  anomaly_review_threshold?: number;
  anomaly_block_threshold?: number;
}

/**
 * Ce que le moteur regarde pour juger la sécurité d'un commit :
 * le code neuf (défaut), le Quality Gate SonarQube, ou la dette du projet.
 */
export type SecurityCriterion = "new_code" | "quality_gate" | "total";
export const SECURITY_CRITERIA: SecurityCriterion[] = ["new_code", "quality_gate", "total"];

export interface HealthEntry {
  configured: boolean;
  reachable: boolean | null;
  /** null = aucun jeton enregistré, donc rien à vérifier au-delà de l'atteignabilité. */
  authenticated?: boolean | null;
  error?: string;
  message?: string;
  code?: string;
}

export type Health = Record<string, HealthEntry>;

export interface TestResult {
  reachable: boolean;
  code: string;
  message: string;
  http?: number;
}

/** Action d'administration scellée (comptes, intégrations, modules, politiques, pipelines, connexions). */
export interface AdminEvent {
  id: number;
  timestamp: string;
  actor: string;
  actor_role: UserRole;
  action: string;
  target_type: string;
  target_id: string | null;
  target_label: string | null;
  /** Instantanés JSON, secrets déjà masqués côté API. */
  before: string | null;
  after: string | null;
  ip: string | null;
  entry_hash: string;
}

export interface ChainVerification {
  status: "intact" | "corrupted";
  message: string;
  corrupted_id?: number | null;
}

export interface ModuleInfo {
  key: string;
  name: string;
  description: string;
  category: string;
  is_core: boolean;
  is_active: boolean;
}

export interface NotificationConfig {
  smtp_host?: string | null;
  smtp_port?: number;
  smtp_user?: string | null;
  smtp_password?: boolean;
  smtp_use_tls?: boolean;
  from_address?: string | null;
  notify_on_blocked?: boolean;
  notify_on_waiting_human?: boolean;
  notify_on_derogation?: boolean;
}
