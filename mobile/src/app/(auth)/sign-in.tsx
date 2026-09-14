/**
 * src/app/(auth)/sign-in.tsx
 * Sign in with email and password. On success the session becomes
 * signed-in and the root layout switches to the app on its own.
 * Failures show the API's own message.
 */

import { session } from "../../auth";
import { AuthForm } from "../../ui/AuthForm";
import { AuthShell } from "../../ui/AuthShell";

export default function SignInScreen() {
  return (
    <AuthShell
      title="Sign in"
      footerText="New here?"
      footerLink={{ label: "Create an account", href: "/register" }}
    >
      <AuthForm submitLabel="Sign in" onSubmit={(email, password) => session.signIn(email, password)} />
    </AuthShell>
  );
}
