import { redirect } from "next/navigation";
import Link from "next/link";
import { getCurrentUser } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { ChevronLeft } from "lucide-react";
import { QualitaAiClient } from "./qualita-ai-client";

export default async function QualitaAiPage() {
  const user = await getCurrentUser();
  if (!user || !user.is_admin) redirect("/dashboard");
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link href="/admin"><ChevronLeft className="size-4 mr-1" /> Admin</Link>
        </Button>
        <h1 className="text-2xl font-bold tracking-tight">Qualità AI</h1>
      </div>
      <QualitaAiClient />
    </div>
  );
}
