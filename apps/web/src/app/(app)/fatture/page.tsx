import { FileText } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export default function FatturePage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Fatture</h1>
      <Card>
        <CardContent className="py-16 text-center">
          <FileText className="mx-auto size-12 text-muted-foreground/40" />
          <p className="mt-4 text-base font-medium">In costruzione</p>
          <p className="text-sm text-muted-foreground mt-1">Questa sezione sarà disponibile nella Fase 4.</p>
        </CardContent>
      </Card>
    </div>
  );
}
