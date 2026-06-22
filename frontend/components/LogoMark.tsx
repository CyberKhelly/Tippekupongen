interface LogoMarkProps {
  size?: number;
  className?: string;
}

export function LogoMark({ size = 36, className }: LogoMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 48 48"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      role="img"
      aria-label="TippeQpongen"
      className={className}
    >
      <rect width="48" height="48" rx="10" fill="#111110" />
      <rect x="9"  y="28" width="8" height="12" rx="2" fill="#F5C542" fillOpacity="0.45" />
      <rect x="20" y="18" width="8" height="22" rx="2" fill="#F5C542" fillOpacity="0.70" />
      <rect x="31" y="10" width="8" height="30" rx="2" fill="#F5C542" />
    </svg>
  );
}
