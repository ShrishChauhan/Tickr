import type { OHLCBar } from "@/lib/api";

interface Props {
  ohlc: OHLCBar[];
  isUp: boolean;
  width?: number;
  height?: number;
}

function toPoints(values: number[], w: number, h: number): string {
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  return values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * w;
      const y = h - ((v - min) / range) * h;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export default function Sparkline({ ohlc, isUp, width = 96, height = 28 }: Props) {
  if (!ohlc || ohlc.length < 2) {
    // Equities via Finnhub currently return an empty ohlc[] — degrade to a muted flat
    // line rather than showing nothing or an error.
    return (
      <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="var(--color-text-muted)"
          strokeWidth="1"
          strokeDasharray="2,3"
        />
      </svg>
    );
  }

  const closes = ohlc.map((b) => b.close);
  const color = isUp ? "#22c55e" : "#ef4444"; // matches --color-data-green / --color-data-red

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} fill="none" aria-hidden="true">
      <polyline
        points={toPoints(closes, width, height - 4)}
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}
