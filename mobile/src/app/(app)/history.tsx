/**
 * src/app/(app)/history.tsx
 * History. Every study session the student recorded, grouped by day,
 * newest first, each as "Subject — minutes" with the assignment under
 * it: the evidence that they followed their plan. Seven days by
 * default, with a switch to thirty. Refreshes on pull and on open.
 */

import { router } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { history, useHistory } from "../../history";
import { DayGroup, formatMinutes, groupByDay, HistorySession } from "../../history/view";
import { clock12 } from "../../today/view";
import { colors } from "../../ui/AuthForm";

type Row = { kind: "day"; group: DayGroup } | { kind: "session"; session: HistorySession };

function rowsOf(groups: DayGroup[]): Row[] {
  const rows: Row[] = [];
  for (const group of groups) {
    rows.push({ kind: "day", group });
    for (const session of group.sessions) rows.push({ kind: "session", session });
  }
  return rows;
}

export default function HistoryScreen() {
  const { status, history: h, message } = useHistory();
  const [days, setDays] = useState(7);
  const refresh = useCallback(() => { void history.load(days); }, [days]);
  useEffect(() => { refresh(); }, [refresh]);

  const groups = h ? groupByDay(h.sessions, h.to) : [];
  const rows = rowsOf(groups);

  return (
    <SafeAreaView style={styles.page}>
      <View style={styles.top}>
        <Pressable onPress={() => router.back()} accessibilityRole="button" hitSlop={8}>
          <Text style={styles.back}>‹ Back</Text>
        </Pressable>
        <View style={styles.range} accessibilityRole="radiogroup">
          {[7, 30].map((n) => (
            <Pressable key={n} onPress={() => setDays(n)} accessibilityRole="radio" accessibilityState={{ selected: days === n }}
              style={[styles.rangeButton, days === n && styles.rangeButtonOn]}>
              <Text style={[styles.rangeText, days === n && styles.rangeTextOn]}>{n} days</Text>
            </Pressable>
          ))}
        </View>
      </View>
      <Text style={styles.title}>History</Text>
      {h ? (
        <Text style={styles.summary}>
          {formatMinutes(h.minutes)} in {h.sessions_count} session{h.sessions_count === 1 ? "" : "s"} over the last {h.days} days
        </Text>
      ) : null}
      {message ? <Text style={styles.error} accessibilityRole="alert">{message}</Text> : null}

      <FlatList
        data={rows}
        keyExtractor={(r) => (r.kind === "day" ? `d-${r.group.date}` : `s-${r.session.id}`)}
        renderItem={({ item }) =>
          item.kind === "day" ? (
            <View style={styles.dayHead}>
              <Text style={styles.dayLabel}>{item.group.label}</Text>
              <Text style={styles.dayMinutes}>{formatMinutes(item.group.minutes)}</Text>
            </View>
          ) : (
            <View style={styles.session}>
              <View style={styles.sessionBody}>
                <Text style={styles.sessionMain} numberOfLines={1}>
                  {item.session.subject || "No subject"} — {formatMinutes(item.session.minutes)}
                </Text>
                <Text style={styles.sessionSub} numberOfLines={1}>
                  {item.session.assignment} · {clock12(item.session.start)} – {clock12(item.session.end)}
                </Text>
              </View>
              <Text style={styles.tick}>✓</Text>
            </View>
          )
        }
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={status === "refreshing"} onRefresh={refresh} tintColor={colors.accent} />}
        ListEmptyComponent={
          status === "loading" ? <Text style={styles.muted}>Loading…</Text>
          : status === "error" ? <Text style={styles.muted}>Can't load history. Pull down to try again.</Text>
          : <Text style={styles.muted}>No sessions recorded yet. Finish one from Focus and it will show up here.</Text>
        }
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.page },
  top: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingHorizontal: 20, paddingTop: 12 },
  back: { color: colors.accent, fontSize: 16, fontWeight: "600" },
  range: { flexDirection: "row", backgroundColor: colors.field, borderRadius: 999, padding: 3 },
  rangeButton: { paddingHorizontal: 12, paddingVertical: 5, borderRadius: 999 },
  rangeButtonOn: { backgroundColor: colors.page },
  rangeText: { color: colors.muted, fontSize: 13, fontWeight: "600" },
  rangeTextOn: { color: colors.ink },
  title: { color: colors.ink, fontSize: 30, fontWeight: "700", paddingHorizontal: 24, paddingTop: 8 },
  summary: { color: colors.muted, fontSize: 14, paddingHorizontal: 24, paddingTop: 2, paddingBottom: 8 },
  error: { color: colors.danger, fontSize: 14, paddingHorizontal: 24, paddingBottom: 8 },
  list: { paddingHorizontal: 16, paddingBottom: 24 },
  dayHead: { flexDirection: "row", justifyContent: "space-between", alignItems: "baseline", paddingTop: 18, paddingBottom: 6, paddingHorizontal: 4 },
  dayLabel: { color: colors.ink, fontSize: 15, fontWeight: "700" },
  dayMinutes: { color: colors.muted, fontSize: 13, fontVariant: ["tabular-nums"] },
  session: { flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: colors.field, borderRadius: 12, padding: 12, marginBottom: 8 },
  sessionBody: { flex: 1, gap: 2 },
  sessionMain: { color: colors.ink, fontSize: 16, fontWeight: "600" },
  sessionSub: { color: colors.muted, fontSize: 13 },
  tick: { color: "#1f7a3a", fontSize: 16, fontWeight: "700" },
  muted: { color: colors.muted, fontSize: 14, textAlign: "center", marginTop: 24, paddingHorizontal: 24 },
});
