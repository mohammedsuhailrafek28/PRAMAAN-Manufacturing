import { Suspense } from "react";
import { DataProvider } from "@/dash/data";
import { AskWidget } from "@/ask/AskWidget";
import { GateBanner, MotorBar, SideNav } from "@/dash/ui";

export const metadata = { title: "PRAMAAN | Dashboard" };

export default function DashboardLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <>
      <link rel="preconnect" href="https://fonts.googleapis.com" />
      <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Unbounded:wght@400;500;600&family=Hanken+Grotesk:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" />
      <Suspense fallback={null}>
        <DataProvider>
          <div className="dash">
            <SideNav />
            <div className="main">
              <MotorBar />
              <main className="content">
                <GateBanner />
                {children}
              </main>
            </div>
          </div>
          <AskWidget />
        </DataProvider>
      </Suspense>
    </>
  );
}
