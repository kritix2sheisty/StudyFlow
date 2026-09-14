/**
 * src/ui/AuthShell.tsx
 * The frame around the sign-in and create-account screens: the app
 * name, a title, the form, a link to the other screen, and the server
 * address in small print so a student can see at a glance which laptop
 * the phone is talking to.
 */

import { Link } from "expo-router";
import type { ReactNode } from "react";
import { KeyboardAvoidingView, Platform, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { baseUrl } from "../auth";
import { colors } from "./AuthForm";

export interface AuthShellProps {
  title: string;
  children: ReactNode;
  footerText: string;
  footerLink: { label: string; href: "/sign-in" | "/register" };
}

export function AuthShell({ title, children, footerText, footerLink }: AuthShellProps) {
  return (
    <SafeAreaView style={styles.page}>
      <KeyboardAvoidingView style={styles.body} behavior={Platform.OS === "ios" ? "padding" : undefined}>
        <Text style={styles.brand}>StudyFlow</Text>
        <Text style={styles.title}>{title}</Text>
        {children}
        <View style={styles.footer}>
          <Text style={styles.footerText}>{footerText} </Text>
          <Link href={footerLink.href} replace style={styles.footerLink}>
            {footerLink.label}
          </Link>
        </View>
      </KeyboardAvoidingView>
      <Text style={styles.server}>Server: {baseUrl || "not set (see mobile/.env.example)"}</Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.page },
  body: { flex: 1, justifyContent: "center", paddingHorizontal: 28, gap: 12 },
  brand: { color: colors.accent, fontSize: 14, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },
  title: { color: colors.ink, fontSize: 28, fontWeight: "700", marginBottom: 8 },
  footer: { flexDirection: "row", justifyContent: "center", marginTop: 16 },
  footerText: { color: colors.muted, fontSize: 14 },
  footerLink: { color: colors.accent, fontSize: 14, fontWeight: "600" },
  server: { color: colors.muted, fontSize: 12, textAlign: "center", paddingVertical: 12 },
});
