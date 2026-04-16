import typography from "@tailwindcss/typography";

/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  plugins: [typography],
  theme: {
    extend: {
      keyframes: {
        "glow-pulse": {
          "0%, 100%": {
            transform: "scale(1)",
            opacity: "0.85",
            filter: "brightness(1)",
          },
          "50%": {
            transform: "scale(1.15)",
            opacity: "1",
            filter: "brightness(1.3)",
          },
        },
        slideIn: {
          "0%": { opacity: "0", transform: "translateY(-6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "spin-slow": "spin 3s linear infinite",
        "glow-pulse": "glow-pulse 4s ease-in-out infinite",
      },
    },
  },
};
