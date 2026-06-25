import styles from "./SearchBar.module.css";

// Search functionality wired in Phase 3b
export default function SearchBar() {
  return (
    <div className={styles.bar} role="search" aria-label="Stock search (coming soon)">
      <span className={styles.icon} aria-hidden="true">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <circle cx="6.5" cy="6.5" r="5" stroke="currentColor" strokeWidth="1.5" />
          <line
            x1="10.5"
            y1="10.5"
            x2="14"
            y2="14"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
          />
        </svg>
      </span>
      <span className={styles.placeholder}>Search any stock&hellip;</span>
      <span className={styles.kbd}>
        <kbd>⌘K</kbd>
      </span>
    </div>
  );
}
