"use client";

import { useState, useEffect } from "react";
import styles from "./Typewriter.module.css";

interface TypewriterProps {
  text: string;
  charDelay?: number;
  startDelay?: number;
  instant: boolean;
}

export default function Typewriter({
  text,
  charDelay = 50,
  startDelay = 0,
  instant,
}: TypewriterProps) {
  const [count, setCount] = useState(instant ? text.length : 0);
  const [done, setDone] = useState(instant);

  useEffect(() => {
    if (instant) {
      setCount(text.length);
      setDone(true);
      return;
    }

    let localCount = 0;
    let tickId: ReturnType<typeof setTimeout>;

    const startId = setTimeout(() => {
      const tick = () => {
        localCount++;
        setCount(localCount);
        if (localCount < text.length) {
          tickId = setTimeout(tick, charDelay);
        } else {
          setDone(true);
        }
      };
      tick();
    }, startDelay);

    return () => {
      clearTimeout(startId);
      clearTimeout(tickId);
    };
    // text, charDelay, startDelay are call-site constants — intentionally excluded
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instant]);

  const cursorCls = instant
    ? styles.cursorGone
    : done
      ? styles.cursorFade
      : styles.cursor;

  return (
    <span className={styles.wrap}>
      {text.slice(0, count)}
      <span className={cursorCls} aria-hidden="true">|</span>
    </span>
  );
}
