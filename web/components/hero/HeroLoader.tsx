"use client";

// Client boundary needed so that ssr:false works for the animated hero
import dynamic from "next/dynamic";

const HeroSection = dynamic(() => import("./HeroSection"), {
  ssr: false,
  loading: () => (
    <div style={{ minHeight: "100svh", background: "#04070a" }} />
  ),
});

export default function HeroLoader() {
  return <HeroSection />;
}
