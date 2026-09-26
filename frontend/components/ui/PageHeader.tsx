export function PageHeader({
  title,
  description,
  actions,
}: {
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-3 flex-wrap min-h-8">
      <div className="min-w-0">
        <h2 className="text-[18px] font-semibold text-ink tracking-tight leading-tight">{title}</h2>
        {description && <p className="text-[12.5px] text-ink-3 mt-0.5 leading-snug">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-1.5 flex-wrap justify-end">{actions}</div>}
    </div>
  );
}
