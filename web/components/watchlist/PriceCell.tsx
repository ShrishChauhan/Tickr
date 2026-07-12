"use client";

import type { WatchlistPriceEntry } from "@/lib/hooks/useWatchlistPrices";
import { fmtPrice, fmtChangePct } from "@/lib/format";
import Sparkline from "./Sparkline";
import ExplainButton from "./ExplainButton";
import styles from "./PriceCell.module.css";

interface Props {
  entry: WatchlistPriceEntry | undefined;
}

export default function PriceCell({ entry }: Props) {
  if (!entry || entry.status === "loading") {
    return (
      <div className={styles.cell}>
        <span className={styles.skeletonPrice} aria-busy="true" />
        <span className={styles.skeletonSpark} aria-busy="true" />
      </div>
    );
  }

  if (entry.status === "error") {
    return (
      <div className={styles.cell}>
        <span className={styles.muted}>—</span>
      </div>
    );
  }

  const { current_price, change_24h_pct, currency, ohlc } = entry.data;
  const isUp = (change_24h_pct ?? 0) >= 0;

  return (
    <div className={styles.cell}>
      <div className={styles.priceCol}>
        <span className={styles.price}>{fmtPrice(current_price, currency)}</span>
        <span className={`${styles.change} ${isUp ? styles.changeUp : styles.changeDown}`}>
          {fmtChangePct(change_24h_pct)}
        </span>
      </div>
      <Sparkline ohlc={ohlc} isUp={isUp} />
      {current_price != null && (
        <ExplainButton
          ticker={entry.data.ticker}
          assetType={entry.data.asset_type}
          currentPrice={current_price}
          changePct={change_24h_pct}
        />
      )}
    </div>
  );
}
