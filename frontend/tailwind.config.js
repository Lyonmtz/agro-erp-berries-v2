/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        berry: {
          50: "#fdf2f4",
          100: "#fce7eb",
          600: "#c81e4b",
          700: "#a5153c",
          900: "#630d26",
        },
      },
    },
  },
  plugins: [],
};
