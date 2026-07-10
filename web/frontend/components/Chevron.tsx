interface ChevronProps {
  size?: number;
  className?: string;
  fill?: string;
  stroke?: string;
}

export default function Chevron({
  size = 24,
  className = "",
  fill = "url(#btrlGrad)",
  stroke = fill,
}: ChevronProps) {
  return (
    <svg
      width={size}
      height={(size * 3) / 4}
      viewBox="0 0 480 480"
      preserveAspectRatio="xMidYMid meet"
      shapeRendering="geometricPrecision"
      className={className}
      aria-hidden="true"
    >
      <defs>
        <linearGradient id="btrlGrad" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0%" stopColor="#734e9e" suppressHydrationWarning />
          <stop offset="100%" stopColor="#d09846" suppressHydrationWarning />
        </linearGradient>
      </defs>
      <path
        d="M60 80 L240 80 L460 240 L240 400 L60 400 L280 240 Z"
        fill={fill}
        stroke={stroke}
        strokeWidth={16}
        strokeLinejoin="round"
        strokeLinecap="round"
        paintOrder="stroke fill"
      />
    </svg>
  );
}