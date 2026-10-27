import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "PRAMAAN | Manufacturing Intelligence",
  description: "Evidence-led manufacturing traceability workspace",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
