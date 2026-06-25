import styles from "./MoversRow.module.css";

interface Mover {
  symbol: string;
  name: string;
  price: string;
  change: string;
  dir: "up" | "down";
  sparkline: number[];
}

const MOVERS: Mover[] = [
  {
    symbol: "NVDA",
    name: "NVIDIA Corp",
    price: "127.84",
    change: "+4.32%",
    dir: "up",
    sparkline: [20, 22, 18, 25, 22, 30, 28, 35, 33, 40],
  },
  {
    symbol: "AAPL",
    name: "Apple Inc",
    price: "213.49",
    change: "+1.87%",
    dir: "up",
    sparkline: [30, 28, 32, 29, 31, 27, 32, 30, 33, 36],
  },
  {
    symbol: "TSLA",
    name: "Tesla Inc",
    price: "247.31",
    change: "-2.14%",
    dir: "down",
    sparkline: [40, 38, 42, 36, 38, 32, 34, 28, 30, 24],
  },
  {
    symbol: "AMZN",
    name: "Amazon.com",
    price: "198.75",
    change: "+0.93%",
    dir: "up",
    sparkline: [28, 26, 30, 27, 29, 26, 30, 27, 31, 33],
  },
  {
    symbol: "META",
    name: "Meta Platforms",
    price: "522.60",
    change: "-1.48%",
    dir: "down",
    sparkline: [38, 36, 40, 34, 36, 30, 32, 26, 28, 22],
  },
];

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

function MoverCard({ m }: { m: Mover }) {
  const isUp = m.dir === "up";
  const changeColor = isUp
    ? "var(--color-data-green)"
    : "var(--color-data-red)";
  const sparkColor = isUp ? "#22c55e" : "#ef4444";
  const borderColor = isUp
    ? "rgba(34, 197, 94, 0.2)"
    : "rgba(239, 68, 68, 0.2)";

  return (
    <div
      className={styles.card}
      style={{ borderColor }}
    >
      <div className={styles.cardTop}>
        <span className={styles.symbol}>{m.symbol}</span>
        <svg
          width="60"
          height="24"
          viewBox="0 0 60 24"
          fill="none"
          aria-hidden="true"
        >
          <polyline
            points={toPoints(m.sparkline, 60, 22)}
            stroke={sparkColor}
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            fill="none"
          />
        </svg>
      </div>
      <div className={styles.name}>{m.name}</div>
      <div className={styles.cardBottom}>
        <span className={styles.price}>{m.price}</span>
        <span className={styles.change} style={{ color: changeColor }}>
          {m.change}
        </span>
      </div>
    </div>
  );
}

export default function MoversRow() {
  return (
    <section className={styles.section} aria-label="Today's Movers — sample data">
      <div className={styles.header}>
        <span className={styles.title}>Today&rsquo;s Movers</span>
        <span className={styles.badge}>Sample Data</span>
      </div>
      <div className={styles.row}>
        {MOVERS.map((m) => (
          <MoverCard key={m.symbol} m={m} />
        ))}
      </div>
    </section>
  );
}
