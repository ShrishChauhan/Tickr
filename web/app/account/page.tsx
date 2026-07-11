import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import ProfileEditForm from "@/components/profile/ProfileEditForm";
import styles from "./page.module.css";

export default async function AccountPage() {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();

  if (!data.user) {
    redirect("/login");
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select("username, first_name, last_name, display_name, bio")
    .eq("id", data.user.id)
    .single();

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <h1 className={styles.title}>Account</h1>
        <p className={styles.text}>Signed in as {data.user.email}</p>
        <ProfileEditForm
          initialUsername={profile?.username ?? ""}
          initialFirstName={profile?.first_name ?? ""}
          initialLastName={profile?.last_name ?? ""}
          initialDisplayName={profile?.display_name ?? ""}
          initialBio={profile?.bio ?? ""}
        />
      </div>
    </main>
  );
}
