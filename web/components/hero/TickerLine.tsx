"use client";

import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import styles from "./TickerLine.module.css";

const PATH =
  "M 0 660 L 90 610 L 110 630 L 200 565 L 220 590 L 330 510 L 355 535 L 460 460 L 485 490 L 600 400 L 625 428 L 740 355 L 760 380 L 880 300 L 905 325 L 1030 255 L 1055 278 L 1200 195";

const JITTER_PL = [0, 0.16, 0.12, 0.33, 0.27, 0.55, 0.5, 0.76, 0.71, 1.0];
const JITTER_T = [0, 0.14, 0.18, 0.37, 0.41, 0.6, 0.64, 0.82, 0.87, 1.0];

interface TickerLineProps {
  instant: boolean;
}

export default function TickerLine({ instant }: TickerLineProps) {
  const [dimmed, setDimmed] = useState(instant);

  useEffect(() => {
    if (instant) {
      setDimmed(true);
      return;
    }
    const t = setTimeout(() => setDimmed(true), 3500);
    return () => clearTimeout(t);
  }, [instant]);

  const pathAnimate = instant ? { pathLength: 1 } : { pathLength: JITTER_PL };
  const pathTransition = instant
    ? { duration: 0 }
    : { duration: 3.0, times: JITTER_T, ease: "easeInOut" as const };

  return (
    <svg
      className={styles.svg}
      viewBox="0 0 1200 700"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <filter id="ticker-halo" x="-15%" y="-15%" width="130%" height="130%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="9" />
        </filter>
        <filter id="ticker-mid" x="-8%" y="-8%" width="116%" height="116%">
          <feGaussianBlur in="SourceGraphic" stdDeviation="3.5" />
        </filter>
      </defs>

      <motion.g
        animate={{ opacity: dimmed ? 0.22 : 1 }}
        transition={{ duration: instant ? 0 : 1.0 }}
      >
        {/* Wide soft halo */}
        <motion.path
          d={PATH}
          stroke="#2bff88"
          strokeWidth={22}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
          filter="url(#ticker-halo)"
          style={{ opacity: 0.18 }}
          initial={{ pathLength: instant ? 1 : 0 }}
          animate={pathAnimate}
          transition={pathTransition}
        />
        {/* Medium glow */}
        <motion.path
          d={PATH}
          stroke="#2bff88"
          strokeWidth={8}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
          filter="url(#ticker-mid)"
          style={{ opacity: 0.42 }}
          initial={{ pathLength: instant ? 1 : 0 }}
          animate={pathAnimate}
          transition={pathTransition}
        />
        {/* Sharp bright core */}
        <motion.path
          d={PATH}
          stroke="#2bff88"
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          fill="none"
          initial={{ pathLength: instant ? 1 : 0 }}
          animate={pathAnimate}
          transition={pathTransition}
        />
      </motion.g>
    </svg>
  );
}
