import { Header } from "./Header";

interface AppLayoutProps {
  children: React.ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  return (
    <div className="min-h-screen bg-background">
      <Header />
      <main className="mx-auto w-full max-w-[110rem] px-4 py-8 sm:px-6 lg:px-8 xl:py-10 2xl:px-10">
        {children}
      </main>
    </div>
  );
}
