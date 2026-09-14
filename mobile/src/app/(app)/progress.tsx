/**
 * src/app/(app)/progress.tsx
 * Progress. The engine's numbers, shown, not recomputed: hours done
 * against hours required per assignment, with the plan's risk word
 * (CRITICAL / HIGH / MODERATE / LOW) as the plan shows it; totals on
 * top; assignments marked complete listed at the end. Refreshes on
 * pull and whenever it opens.
 */

import { router } from "expo-router";
import { useCallback, useEffect } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { progress, useProgress } from "../../progress";
import type { ProgressAssignment } from "../../progress/store";
import { colors } from "../../ui/AuthForm";

const RISK_COLOR: Record<string, string> = {
  CRITICAL: "#c0392b",
  HIGH: "#d35400",
  MODERATE: "#b7791f",
  LOW: "#1f7a3a",
};

function hours(n: number): string {
  return Number.isInteger(n) ? `${n}h` : `${n.toFixed(1)}h`;
}

function Row({ a }: { a: ProgressAssignment }) {
  const pct = Math.min(100, Math.max(0, a.done_percent));
  return (
    <View style={styles.row}>
      <View style={styles.rowTop}>
        <Text style={styles.name} numberOfLines={2}>{a.name}</Text>
        <Text style={[styles.risk, { color: RISK_COLOR[a.risk] ?? colors.muted }]}>{a.risk}</Text>
      </View>
      <Text style={styles.meta}>{a.subject ? `${a.subject} · ` : ""}due {a.due_date}</Text>
      <View style={styles.bar}>
        <View style={[styles.barFill, { width: `${pct}%` }]} />
      </View>
      <Text style={styles.hours}>{hours(a.done_hours)} of {hours(a.required_hours)} done · {pct}%</Text>
    </View>
  );
}

export default function ProgressScreen() {
  const { status, progress: p, message } = useProgress();
  const refresh = useCallback(() => { void progress.load(); }, []);
  useEffect(() => { refresh(); }, [refresh]);

  return (
    <SafeAreaView style={styles.page}>
      <View style={styles.top}>
        <Pressable onPress={() => router.back()} accessibilityRole="button" hitSlop={8}>
          <Text style={styles.back}>‹ Today</Text>
        </Pressable>
      </View>
      <Text style={styles.title}>Progress</Text>
      {message ? <Text style={styles.error} accessibilityRole="alert">{message}</Text> : null}

      <FlatList
        data={p?.assignments ?? []}
        keyExtractor={(a) => String(a.id)}
        renderItem={({ item }) => <Row a={item} />}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={status === "refreshing"} onRefresh={refresh} tintColor={colors.accent} />}
        ListHeaderComponent={p ? (
          <View style={styles.totals}>
            <View style={styles.total}><Text style={styles.totalNumber}>{hours(p.done_hours)}</Text><Text style={styles.totalLabel}>studied</Text></View>
            <View style={styles.total}><Text style={styles.totalNumber}>{p.sessions_completed}</Text><Text style={styles.totalLabel}>sessions</Text></View>
            <View style={styles.total}><Text style={styles.totalNumber}>{p.completed_count}</Text><Text style={styles.totalLabel}>finished</Text></View>
            {!p.fresh ? <Text style={styles.stale}>Your plan needs regenerating on your laptop; hours shown are from the assignments themselves.</Text> : null}
          </View>
        ) : null}
        ListEmptyComponent={
          status === "loading" ? <Text style={styles.muted}>Loading…</Text>
          : status === "error" ? <Text style={styles.muted}>Can't load progress. Pull down to try again.</Text>
          : <Text style={styles.muted}>No active assignments.</Text>
        }
        ListFooterComponent={p && p.completed.length ? (
          <View style={styles.completed}>
            <Text style={styles.completedTitle}>Completed</Text>
            {p.completed.map((name) => <Text key={name} style={styles.completedName}>✓ {name}</Text>)}
          </View>
        ) : null}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.page },
  top: { paddingHorizontal: 20, paddingTop: 12 },
  back: { color: colors.accent, fontSize: 16, fontWeight: "600" },
  title: { color: colors.ink, fontSize: 30, fontWeight: "700", paddingHorizontal: 24, paddingTop: 8, paddingBottom: 8 },
  error: { color: colors.danger, fontSize: 14, paddingHorizontal: 24, paddingBottom: 8 },
  list: { paddingHorizontal: 16, paddingBottom: 24, gap: 10 },
  totals: { flexDirection: "row", flexWrap: "wrap", gap: 10, marginBottom: 6 },
  total: { flex: 1, minWidth: 90, backgroundColor: colors.field, borderRadius: 14, padding: 14, alignItems: "center" },
  totalNumber: { color: colors.ink, fontSize: 24, fontWeight: "700", fontVariant: ["tabular-nums"] },
  totalLabel: { color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1, marginTop: 2 },
  stale: { width: "100%", color: "#8a5a00", fontSize: 13, backgroundColor: "#fff1cc", borderRadius: 10, padding: 10 },
  row: { backgroundColor: colors.field, borderRadius: 14, padding: 14, gap: 6 },
  rowTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 12 },
  name: { flex: 1, color: colors.ink, fontSize: 17, fontWeight: "600" },
  risk: { fontSize: 12, fontWeight: "700", letterSpacing: 1 },
  meta: { color: colors.muted, fontSize: 13 },
  bar: { height: 8, borderRadius: 999, backgroundColor: "#e5e5ea", overflow: "hidden" },
  barFill: { height: "100%", backgroundColor: colors.accent, borderRadius: 999 },
  hours: { color: colors.muted, fontSize: 13, fontVariant: ["tabular-nums"] },
  muted: { color: colors.muted, fontSize: 14, textAlign: "center", marginTop: 24 },
  completed: { marginTop: 16, gap: 6 },
  completedTitle: { color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1 },
  completedName: { color: colors.muted, fontSize: 15 },
});
