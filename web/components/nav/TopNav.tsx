"use client";

import { useEffect } from "react";
import { motion, useAnimation } from "framer-motion";
import TickrLogo from "@/components/logo/TickrLogo";
import styles from "./TopNav.module.css";

interface TopNavProps {
  instant: boolean;
}

export default function TopNav({ instant }: TopNavProps) {
  const controls = useAnimation();

  useEffect(() => {
    if (instant) {
      controls.set({ opacity: 1 });
    } else {
      controls.start({ opacity: 1, transition: { duration: 0.4, delay: 5.85 } });
    }
  }, [instant, controls]);

  return (
    <motion.nav
      className={`${styles.nav} ${instant ? styles.navSolid : ""}`}
      role="navigation"
      aria-label="Main navigation"
      animate={controls}
      initial={{ opacity: 0 }}
    >
      <span style={{ fontSize: "1.5rem" }}>
        <TickrLogo />
      </span>

      <div className={styles.links}>
        {/* Links wire up in Phase 3b */}
        <a href="#" className={styles.link}>
          Search
        </a>
        <a href="#" className={styles.link}>
          About
        </a>
      </div>
    </motion.nav>
  );
}
