/**
 * src/app/(app)/progress.tsx
 * Progress. Two sources, shown, not recomputed: the history endpoint
 * for the week (hours studied, sessions, streak, subjects, today's
 * planned against completed) and the plan's progress for each
 * assignment (hours done against required, with the engine's risk word
 * as it sends it: CRITICAL / HIGH / MODERATE / LOW). The mentor's two
 * motivation sentences sit on top when there is something to say.
 * Refreshes on pull and whenever it opens; History is one tap away.
 */

import { router } from "expo-router";
import { useCallback, useEffect } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { history, useHistory } from "../../history";
import { formatMinutes, todayLines, weekSummary } from "../../history/view";
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

function Tile({ number, label }: { number: string; label: string }) {
  return (
    <View style={styles.tile}>
      <Text style={styles.tileNumber}>{number}</Text>
      <Text style={styles.tileLabel}>{label}</Text>
    </View>
  );
}

function Bar({ percent, color = colors.accent }: { percent: number; color?: string }) {
  return (
    <View style={styles.bar}>
      <View style={[styles.barFill, { width: `${Math.min(100, Math.max(0, percent))}%`, backgroundColor: color }]} />
    </View>
  );
}

function AssignmentRow({ a }: { a: ProgressAssignment }) {
  return (
    <View style={styles.row}>
      <View style={styles.rowTop}>
        <Text style={styles.name} numberOfLines={2}>{a.name}</Text>
        <Text style={[styles.risk, { color: RISK_COLOR[a.risk] ?? colors.muted }]}>{a.risk}</Text>
      </View>
      <Text style={styles.meta}>{a.subject ? `${a.subject} · ` : ""}due {a.due_date}</Text>
      <Bar percent={a.done_percent} />
      <Text style={styles.hours}>{hours(a.done_hours)} of {hours(a.required_hours)} done · {Math.min(100, Math.max(0, a.done_percent))}%</Text>
    </View>
  );
}

export default function ProgressScreen() {
  const { status, progress: p, message } = useProgress();
  const { history: h, message: historyMessage } = useHistory();
  const refresh = useCallback(() => { void progress.load(); void history.load(); }, []);
  useEffect(() => { refresh(); }, [refresh]);

  const week = h ? weekSummary(h) : null;
  const lines = h ? todayLines(h.today) : [];

  const header = (
    <View style={styles.header}>
      {lines.length ? (
        <View style={styles.cheer}>
          <Text style={styles.cheerMain}>{lines[0]}</Text>
          <Text style={styles.cheerSub}>{lines[1]}</Text>
        </View>
      ) : null}

      {week ? (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>Today</Text>
          {week.today.planned > 0 ? (
            <>
              <Bar percent={week.today.percent} color="#1f7a3a" />
              <Text style={styles.cardLine}>
                {formatMinutes(week.today.done)} of {formatMinutes(week.today.planned)} planned · {week.today.sessionsDone} of {week.today.sessionsPlanned} session{week.today.sessionsPlanned === 1 ? "" : "s"} · {week.today.percent}%
              </Text>
            </>
          ) : (
            <Text style={styles.cardLine}>
              {week.today.done > 0 ? `${formatMinutes(week.today.done)} studied. ` : ""}Nothing planned for today{p && !p.fresh ? " until the plan is regenerated on your laptop" : ""}.
            </Text>
          )}
        </View>
      ) : null}

      {week ? (
        <>
          <Text style={styles.sectionTitle}>Last {week.daysInWindow} days</Text>
          <View style={styles.tiles}>
            <Tile number={formatMinutes(week.minutes)} label="studied" />
            <Tile number={String(week.sessions)} label="sessions" />
            <Tile number={`${week.streak}`} label={week.streak === 1 ? "day streak" : "day streak"} />
            <Tile number={`${week.activeDays}/${week.daysInWindow}`} label="days studied" />
          </View>
          {h && h.by_subject.length ? (
            <View style={styles.card}>
              <Text style={styles.cardTitle}>Subjects</Text>
              {h.by_subject.map((s) => (
                <View key={s.subject || "none"} style={styles.subjectRow}>
                  <Text style={styles.subjectName} numberOfLines={1}>{s.subject || "No subject"}</Text>
                  <Bar percent={h.minutes ? (100 * s.minutes) / h.minutes : 0} />
                  <Text style={styles.subjectMinutes}>{formatMinutes(s.minutes)}</Text>
                </View>
              ))}
            </View>
          ) : null}
          <Pressable onPress={() => router.push("/history")} accessibilityRole="button" style={styles.link}>
            <Text style={styles.linkText}>All sessions ›</Text>
          </Pressable>
        </>
      ) : null}

      {p ? (
        <View style={styles.assignHead}>
          <Text style={styles.sectionTitle}>Assignments</Text>
          <Text style={styles.sectionMeta}>{p.active_count} active · {p.completed_count} finished</Text>
          {!p.fresh ? <Text style={styles.stale}>Your plan needs regenerating on your laptop; hours shown are from the assignments themselves.</Text> : null}
        </View>
      ) : null}
    </View>
  );

  return (
    <SafeAreaView style={styles.page}>
      <View style={styles.top}>
        <Pressable onPress={() => router.back()} accessibilityRole="button" hitSlop={8}>
          <Text style={styles.back}>‹ Today</Text>
        </Pressable>
      </View>
      <Text style={styles.title}>Progress</Text>
      {message || historyMessage ? <Text style={styles.error} accessibilityRole="alert">{message ?? historyMessage}</Text> : null}

      <FlatList
        data={p?.assignments ?? []}
        keyExtractor={(a) => String(a.id)}
        renderItem={({ item }) => <AssignmentRow a={item} />}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={status === "refreshing"} onRefresh={refresh} tintColor={colors.accent} />}
        ListHeaderComponent={header}
        ListEmptyComponent={
          status === "loading" ? <Text style={styles.muted}>Loading…</Text>
          : status === "error" ? <Text style={styles.muted}>Can't load progress. Pull down to try again.</Text>
          : <Text style={styles.muted}>No active assignments.</Text>
        }
        ListFooterComponent={p && p.completed.length ? (
          <View style={styles.completed}>
            <Text style={styles.sectionTitle}>Completed</Text>
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
  title: { color: colors.ink, fontSize: 30, fontWeight: "700", paddingHorizontal: 24, paddingTop: 8, paddingBottom: 4 },
  error: { color: colors.danger, fontSize: 14, paddingHorizontal: 24, paddingBottom: 8 },
  list: { paddingHorizontal: 16, paddingBottom: 24, gap: 10 },
  header: { gap: 10, paddingBottom: 4 },
  cheer: { backgroundColor: "#e3f1fd", borderRadius: 14, padding: 14, gap: 2 },
  cheerMain: { color: colors.ink, fontSize: 17, fontWeight: "700" },
  cheerSub: { color: colors.ink, fontSize: 14 },
  card: { backgroundColor: colors.field, borderRadius: 14, padding: 14, gap: 8 },
  cardTitle: { color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1, fontWeight: "600" },
  cardLine: { color: colors.ink, fontSize: 14 },
  sectionTitle: { color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1, fontWeight: "600", paddingTop: 6 },
  sectionMeta: { color: colors.muted, fontSize: 13 },
  tiles: { flexDirection: "row", flexWrap: "wrap", gap: 10 },
  tile: { flexGrow: 1, flexBasis: "45%", backgroundColor: colors.field, borderRadius: 14, padding: 14, alignItems: "center" },
  tileNumber: { color: colors.ink, fontSize: 24, fontWeight: "700", fontVariant: ["tabular-nums"] },
  tileLabel: { color: colors.muted, fontSize: 12, textTransform: "uppercase", letterSpacing: 1, marginTop: 2 },
  subjectRow: { gap: 4 },
  subjectName: { color: colors.ink, fontSize: 14, fontWeight: "600" },
  subjectMinutes: { color: colors.muted, fontSize: 12, fontVariant: ["tabular-nums"] },
  link: { alignSelf: "flex-start", paddingVertical: 4 },
  linkText: { color: colors.accent, fontSize: 15, fontWeight: "600" },
  assignHead: { gap: 4 },
  stale: { color: "#8a5a00", fontSize: 13, backgroundColor: "#fff1cc", borderRadius: 10, padding: 10 },
  row: { backgroundColor: colors.field, borderRadius: 14, padding: 14, gap: 6 },
  rowTop: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", gap: 12 },
  name: { flex: 1, color: colors.ink, fontSize: 17, fontWeight: "600" },
  risk: { fontSize: 12, fontWeight: "700", letterSpacing: 1 },
  meta: { color: colors.muted, fontSize: 13 },
  bar: { height: 8, borderRadius: 999, backgroundColor: "#e5e5ea", overflow: "hidden" },
  barFill: { height: "100%", borderRadius: 999 },
  hours: { color: colors.muted, fontSize: 13, fontVariant: ["tabular-nums"] },
  muted: { color: colors.muted, fontSize: 14, textAlign: "center", marginTop: 24 },
  completed: { marginTop: 8, gap: 6 },
  completedName: { color: colors.muted, fontSize: 15 },
});
