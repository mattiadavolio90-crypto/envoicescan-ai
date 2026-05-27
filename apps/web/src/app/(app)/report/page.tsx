import { Receipt } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

export default function ReportPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold tracking-tight">Report</h1>
      <Card>
        <CardContent className="py-16 text-center">
          <Receipt className="mx-auto size-12 text-muted-foreground/40" />
          <p className="mt-4 text-base font-medium">In costruzione</p>
          <p className="text-sm text-muted-foreground mt-1">Questa sezione sarà disponibile nelle fasi successive.</p>
        </CardContent>
      </Card>
    </div>
  );
}
