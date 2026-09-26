"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  Bell,
  Blocks,
  ChevronRight,
  FileBarChart,
  FileClock,
  FolderGit2,
  History,
  KeyRound,
  KeySquare,
  LayoutDashboard,
  LogOut,
  Menu as MenuIcon,
  Plug,
  ScrollText,
  Settings,
  ShieldAlert,
  ShieldQuestion,
  Terminal,
  User as UserIcon,
  Users,
  X,
} from "lucide-react";
import { useAuth, type AuthUser, type UserRole } from "@/contexts/AuthContext";
import { ModulesProvider, useModules } from "@/contexts/ModulesContext";
import { useIdleLock } from "@/lib/session";
import { PasswordConfirmation } from "@/components/PasswordConfirmation";
import { HadiLogo } from "@/components/HadiLogo";
import { LanguageToggle } from "@/components/LanguageToggle";
import { NotificationsBell } from "@/components/NotificationsBell";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Menu, MenuItem } from "@/components/ui/Menu";
import { Spinner } from "@/components/ui/Spinner";
import { useT, type MessageKey } from "@/lib/i18n";
import { cn } from "@/lib/cn";

interface NavItem {
  href: string;
  label: MessageKey;
  icon: typeof LayoutDashboard;
  roles?: UserRole[];
  moduleKey?: string;
}

interface NavGroup {
  label: MessageKey;
  items: NavItem[];
}

const NAV_GROUPS: NavGroup[] = [
  {
    label: "nav.group.pipelines",
    items: [
      { href: "/dashboard", label: "nav.overview", icon: LayoutDashboard },
      { href: "/dashboard/pipelines", label: "nav.executions", icon: History, moduleKey: "pipelines" },
      { href: "/dashboard/pipeline-configs", label: "nav.repositories", icon: FolderGit2, roles: ["admin", "security_officer"], moduleKey: "pipelines" },
      { href: "/dashboard/decisions", label: "nav.decisions", icon: ShieldAlert, moduleKey: "decisions" },
    ],
  },
  {
    label: "nav.group.security",
    items: [
      { href: "/dashboard/derogations", label: "nav.derogations", icon: FileClock, roles: ["admin", "security_officer", "direction"], moduleKey: "derogations" },
      { href: "/dashboard/audit", label: "nav.audit", icon: ScrollText, roles: ["admin", "security_officer"], moduleKey: "audit" },
      { href: "/dashboard/compliance-policies", label: "nav.policies", icon: ShieldQuestion, roles: ["admin", "security_officer"], moduleKey: "compliance_policies" },
    ],
  },
  {
    label: "nav.group.system",
    items: [
      { href: "/dashboard/integrations", label: "nav.integrations", icon: Plug, roles: ["admin", "security_officer"], moduleKey: "integrations" },
      { href: "/dashboard/monitoring", label: "nav.monitoring", icon: Activity, roles: ["admin", "security_officer"], moduleKey: "monitoring" },
      { href: "/dashboard/notifications", label: "nav.notifications", icon: Bell, roles: ["admin", "security_officer"], moduleKey: "notifications" },
      { href: "/dashboard/reports", label: "nav.reports", icon: FileBarChart, roles: ["admin", "security_officer", "direction"], moduleKey: "reports" },
      { href: "/dashboard/cli", label: "nav.cli", icon: Terminal, roles: ["admin", "security_officer", "developer", "direction"] },
    ],
  },
  {
    label: "nav.group.admin",
    items: [
      { href: "/dashboard/users", label: "nav.users", icon: Users, roles: ["admin"] },
      { href: "/dashboard/api-tokens", label: "nav.tokens", icon: KeySquare, roles: ["admin"], moduleKey: "api_tokens" },
      { href: "/dashboard/modules", label: "nav.modules", icon: Blocks, roles: ["admin"] },
      { href: "/dashboard/settings", label: "nav.settings", icon: Settings, roles: ["admin", "security_officer"] },
    ],
  },
];

const ALL_ITEMS = NAV_GROUPS.flatMap((g) => g.items);

function initials(username: string): string {
  return username.slice(0, 2).toUpperCase();
}

function breadcrumb(pathname: string): { label: MessageKey | string; href?: string }[] {
  const exact = ALL_ITEMS.find((i) => i.href === pathname);
  if (exact) return exact.href === "/dashboard" ? [{ label: exact.label }] : [{ label: "nav.overview", href: "/dashboard" }, { label: exact.label }];

  const parent = ALL_ITEMS.filter((i) => i.href !== "/dashboard" && pathname.startsWith(i.href + "/")).sort((a, b) => b.href.length - a.href.length)[0];
  if (parent) {
    const tail = pathname.slice(parent.href.length + 1).split("/")[0];
    return [{ label: "nav.overview", href: "/dashboard" }, { label: parent.label, href: parent.href }, { label: /^\d+$/.test(tail) ? `#${tail}` : tail }];
  }
  return [{ label: "nav.overview", href: "/dashboard" }];
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
  // Le menu mobile est ouvert "pour un chemin" : changer de page le referme
  // sans effet ni setState, l'état se dérive pendant le rendu.
  const [openFor, setOpenFor] = useState<string | null>(null);
  const navOpen = openFor === pathname;
  const setNavOpen = (open: boolean) => setOpenFor(open ? pathname : null);

  useEffect(() => {
    if (isLoading) return;
    if (!user) router.push("/login");
    else if (user.must_change_password) router.push("/change-password");
  }, [isLoading, user, router]);

  // Poste laissé sans surveillance : la session est effacée au-delà du délai
  // d'inactivité de l'instance, et prolongée tant que quelqu'un travaille.
  useIdleLock(logout);

  useEffect(() => {
    if (!navOpen) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpenFor(null);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen]);

  if (isLoading || !user || user.must_change_password) {
    return (
      <div className="flex h-dvh items-center justify-center bg-page">
        <Spinner className="w-6 h-6" />
      </div>
    );
  }

  return (
    <ModulesProvider>
      <PasswordConfirmation />
      <div className="flex flex-col h-dvh bg-page">
        <TopBar user={user} pathname={pathname} onLogout={logout} onOpenNav={() => setNavOpen(true)} />
        <div className="flex flex-1 min-h-0">
          {navOpen && <div className="fixed inset-0 bg-black/50 z-40 md:hidden" onClick={() => setNavOpen(false)} aria-hidden="true" />}
          <Sidebar user={user} pathname={pathname} isOpen={navOpen} onClose={() => setNavOpen(false)} />
          <main className="flex-1 min-w-0 overflow-y-auto px-4 py-4 md:px-6 md:py-5">{children}</main>
        </div>
      </div>
    </ModulesProvider>
  );
}

function TopBar({ user, pathname, onLogout, onOpenNav }: { user: AuthUser; pathname: string; onLogout: () => void; onOpenNav: () => void }) {
  const router = useRouter();
  const t = useT();
  const crumbs = breadcrumb(pathname);
  const label = (l: MessageKey | string) => (l.startsWith("nav.") ? t(l as MessageKey) : l);

  return (
    <header className="h-11 flex-shrink-0 bg-chrome text-chrome-ink border-b border-chrome-line flex items-center gap-3 px-3 md:px-4">
      <button onClick={onOpenNav} className="p-1.5 -ml-1 rounded text-chrome-ink-2 hover:text-chrome-ink hover:bg-chrome-2 md:hidden" aria-label={t("nav.open")}>
        <MenuIcon className="w-4.5 h-4.5" />
      </button>

      <Link href="/dashboard" className="flex items-center gap-2 flex-shrink-0 mr-2 text-chrome-ink">
        <HadiLogo size={20} />
        <span className="text-[13.5px] font-semibold tracking-tight hidden sm:inline">{t("app.name")}</span>
      </Link>

      <nav aria-label={t("nav.breadcrumb")} className="flex items-center gap-1 min-w-0 text-[12.5px]">
        {crumbs.map((crumb, index) => (
          <span key={index} className="flex items-center gap-1 min-w-0">
            {index > 0 && <ChevronRight className="w-3.5 h-3.5 text-chrome-ink-2 flex-shrink-0" aria-hidden="true" />}
            {crumb.href ? (
              <Link href={crumb.href} className="text-chrome-ink-2 hover:text-chrome-ink truncate">{label(crumb.label)}</Link>
            ) : (
              <span className="text-chrome-ink truncate font-medium" aria-current="page">{label(crumb.label)}</span>
            )}
          </span>
        ))}
      </nav>

      <div className="flex-1" />

      <LanguageToggle className="hidden sm:inline-flex" />
      <div className="flex items-center gap-0.5 [&_button]:text-chrome-ink-2 [&_button:hover]:text-chrome-ink [&_button:hover]:bg-chrome-2">
        <ThemeToggle />
        <NotificationsBell role={user.role} onNavigate={(href) => router.push(href)} />
      </div>

      <Menu
        trigger={({ onClick }) => (
          <button onClick={onClick} className="flex items-center gap-2 pl-1 pr-2 h-8 rounded hover:bg-chrome-2 transition-colors">
            <span className="w-6 h-6 rounded-sm bg-chrome-2 border border-chrome-line flex items-center justify-center text-[10px] font-semibold">{initials(user.username)}</span>
            <span className="hidden sm:block text-[12.5px] font-mono text-chrome-ink-2">{user.username}</span>
          </button>
        )}
      >
        <div className="px-3.5 py-2.5 border-b border-line">
          <p className="text-sm font-medium text-ink truncate">{user.username}</p>
          <p className="text-xs text-ink-3">{t(`role.${user.role}`)}</p>
        </div>
        <MenuItem icon={UserIcon} href="/dashboard/profile">{t("user.profile")}</MenuItem>
        <MenuItem icon={KeyRound} href="/change-password">{t("user.changePassword")}</MenuItem>
        <div className="sm:hidden px-3.5 py-2 border-t border-line">
          <LanguageToggle />
        </div>
        <div className="border-t border-line mt-1 pt-1">
          <MenuItem icon={LogOut} danger onClick={onLogout}>{t("user.logout")}</MenuItem>
        </div>
      </Menu>
    </header>
  );
}

function Sidebar({ user, pathname, isOpen, onClose }: { user: AuthUser; pathname: string; isOpen: boolean; onClose: () => void }) {
  const { isActive: isModuleActive } = useModules();
  const t = useT();

  const groups = NAV_GROUPS.map((group) => ({
    ...group,
    items: group.items.filter((item) => (!item.roles || item.roles.includes(user.role)) && (!item.moduleKey || isModuleActive(item.moduleKey))),
  })).filter((group) => group.items.length > 0);

  return (
    <aside
      aria-label={t("nav.main")}
      className={cn(
        "w-56 flex-shrink-0 bg-surface border-r border-line flex flex-col z-50 fixed md:static inset-y-0 left-0 top-11 md:top-auto transition-transform duration-150",
        isOpen ? "translate-x-0" : "-translate-x-full md:translate-x-0"
      )}
    >
      <div className="flex items-center justify-end px-2 pt-2 md:hidden">
        <button onClick={onClose} className="p-1.5 rounded text-ink-3 hover:text-ink hover:bg-surface-2" aria-label={t("nav.close")}>
          <X className="w-4 h-4" />
        </button>
      </div>

      <nav className="flex-1 overflow-y-auto py-2">
        {groups.map((group) => (
          <div key={group.label} className="mb-3">
            <p className="px-4 pt-2 pb-1 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-ink-3">{t(group.label)}</p>
            <ul>
              {group.items.map((item) => {
                const isActive = pathname === item.href || (item.href !== "/dashboard" && pathname.startsWith(item.href + "/"));
                const Icon = item.icon;
                return (
                  <li key={item.href}>
                    <Link
                      href={item.href}
                      aria-current={isActive ? "page" : undefined}
                      className={cn(
                        "flex items-center gap-2.5 h-8 pl-3.5 pr-3 border-l-[3px] text-[13px] transition-colors",
                        isActive ? "border-accent bg-accent-soft text-ink font-medium" : "border-transparent text-ink-2 hover:text-ink hover:bg-surface-2"
                      )}
                    >
                      <Icon className={cn("w-4 h-4 flex-shrink-0", isActive ? "text-accent" : "text-ink-3")} />
                      <span className="truncate">{t(item.label)}</span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      <div className="px-4 py-2.5 border-t border-line">
        <p className="text-[11px] text-ink-3 font-mono truncate">
          {user.username} · {t(`role.${user.role}`)}
        </p>
      </div>
    </aside>
  );
}
