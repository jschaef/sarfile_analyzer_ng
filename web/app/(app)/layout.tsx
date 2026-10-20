import { AppHeader } from "@/components/app-header";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <>
      <AppHeader />
      <main className="mx-auto w-full max-w-screen-2xl flex-1 px-4 py-6">{children}</main>
    </>
  );
}
