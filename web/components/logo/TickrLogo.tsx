import styles from "./TickrLogo.module.css";

interface TickrLogoProps {
  className?: string;
}

// Font size is controlled by the parent wrapper — this component inherits it.
export default function TickrLogo({ className }: TickrLogoProps) {
  return (
    <span
      className={`${styles.logo} ${className ?? ""}`}
      aria-label="Tickr"
    >
      <span className={styles.letter}>T</span>

      {/* Two arrows replace the "I" */}
      <span className={styles.arrowGap} aria-hidden="true">
        <svg
          viewBox="0 0 26 56"
          height="1em"
          width="0.46em"
          style={{ overflow: "visible", display: "block", flexShrink: 0 }}
        >
          {/* Green up arrow — sits higher and to the right */}
          <g
            style={{
              filter:
                "drop-shadow(0 0 2px #2bff88) drop-shadow(0 0 6px rgba(43,255,136,0.55))",
            }}
          >
            <line
              x1="18"
              y1="42"
              x2="18"
              y2="12"
              stroke="#2bff88"
              strokeWidth="4"
              strokeLinecap="round"
            />
            <polyline
              points="12,22 18,10 24,22"
              stroke="#2bff88"
              strokeWidth="4"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </g>

          {/* Red down arrow — sits lower and to the left */}
          <g
            style={{
              filter:
                "drop-shadow(0 0 2px #ff4060) drop-shadow(0 0 6px rgba(255,64,96,0.55))",
            }}
          >
            <line
              x1="8"
              y1="14"
              x2="8"
              y2="44"
              stroke="#ff4060"
              strokeWidth="4"
              strokeLinecap="round"
            />
            <polyline
              points="2,34 8,46 14,34"
              stroke="#ff4060"
              strokeWidth="4"
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </g>
        </svg>
      </span>

      <span className={styles.letter}>CKR</span>
    </span>
  );
}
