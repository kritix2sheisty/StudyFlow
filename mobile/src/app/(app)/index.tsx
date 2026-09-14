/**
 * src/app/(app)/index.tsx
 * Home for M1: who is signed in and a way out. M2 replaces the
 * placeholder text with today's sessions.
 */

import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { session } from "../../auth";
import { useSession } from "../../auth/useSession";
import { colors } from "../../ui/AuthForm";

export default function HomeScreen() {
  const { email, user } = useSession();
  return (
    <SafeAreaView style={styles.page}>
      <View style={styles.header}>
        <Text style={styles.brand}>StudyFlow</Text>
        <Pressable onPress={() => void session.signOut()} accessibilityRole="button" hitSlop={8}>
          <Text style={styles.logout}>Log out</Text>
        </Pressable>
      </View>
      <View style={styles.body}>
        <Text style={styles.signedIn}>Signed in as</Text>
        <Text style={styles.email}>{user?.email ?? email}</Text>
        <Text style={styles.placeholder}>Today's study sessions will appear here.</Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.page },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 24, paddingVertical: 16 },
  brand: { color: colors.accent, fontSize: 14, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },
  logout: { color: colors.accent, fontSize: 16, fontWeight: "600" },
  body: { flex: 1, justifyContent: "center", alignItems: "center", paddingHorizontal: 28, gap: 8 },
  signedIn: { color: colors.muted, fontSize: 14 },
  email: { color: colors.ink, fontSize: 20, fontWeight: "600" },
  placeholder: { color: colors.muted, fontSize: 14, marginTop: 24, textAlign: "center" },
});
