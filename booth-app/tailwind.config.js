/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        cream: "#F5F0EB",
        burgundy: "#6B1D2A",
      },
      fontFamily: {
        display: ['"Bodoni Moda"', "serif"],
        body: ["Inter", "sans-serif"],
        script: ['"Dancing Script"', "cursive"],
      },
    },
  },
  plugins: [],
};
