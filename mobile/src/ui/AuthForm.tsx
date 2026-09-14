/**
 * src/ui/AuthForm.tsx
 * The one form both auth screens use: email, password, an optional
 * confirm field, a submit button that goes busy while the call runs,
 * and the failure message shown in the API's own words underneath.
 * The screen owns what submit does; this owns how it looks.
 */

import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { errorMessage } from "./messages";

export interface AuthFormProps {
  submitLabel: string;
  confirm?: boolean;
  onSubmit: (email: string, password: string) => Promise<void>;
}

export const PASSWORDS_DIFFER = "The two passwords are not the same.";

export function AuthForm({ submitLabel, confirm = false, onSubmit }: AuthFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [again, setAgain] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (busy) return;
    if (confirm && password !== again) {
      setError(PASSWORDS_DIFFER);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSubmit(email.trim(), password);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <View style={styles.form}>
      <TextInput
        style={styles.input}
        placeholder="Email"
        placeholderTextColor={colors.muted}
        autoCapitalize="none"
        autoCorrect={false}
        keyboardType="email-address"
        textContentType="emailAddress"
        value={email}
        onChangeText={setEmail}
        editable={!busy}
      />
      <TextInput
        style={styles.input}
        placeholder="Password"
        placeholderTextColor={colors.muted}
        secureTextEntry
        textContentType={confirm ? "newPassword" : "password"}
        value={password}
        onChangeText={setPassword}
        editable={!busy}
        onSubmitEditing={confirm ? undefined : submit}
      />
      {confirm && (
        <TextInput
          style={styles.input}
          placeholder="Password again"
          placeholderTextColor={colors.muted}
          secureTextEntry
          textContentType="newPassword"
          value={again}
          onChangeText={setAgain}
          editable={!busy}
          onSubmitEditing={submit}
        />
      )}
      {error && (
        <Text style={styles.error} accessibilityRole="alert">
          {error}
        </Text>
      )}
      <Pressable
        style={({ pressed }) => [styles.button, (pressed || busy) && styles.buttonPressed]}
        onPress={submit}
        disabled={busy}
        accessibilityRole="button"
      >
        {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.buttonText}>{submitLabel}</Text>}
      </Pressable>
    </View>
  );
}

export const colors = {
  ink: "#1c1c1e",
  muted: "#8e8e93",
  accent: "#208aef",
  danger: "#c0392b",
  field: "#f2f2f7",
  page: "#ffffff",
};

const styles = StyleSheet.create({
  form: { gap: 12 },
  input: {
    backgroundColor: colors.field,
    borderRadius: 10,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 16,
    color: colors.ink,
  },
  error: { color: colors.danger, fontSize: 14 },
  button: {
    backgroundColor: colors.accent,
    borderRadius: 10,
    paddingVertical: 14,
    alignItems: "center",
    marginTop: 4,
  },
  buttonPressed: { opacity: 0.7 },
  buttonText: { color: "#fff", fontSize: 16, fontWeight: "600" },
});
