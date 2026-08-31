"use client";

import { useRouter } from "next/navigation";
import Shell from "@/components/Shell";
import EmployeeForm from "@/components/EmployeeForm";

export default function NewEmployeePage() {
  const router = useRouter();
  return (
    <Shell>
      <h1 className="mb-6 text-2xl font-bold">إضافة موظف جديد</h1>
      <EmployeeForm onSaved={(emp) => router.replace(`/employees/${emp.id}`)} />
    </Shell>
  );
}
