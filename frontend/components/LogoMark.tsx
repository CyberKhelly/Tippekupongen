import { LogoIcon } from "@/components/brand/Logo";

interface LogoMarkProps {
  size?: number;
  className?: string;
}

export function LogoMark({ size = 24 }: LogoMarkProps) {
  return <LogoIcon height={size} theme="on-dark" />;
}
