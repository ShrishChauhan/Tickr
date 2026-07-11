import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import styles from "./page.module.css";

export default async function AccountPage() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();

  if (!data.user) {
    redirect("/login");
  }

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <h1 className={styles.title}>Account</h1>
        <p className={styles.text}>Signed in as {data.user.email}</p>
      </div>
    </main>
  );
}
