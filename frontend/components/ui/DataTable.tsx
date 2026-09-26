"use client";

import { useState, type ReactNode } from "react";
import {
  type ColumnDef,
  type SortingState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight } from "lucide-react";
import { useT } from "@/lib/i18n";
import { cn } from "@/lib/cn";
import { CenteredSpinner } from "./Spinner";

export type { ColumnDef };

export interface ServerPagination {
  offset: number;
  limit: number;
  total: number;
  onChange: (offset: number) => void;
}

interface DataTableProps<Row> {
  columns: ColumnDef<Row, unknown>[];
  data: Row[];
  rowKey: (row: Row) => string | number;
  isLoading?: boolean;
  /** Filtre plein texte sur les colonnes (tri et filtre côté client, sur les lignes reçues). */
  filter?: string;
  onRowClick?: (row: Row) => void;
  /** Pagination tenue par l'API : la table n'affiche que la page reçue. */
  pagination?: ServerPagination;
  empty?: ReactNode;
  className?: string;
}

/**
 * Table dense d'outil : en-tête collant, tri au clic, filtre, pagination.
 * Les colonnes déclarent `meta.align`, `meta.mono` et `meta.width` ;
 * le rendu des cellules reste dans les pages.
 */
export function DataTable<Row>({ columns, data, rowKey, isLoading, filter = "", onRowClick, pagination, empty, className }: DataTableProps<Row>) {
  const t = useT();
  const [sorting, setSorting] = useState<SortingState>([]);
  // eslint-disable-next-line react-hooks/incompatible-library -- react-table gère sa propre mémoïsation
  const table = useReactTable({
    data,
    columns,
    state: { sorting, globalFilter: filter },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    getRowId: (row) => String(rowKey(row)),
  });
  const rows = table.getRowModel().rows;

  return (
    <div className={cn("rounded border border-line bg-surface overflow-hidden", className)}>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13px] table-fixed">
          <colgroup>
            {table.getAllLeafColumns().map((column) => (
              <col key={column.id} style={{ width: column.columnDef.meta?.width }} />
            ))}
          </colgroup>
          <thead className="sticky top-0 z-[1] bg-surface-2">
            {table.getHeaderGroups().map((group) => (
              <tr key={group.id}>
                {group.headers.map((header) => {
                  const sortable = header.column.getCanSort();
                  const direction = header.column.getIsSorted();
                  return (
                    <th
                      key={header.id}
                      scope="col"
                      onClick={sortable ? header.column.getToggleSortingHandler() : undefined}
                      className={cn(
                        "h-8 px-3 text-[11px] font-semibold uppercase tracking-wider text-ink-3 whitespace-nowrap border-b border-line select-none",
                        ALIGN[header.column.columnDef.meta?.align ?? "left"],
                        sortable && "cursor-pointer hover:text-ink-2"
                      )}
                    >
                      <span className="inline-flex items-center gap-1">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        {direction === "asc" && <ArrowUp className="w-3 h-3" />}
                        {direction === "desc" && <ArrowDown className="w-3 h-3" />}
                      </span>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {isLoading ? (
              <tr>
                <td colSpan={columns.length}><CenteredSpinner className="py-10" /></td>
              </tr>
            ) : rows.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center text-ink-3">{empty ?? t("common.noData")}</td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                  tabIndex={onRowClick ? 0 : undefined}
                  onKeyDown={onRowClick ? (e) => { if (e.key === "Enter") onRowClick(row.original); } : undefined}
                  className={cn(
                    "border-b border-line last:border-b-0 hover:bg-surface-2/60 transition-colors",
                    onRowClick && "cursor-pointer focus-visible:bg-accent-soft/60 outline-none"
                  )}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className={cn(
                        "px-3 py-1.5 align-middle text-ink-2 truncate",
                        ALIGN[cell.column.columnDef.meta?.align ?? "left"],
                        cell.column.columnDef.meta?.mono && "font-mono text-[12px] tabular-nums"
                      )}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {pagination && pagination.total > pagination.limit && <Pager {...pagination} />}
    </div>
  );
}

function Pager({ offset, limit, total, onChange }: ServerPagination) {
  const t = useT();
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <div className="flex items-center justify-between px-3 h-9 border-t border-line text-[12px] text-ink-3">
      <span>{t("common.pageOf", { page, pages, total })}</span>
      <span className="inline-flex gap-1">
        <PagerButton disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))} icon={ChevronLeft} />
        <PagerButton disabled={offset + limit >= total} onClick={() => onChange(offset + limit)} icon={ChevronRight} />
      </span>
    </div>
  );
}

function PagerButton({ disabled, onClick, icon: Icon }: { disabled: boolean; onClick: () => void; icon: typeof ChevronLeft }) {
  return (
    <button type="button" disabled={disabled} onClick={onClick} className="p-1 rounded hover:bg-surface-2 disabled:opacity-40 disabled:cursor-not-allowed">
      <Icon className="w-4 h-4" />
    </button>
  );
}

const ALIGN = { left: "text-left", right: "text-right", center: "text-center" } as const;

declare module "@tanstack/react-table" {
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  interface ColumnMeta<TData, TValue> {
    align?: "left" | "right" | "center";
    mono?: boolean;
    /** Largeur CSS (ex. "12ch", "20%") ; sans valeur, part du reste. */
    width?: string;
  }
}
