interface LogoMarkProps {
  size?: number;
  className?: string;
}

/**
 * TippeQpongen logo mark — three ascending probability bars.
 *
 * Bars represent the H/U/B outcome distribution, ordered shortest→tallest
 * (left to right). Amber fill with diminishing opacity on shorter bars.
 * Scales cleanly from 16px to 256px.
 *
 * Usage rules:
 *  • Always render on #111 or darker backgrounds
 *  • Clear space: minimum 0.5× mark-width on all sides
 *  • Do not rotate, recolour, or clip
 *  • Monochrome variant: /logo-mono.svg (white bars on dark)
 */
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
      {/* Dark container */}
      <rect width="48" height="48" rx="10" fill="#111111" />
      {/* Left bar — shortest, most muted */}
      <rect x="9"  y="28" width="8" height="12" rx="2" fill="#F5C542" fillOpacity="0.45" />
      {/* Center bar — medium */}
      <rect x="20" y="18" width="8" height="22" rx="2" fill="#F5C542" fillOpacity="0.70" />
      {/* Right bar — tallest, full amber */}
      <rect x="31" y="10" width="8" height="30" rx="2" fill="#F5C542" />
    </svg>
  );
}
