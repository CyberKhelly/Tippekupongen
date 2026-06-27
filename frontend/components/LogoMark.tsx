import { LogoIcon } from "@/components/brand/Logo";

interface LogoMarkProps {
  size?: number;
  className?: string;
}

// NavRail icon — dark surface, so uses the card variant for contrast
export function LogoMark({ size = 24 }: LogoMarkProps) {
  return <LogoIcon height={size} theme="dark" />;
}
