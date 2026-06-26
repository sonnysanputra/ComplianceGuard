"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { Spinner } from "@/components/ui";

export default function WorkspaceRedirect() {
  const router = useRouter();
  useEffect(() => {
    api.cases()
      .then((c) => router.replace(c.length ? `/case/${encodeURIComponent(c[0].case_id)}` : "/cases"))
      .catch(() => router.replace("/cases"));
  }, [router]);
  return <Spinner label="opening the latest case…" />;
}
