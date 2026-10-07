/**
 * src/today/GeneratePlanButton.tsx
 * The control that starts a plan generate. Screens pass busy and
 * onPress; this only draws the button.
 */

import { ActivityIndicator, Pressable, StyleSheet, Text } from "react-native";

import { colors } from "../ui/AuthForm";

export function GeneratePlanButton({ label, busy, onPress }: {
  label: string;
  busy: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={busy}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [styles.button, (pressed || busy) && styles.pressed]}
    >
      {busy ? <ActivityIndicator color="#fff" /> : <Text style={styles.text}>{label}</Text>}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: { backgroundColor: colors.accent, borderRadius: 12, paddingVertical: 14, alignItems: "center", marginTop: 4 },
  pressed: { opacity: 0.7 },
  text: { color: "#fff", fontSize: 16, fontWeight: "700" },
});
