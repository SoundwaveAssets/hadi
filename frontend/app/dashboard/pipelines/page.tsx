"use client";

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { GitBranch } from "lucide-react";
import { usePipelines, type Pipeline } from "@/lib/api";
import { useT } from "@/lib/i18n";
import { StatusBadge } from "@/components/StatusBadge";
import { IdentityBadge } from "@/components/IdentityBadge";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { DataTable, type ColumnDef } from "@/components/ui/DataTable";
import { RepositorySelector } from "@/components/RepositorySelector";
import { FilterInput } from "@/components/devtools/FilterInput";

const PAGE_SIZE = 50;

export default function PipelinesPage() {
  const t = useT();
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [repository, setRepository] = useState("");
  const [offset, setOffset] = useState(0);
  const { data, isLoading } = usePipelines(repository || undefined, PAGE_SIZE, offset);

  const columns = useMemo<ColumnDef<Pipeline, unknown>[]>(
    () => [
      {
        id: "repository",
        accessorFn: (p) => `${p.repository} ${p.branch}`,
        header: t("pipelines.repoBranch"),
        meta: { width: "24%" },
        cell: ({ row }) => (
          <>
            <div className="font-medium text-ink truncate">{row.original.repository}</div>
            <div className="text-ink-3 text-xs truncate">{row.original.branch}</div>
          </>
        ),
      },
      {
        id: "commit",
        accessorFn: (p) => `${p.commit_message} ${p.commit_id}`,
        header: t("common.commit"),
        enableSorting: false,
        meta: { width: "40%" },
        cell: ({ row }) => (
          <>
            <div className="text-ink-2 truncate" title={row.original.commit_message}>{row.original.commit_message}</div>
            <div className="text-ink-3 text-xs font-mono">{row.original.commit_id.slice(0, 8)}</div>
          </>
        ),
      },
      {
        accessorKey: "author",
        header: t("common.author"),
        meta: { width: "14%" },
        cell: ({ row: { original: p } }) => <IdentityBadge username={p.author} source={p.identity_source} commitAuthor={p.commit_author} />,
      },
      { accessorKey: "status", header: t("common.status"), meta: { width: "22%" }, cell: ({ getValue }) => <StatusBadge status={getValue<string>()} /> },
    ],
    [t]
  );

  const items = data?.items ?? [];

  return (
    <div className="space-y-4">
      <PageHeader
        title={t("page.executions")}
        actions={
          <div className="flex items-center gap-2">
            <RepositorySelector value={repository} onChange={(value) => { setRepository(value); setOffset(0); }} />
            <FilterInput value={query} onChange={setQuery} className="w-44" />
          </div>
        }
      />
      {!isLoading && items.length === 0 ? (
        <EmptyState icon={GitBranch} title={t("pipelines.empty")} description={t("pipelines.emptyHint")} tone="brand" />
      ) : (
        <DataTable
          columns={columns}
          data={items}
          rowKey={(p) => p.id}
          isLoading={isLoading}
          filter={query}
          onRowClick={(p) => router.push(`/dashboard/pipelines/${p.id}`)}
          pagination={data ? { offset, limit: PAGE_SIZE, total: data.total, onChange: setOffset } : undefined}
          empty={t("common.noResults")}
        />
      )}
    </div>
  );
}
