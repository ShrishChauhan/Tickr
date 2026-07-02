"use client";

import { useState, useEffect } from "react";
import { motion, useAnimation } from "framer-motion";
import TickrLogo from "@/components/logo/TickrLogo";
import TickerLine from "./TickerLine";
import TopNav from "@/components/nav/TopNav";
import SearchBar from "./SearchBar";
import MoversRow from "./MoversRow";
import Typewriter from "./Typewriter";
import styles from "./HeroSection.module.css";

const EASE = [0.22, 1, 0.36, 1] as const;

export default function HeroSection() {
  const [instant, setInstant] = useState(false);

  const logoCtrl = useAnimation();
  const taglineCtrl = useAnimation();
  const searchCtrl = useAnimation();
  const moversCtrl = useAnimation();

  useEffect(() => {
    if (instant) {
      // Jump all elements to their final visible state immediately
      logoCtrl.set({ opacity: 1, scale: 1 });
      taglineCtrl.set({ opacity: 1, y: 0 });
      searchCtrl.set({ opacity: 1, y: 0 });
      moversCtrl.set({ opacity: 1, y: 0 });
    } else {
      // Start the natural staggered animation sequence
      logoCtrl.start({ opacity: 1, scale: 1, transition: { duration: 0.55, delay: 3.0, ease: EASE } });
      taglineCtrl.start({ opacity: 1, y: 0, transition: { duration: 0.55, delay: 6.15, ease: EASE } });
      searchCtrl.start({ opacity: 1, y: 0, transition: { duration: 0.55, delay: 6.0, ease: EASE } });
      moversCtrl.start({ opacity: 1, y: 0, transition: { duration: 0.55, delay: 6.35, ease: EASE } });
    }
  }, [instant, logoCtrl, taglineCtrl, searchCtrl, moversCtrl]);

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      setInstant(true);
    }
  }, []);

  useEffect(() => {
    const skip = () => setInstant(true);
    window.addEventListener("click", skip, { once: true, passive: true });
    window.addEventListener("keydown", skip, { once: true });
    document.addEventListener("scroll", skip, { once: true, passive: true });
    const t = setTimeout(skip, 8000);
    return () => clearTimeout(t);
  }, []);

  return (
    <div className={styles.hero}>
      <TickerLine instant={instant} />

      <TopNav instant={instant} />

      <div className={styles.content}>
        <motion.div
          className={styles.logoWrap}
          animate={logoCtrl}
          initial={{ opacity: 0, scale: 0.88 }}
        >
          <TickrLogo />
        </motion.div>

        <motion.p
          className={styles.tagline}
          animate={taglineCtrl}
          initial={{ opacity: 0, y: 18 }}
        >
          <Typewriter
            text="AI-Powered Equity Research Terminal"
            charDelay={50}
            startDelay={6150}
            instant={instant}
          />
        </motion.p>

        <motion.div animate={searchCtrl} initial={{ opacity: 0, y: 18 }}>
          <SearchBar />
        </motion.div>
      </div>

      <motion.div
        className={styles.moversWrap}
        animate={moversCtrl}
        initial={{ opacity: 0, y: 18 }}
      >
        <MoversRow />
      </motion.div>
    </div>
  );
}
