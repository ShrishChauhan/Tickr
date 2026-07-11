import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import CompleteProfileForm from "@/components/profile/CompleteProfileForm";
import styles from "./page.module.css";

export default async function CompleteProfilePage({
  searchParams,
}: {
  searchParams: Promise<{ next?: string }>;
}) {
  const { next } = await searchParams;
  const redirectTo = next ?? "/";

  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  if (!data.user) {
    redirect("/login");
  }

  const { data: profile } = await supabase
    .from("profiles")
    .select("username, first_name, last_name, profile_completed")
    .eq("id", data.user.id)
    .single();

  if (!profile || profile.profile_completed) {
    redirect(redirectTo);
  }

  return (
    <main className={styles.page}>
      <div className={styles.container}>
        <h1 className={styles.title}>Complete your profile</h1>
        <CompleteProfileForm
          initialUsername={profile.username}
          initialFirstName={profile.first_name ?? ""}
          initialLastName={profile.last_name ?? ""}
          redirectTo={redirectTo}
        />
      </div>
    </main>
  );
}
