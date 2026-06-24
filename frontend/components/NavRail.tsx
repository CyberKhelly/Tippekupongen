"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, BarChart2, Activity, Info, Layers2 } from "lucide-react";
import type { LucideProps } from "lucide-react";
import { cn } from "@/lib/utils";
import { LogoMark } from "@/components/LogoMark";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const MAIN_NAV = [
  { href: "/coupon",     icon: LayoutGrid, label: "Kupong"     },
  { href: "/strategien", icon: Layers2,    label: "Systemspill" },
  { href: "/historikk",  icon: BarChart2,  label: "Historikk"  },
  { href: "/modellen",   icon: Activity,   label: "Modellen"   },
] as const;

function NavItem({
  href,
  icon: Icon,
  label,
  active,
}: {
  href: string;
  icon: React.ComponentType<LucideProps>;
  label: string;
  active: boolean;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Link
          href={href}
          aria-label={label}
          aria-current={active ? "page" : undefined}
          className={cn(
            "relative flex h-9 w-9 items-center justify-center rounded-lg",
            "outline-none focus-visible:ring-2 focus-visible:ring-[#D4930A]/40",
            "transition-colors duration-150",
            active
              ? "bg-[#EEEBE5] text-[#111110]"
              : "text-[#ADA9A2] hover:bg-[#F5F3EF] hover:text-[#6B6862]",
          )}
        >
          {active && (
            <span
              aria-hidden
              className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-[14px] rounded-r-full bg-[#D4930A]"
            />
          )}
          <Icon size={17} strokeWidth={active ? 2.2 : 1.75} />
        </Link>
      </TooltipTrigger>
      <TooltipContent
        side="right"
        sideOffset={12}
        className="z-50 overflow-hidden rounded-md px-2.5 py-1 text-[11px] font-semibold bg-[#111110] text-white border-0 shadow-[0_4px_12px_rgba(0,0,0,0.18)]"
      >
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

export function NavRail() {
  const pathname = usePathname();

  return (
    <TooltipProvider delayDuration={300} skipDelayDuration={100}>
      <nav
        aria-label="Navigasjon"
        className="fixed inset-y-0 left-0 z-30 flex flex-col items-center w-12 bg-white border-r border-[#E4E1DA] select-none"
      >
        {/* Logo mark */}
        <Link
          href="/coupon"
          aria-label="TippeQpongen"
          className="flex items-center justify-center h-12 w-full shrink-0 opacity-70 hover:opacity-100 transition-opacity outline-none focus-visible:ring-2 focus-visible:ring-[#D4930A]/40 focus-visible:ring-inset"
        >
          <LogoMark size={20} />
        </Link>

        <span aria-hidden className="w-5 h-px bg-[#E4E1DA]" />

        {/* Main nav */}
        <div className="flex flex-col items-center gap-0.5 py-3 flex-1">
          {MAIN_NAV.map(({ href, icon, label }) => {
            const active =
              href === "/coupon"
                ? pathname === "/coupon" || pathname === "/"
                : pathname.startsWith(href);
            return (
              <NavItem
                key={href}
                href={href}
                icon={icon}
                label={label}
                active={active}
              />
            );
          })}
        </div>

        {/* Bottom: Om */}
        <div className="flex flex-col items-center pb-4">
          <span aria-hidden className="w-5 h-px bg-[#E4E1DA] mb-3" />
          <NavItem
            href="/om"
            icon={Info}
            label="Om TippeQpongen"
            active={pathname === "/om"}
          />
        </div>
      </nav>
    </TooltipProvider>
  );
}
