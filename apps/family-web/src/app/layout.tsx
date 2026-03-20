import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Computer — Family",
  description: "Household intelligence surfaces: history, approvals, state",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body style={{ margin: 0, background: "#fafafa", color: "#1a1a1a" }}>{children}</body>
    </html>
  );
}
