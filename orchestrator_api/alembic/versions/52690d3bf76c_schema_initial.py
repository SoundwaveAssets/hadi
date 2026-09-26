"""Schéma initial : l'état des modèles au passage à Alembic.

Les bases créées avant sont marquées à jour (stamp) au démarrage, voir
app/core/database.py._migrate.

Revision ID: 52690d3bf76c
Revises: 
Create Date: 2026-09-20 18:58:34.019967

"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '52690d3bf76c'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('api_tokens',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('token_prefix', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('role', sa.Enum('DEVELOPER', 'ADMIN', 'SECURITY_OFFICER', 'DIRECTION', name='userrole'), nullable=False),
    sa.Column('created_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_revoked', sa.Boolean(), nullable=False),
    sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_api_tokens_token_hash'), 'api_tokens', ['token_hash'], unique=True)
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
    sa.Column('developer_username', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('repository_name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('commit_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('ai_anomaly_score', sa.Float(), nullable=True),
    sa.Column('ai_explanation', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('sonarqube_vulnerabilities', sa.Integer(), nullable=True),
    sa.Column('sonarqube_metrics', sa.Text(), nullable=True),
    sa.Column('decision', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('justification', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('approved_by', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('four_eyes_approved_by', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('supersedes_audit_id', sa.Integer(), nullable=True),
    sa.Column('previous_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('entry_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('compliance_policies',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('policy_type', sa.Enum('DEPLOYMENT_WINDOW', 'REINFORCED_REPOSITORY', name='compliancepolicytype'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('allowed_days', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('allowed_start_hour', sa.Integer(), nullable=True),
    sa.Column('allowed_end_hour', sa.Integer(), nullable=True),
    sa.Column('repository_scope', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('repository_pattern', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('module_states',
    sa.Column('module_key', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_by', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.PrimaryKeyConstraint('module_key')
    )
    op.create_table('notification_config',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('smtp_host', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('smtp_port', sa.Integer(), nullable=False),
    sa.Column('smtp_user', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('smtp_password', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('smtp_use_tls', sa.Boolean(), nullable=False),
    sa.Column('from_address', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('notify_on_waiting_human', sa.Boolean(), nullable=False),
    sa.Column('notify_on_blocked', sa.Boolean(), nullable=False),
    sa.Column('notify_on_derogation', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('pipeline_configs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('repository', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('vcs_provider', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('webhook_secret', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('jenkins_job_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('sonarqube_project_key', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('argocd_app_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('docker_image_name', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('git_repo_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('jenkins_credentials_id', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('k8s_namespace', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('git_branch', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('manifest_path', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('auto_create_sonarqube_project', sa.Boolean(), nullable=False),
    sa.Column('auto_create_jenkins_job', sa.Boolean(), nullable=False),
    sa.Column('auto_create_argocd_app', sa.Boolean(), nullable=False),
    sa.Column('anomaly_review_threshold', sa.Float(), nullable=True),
    sa.Column('anomaly_block_threshold', sa.Float(), nullable=True),
    sa.Column('ai_observation_mode', sa.Boolean(), nullable=True),
    sa.Column('decision_engine_enabled', sa.Boolean(), nullable=False),
    sa.Column('created_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_pipeline_configs_repository'), 'pipeline_configs', ['repository'], unique=True)
    op.create_table('pipelines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('repository', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('branch', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('commit_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('commit_message', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('author', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('status', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('jenkins_build_number', sa.Integer(), nullable=True),
    sa.Column('execution_log', sa.Text(), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('repository', 'commit_id', name='ix_pipelines_repository_commit_id')
    )
    op.create_index(op.f('ix_pipelines_commit_id'), 'pipelines', ['commit_id'], unique=False)
    op.create_index(op.f('ix_pipelines_repository'), 'pipelines', ['repository'], unique=False)
    op.create_table('system_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('setup_step', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('setup_locked', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('tool_configurations',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('gitea_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('gitea_token', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('github_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('github_token', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('gitlab_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('gitlab_token', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('jenkins_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('jenkins_user', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('jenkins_token', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('sonarqube_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('sonarqube_token', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('argocd_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('argocd_token', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('ai_observation_mode', sa.Boolean(), nullable=False),
    sa.Column('anomaly_review_threshold', sa.Float(), nullable=False),
    sa.Column('anomaly_block_threshold', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('email', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
    sa.Column('hashed_password', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('role', sa.Enum('DEVELOPER', 'ADMIN', 'SECURITY_OFFICER', 'DIRECTION', name='userrole'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('must_change_password', sa.Boolean(), nullable=False),
    sa.Column('failed_login_attempts', sa.Integer(), nullable=False),
    sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)
    op.create_table('webhook_deliveries',
    sa.Column('delivery_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('provider', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('repository', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
    sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('delivery_id')
    )


def downgrade() -> None:
    op.drop_table('webhook_deliveries')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_table('users')
    op.drop_table('tool_configurations')
    op.drop_table('system_settings')
    op.drop_index(op.f('ix_pipelines_repository'), table_name='pipelines')
    op.drop_index(op.f('ix_pipelines_commit_id'), table_name='pipelines')
    op.drop_table('pipelines')
    op.drop_index(op.f('ix_pipeline_configs_repository'), table_name='pipeline_configs')
    op.drop_table('pipeline_configs')
    op.drop_table('notification_config')
    op.drop_table('module_states')
    op.drop_table('compliance_policies')
    op.drop_table('audit_logs')
    op.drop_index(op.f('ix_api_tokens_token_hash'), table_name='api_tokens')
    op.drop_table('api_tokens')
