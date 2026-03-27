import React from 'react';

interface SalesSuitLogoProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

const sizes = {
  sm: { width: 160, height: 48 },
  md: { width: 240, height: 72 },
  lg: { width: 320, height: 96 },
};

export const SalesSuitLogo = React.memo(function SalesSuitLogo({
  size = 'md',
  className = '',
}: SalesSuitLogoProps) {
  const { width, height } = sizes[size];

  return (
    <svg
      width={width}
      height={height}
      viewBox="0 0 320 96"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      role="img"
      aria-label="Honeywell Sales Suit Logo"
    >
      {/* Icon: Hexagon with chart bars */}
      <g transform="translate(12, 8)">
        {/* Outer hexagon */}
        <path
          d="M40 4L70.6 21.7V57.1L40 74.8L9.4 57.1V21.7L40 4Z"
          fill="#D32F2F"
          opacity="0.1"
          stroke="#D32F2F"
          strokeWidth="2"
        />
        {/* Inner bars (chart/analytics symbol) */}
        <rect x="22" y="46" width="8" height="16" rx="2" fill="#D32F2F" opacity="0.6" />
        <rect x="34" y="34" width="8" height="28" rx="2" fill="#D32F2F" opacity="0.8" />
        <rect x="46" y="24" width="8" height="38" rx="2" fill="#D32F2F" />
        {/* Upward arrow */}
        <path
          d="M40 18L46 26H34L40 18Z"
          fill="#B71C1C"
        />
      </g>

      {/* Text: HONEYWELL */}
      <text
        x="96"
        y="36"
        fontFamily="'Exo 2', system-ui, sans-serif"
        fontSize="18"
        fontWeight="700"
        fill="#1a1a1a"
        letterSpacing="3"
      >
        HONEYWELL
      </text>

      {/* Text: Sales Suit */}
      <text
        x="96"
        y="58"
        fontFamily="'Exo 2', system-ui, sans-serif"
        fontSize="22"
        fontWeight="600"
        fill="#D32F2F"
        letterSpacing="1"
      >
        Sales Suit
      </text>

      {/* Divider line */}
      <line x1="96" y1="66" x2="260" y2="66" stroke="#D32F2F" strokeWidth="2" opacity="0.3" />

      {/* Subtitle */}
      <text
        x="96"
        y="82"
        fontFamily="'Roboto Mono', monospace"
        fontSize="9"
        fontWeight="400"
        fill="#999"
        letterSpacing="2"
      >
        SPARE PARTS MANAGEMENT
      </text>
    </svg>
  );
});
