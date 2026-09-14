/**
 * src/app/(app)/index.tsx
 * Today. The list of study sessions planned for today, each marked done,
 * on now, past or upcoming; a header with the date and how many are
 * done; pull down to refresh, and a refresh whenever the app comes back
 * to the front so the clock is right. No plan or a stale plan sends the
 * student to the laptop, where planning lives. Tapping a session opens
 * Focus for it, with the session passed as route params.
 */

import { router } from "expo-router";
import { useCallback, useEffect } from "react";
import {
  AppState, FlatList, Pressable, RefreshControl, StyleSheet, Text, View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { session } from "../../auth";
import { useSession } from "../../auth/useSession";
import { today, useToday } from "../../today";
import type { TodayRow, TodayView } from "../../today/view";
import { colors } from "../../ui/AuthForm";

const STATE_LABEL: Record<TodayRow["state"], string> = {
  done: "Done",
  now: "Now",
  past: "Missed",
  upcoming: "",
};

function dateLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

function openFocus(row: TodayRow) {
  router.push({ pathname: "/focus", params: {
    assignment: row.assignment, subject: row.subject, date: row.date, start: row.start, end: row.end,
    duration_minutes: String(row.duration_minutes), completed: String(row.completed),
  } });
}

function SessionRow({ row }: { row: TodayRow }) {
  const done = row.state === "done";
  const now = row.state === "now";
  return (
    <Pressable
      onPress={() => openFocus(row)}
      accessibilityRole="button"
      accessibilityLabel={`${row.assignment}, ${row.start} to ${row.end}, ${STATE_LABEL[row.state] || "upcoming"}`}
      style={({ pressed }) => [styles.row, now && styles.rowNow, done && styles.rowDone, pressed && styles.rowPressed]}
    >
      <View style={styles.rowTime}>
        <Text style={[styles.time, done && styles.muted]}>{row.start}</Text>
        <Text style={[styles.timeEnd, done && styles.muted]}>{row.end}</Text>
      </View>
      <View style={styles.rowBody}>
        <Text style={[styles.assignment, done && styles.strike]} numberOfLines={2}>{row.assignment}</Text>
        <Text style={[styles.subject, done && styles.muted]} numberOfLines={1}>
          {row.subject ? `${row.subject} · ` : ""}{row.duration_minutes} min
        </Text>
      </View>
      {STATE_LABEL[row.state] ? (
        <Text style={[styles.badge, now && styles.badgeNow, done && styles.badgeDone, row.state === "past" && styles.badgePast]}>
          {done ? "✓ Done" : STATE_LABEL[row.state]}
        </Text>
      ) : null}
    </Pressable>
  );
}

function Notice({ title, body }: { title: string; body: string }) {
  return (
    <View style={styles.notice}>
      <Text style={styles.noticeTitle}>{title}</Text>
      <Text style={styles.noticeBody}>{body}</Text>
    </View>
  );
}

function Body({ view }: { view: TodayView }) {
  switch (view.kind) {
    case "no_plan":
      return <Notice title="No plan yet" body="Add your assignments and study time on your laptop and generate a plan. Today's sessions will show up here." />;
    case "plan_stale":
      return <Notice title="Your plan needs regenerating" body="Something changed since it was made. Regenerate it on your laptop, then pull down to refresh." />;
    case "empty":
      return <Notice title="Nothing planned today" body="Enjoy the day off, or check tomorrow's sessions on your laptop." />;
    default:
      return null;
  }
}

export default function TodayScreen() {
  const { email, user } = useSession();
  const { status, view, message } = useToday();

  const refresh = useCallback(() => { void today.load(); }, []);

  useEffect(() => {
    refresh();
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") refresh();
    });
    return () => sub.remove();
  }, [refresh]);

  const rows = view?.kind === "sessions" ? view.rows : [];

  return (
    <SafeAreaView style={styles.page}>
      <View style={styles.header}>
        <View>
          <Text style={styles.brand}>StudyFlow</Text>
          <Text style={styles.title}>Today</Text>
          {view ? <Text style={styles.date}>{dateLabel(view.date)}</Text> : null}
        </View>
        <Pressable onPress={() => void session.signOut()} accessibilityRole="button" hitSlop={8}>
          <Text style={styles.logout}>Log out</Text>
        </Pressable>
      </View>

      {view?.kind === "sessions" ? (
        <Text style={styles.progress}>{view.done} of {view.total} done</Text>
      ) : null}
      {message ? <Text style={styles.error} accessibilityRole="alert">{message}</Text> : null}

      <FlatList
        data={rows}
        keyExtractor={(r) => `${r.date}-${r.start}-${r.end}`}
        renderItem={({ item }) => <SessionRow row={item} />}
        contentContainerStyle={styles.list}
        refreshControl={<RefreshControl refreshing={status === "refreshing"} onRefresh={refresh} tintColor={colors.accent} />}
        ListEmptyComponent={
          status === "loading" ? <Text style={styles.loading}>Loading today…</Text>
          : status === "error" ? <Notice title="Can't load today" body="Pull down to try again." />
          : view ? <Body view={view} />
          : null
        }
        ListFooterComponent={<Text style={styles.footer}>Signed in as {user?.email ?? email}</Text>}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.page },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "flex-start", paddingHorizontal: 24, paddingTop: 16, paddingBottom: 8 },
  brand: { color: colors.accent, fontSize: 13, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },
  title: { color: colors.ink, fontSize: 30, fontWeight: "700", marginTop: 2 },
  date: { color: colors.muted, fontSize: 15, marginTop: 2 },
  logout: { color: colors.accent, fontSize: 16, fontWeight: "600", paddingTop: 4 },
  progress: { color: colors.muted, fontSize: 14, paddingHorizontal: 24, paddingBottom: 8 },
  error: { color: colors.danger, fontSize: 14, paddingHorizontal: 24, paddingBottom: 8 },
  list: { paddingHorizontal: 16, paddingBottom: 24, gap: 10 },
  row: { flexDirection: "row", alignItems: "center", gap: 14, backgroundColor: colors.field, borderRadius: 14, padding: 14 },
  rowNow: { backgroundColor: "#e3f1fd", borderWidth: 2, borderColor: colors.accent },
  rowDone: { opacity: 0.75 },
  rowPressed: { opacity: 0.6 },
  rowTime: { width: 52, alignItems: "flex-start" },
  time: { color: colors.ink, fontSize: 16, fontWeight: "700", fontVariant: ["tabular-nums"] },
  timeEnd: { color: colors.muted, fontSize: 13, fontVariant: ["tabular-nums"] },
  rowBody: { flex: 1, gap: 2 },
  assignment: { color: colors.ink, fontSize: 17, fontWeight: "600" },
  subject: { color: colors.muted, fontSize: 13 },
  strike: { textDecorationLine: "line-through", color: colors.muted },
  muted: { color: colors.muted },
  badge: { fontSize: 12, fontWeight: "700", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 999, overflow: "hidden", color: colors.ink, backgroundColor: "#e5e5ea" },
  badgeNow: { color: "#fff", backgroundColor: colors.accent },
  badgeDone: { color: "#1f7a3a", backgroundColor: "#dff5e5" },
  badgePast: { color: "#8a5a00", backgroundColor: "#fff1cc" },
  notice: { backgroundColor: colors.field, borderRadius: 14, padding: 18, gap: 6, marginTop: 8 },
  noticeTitle: { color: colors.ink, fontSize: 17, fontWeight: "600" },
  noticeBody: { color: colors.muted, fontSize: 14, lineHeight: 20 },
  loading: { color: colors.muted, fontSize: 14, textAlign: "center", marginTop: 24 },
  footer: { color: colors.muted, fontSize: 12, textAlign: "center", marginTop: 24 },
});
