import { redirect } from "next/navigation";
import Link from "next/link";
import { getCurrentUser } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { ChevronLeft } from "lucide-react";
import { SistemaClient } from "./sistema-client";

export default async function SistemaPage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" nativeButton={false} render={<Link href="/admin" />}>
          <ChevronLeft className="size-4 mr-1" /> Admin
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">Sistema & Salute</h1>
      </div>
      <SistemaClient />
    </div>
  );
}
