import "@fontsource/public-sans/400.css";
import "@fontsource/public-sans/500.css";
import "@fontsource/public-sans/600.css";
import "@fontsource/literata/500.css";
import "@fontsource/literata/600.css";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { globalCss } from "./globalStyles";

const style = document.createElement("style");
style.textContent = globalCss;
document.head.appendChild(style);
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
