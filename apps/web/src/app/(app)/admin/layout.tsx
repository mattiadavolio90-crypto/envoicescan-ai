import { redirect } from "next/navigation";
import { getCurrentUser } from "@/lib/auth";
import { AdminMenu } from "@/components/admin/admin-menu";

export default async function AdminLayout({ children }: { children: React.ReactNode }) {
  const user = await getCurrentUser();
  if (!user) redirect("/login");
  if (!user.is_admin) redirect("/dashboard");
  return (
    <div className="space-y-6">
      <AdminMenu />
      {children}
    </div>
  );
}
