/**
 * src/app/(auth)/register.tsx
 * Create an account: email, a password of at least 8 characters typed
 * twice. The session registers and then signs in, so the student lands
 * in the app straight away.
 */

import { session } from "../../auth";
import { AuthForm } from "../../ui/AuthForm";
import { AuthShell } from "../../ui/AuthShell";

export default function RegisterScreen() {
  return (
    <AuthShell
      title="Create an account"
      footerText="Already have one?"
      footerLink={{ label: "Sign in", href: "/sign-in" }}
    >
      <AuthForm submitLabel="Create account" confirm onSubmit={(email, password) => session.register(email, password)} />
    </AuthShell>
  );
}
