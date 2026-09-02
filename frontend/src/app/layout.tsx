import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AlgoTradePro",
  description: "Stock scanner and threshold watchlist",
};

const THEME_INIT_SCRIPT = `
  try {
    var theme = localStorage.getItem("algotradepro-theme");
    document.documentElement.dataset.theme = theme === "light" ? "light" : "dark";
  } catch (e) {}
`;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased" data-theme="dark" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
