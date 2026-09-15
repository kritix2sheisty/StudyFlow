/**
 * src/app/(app)/focus.tsx
 * Focus. One session, one clock, nothing else on screen. The session
 * comes in as route params from Today (or from the current-session
 * shortcut). The countdown is the session's length, started by the
 * student; pause, resume and reset; when it reaches zero, "Session
 * complete" with a 15-minute break countdown and the next session from
 * the server. Mark complete records the block through the API (a
 * session record, never the whole assignment), then Today and Progress
 * refresh; the answer's hours done are shown. A block already recorded
 * says so instead of offering the button.
 *
 * The clock is read, never counted: useNow re-renders, the timer value
 * gives remaining = endAt - now (see focus/timer.ts).
 */

import { router, useLocalSearchParams } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { api } from "../../auth";
import { focus, useFocus, useNow } from "../../focus";
import { CompleteAnswer, completeSession } from "../../focus/complete";
import {
  createTimer, formatClock, isFinished, pause, remainingMs, reset, resume, start, Timer,
} from "../../focus/timer";
import { history } from "../../history";
import { progress } from "../../progress";
import { today } from "../../today";
import { clock12 } from "../../today/view";
import { colors } from "../../ui/AuthForm";
import { errorMessage } from "../../ui/messages";

export const BREAK_MINUTES = 15;

type Params = {
  assignment?: string;
  subject?: string;
  date?: string;
  start?: string;
  end?: string;
  duration_minutes?: string;
  completed?: string;
};

function Button({ label, onPress, primary = false, quiet = false }: { label: string; onPress: () => void; primary?: boolean; quiet?: boolean }) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      style={({ pressed }) => [styles.button, primary && styles.buttonPrimary, quiet && styles.buttonQuiet, pressed && styles.pressed]}
    >
      <Text style={[styles.buttonText, primary && styles.buttonTextPrimary, quiet && styles.buttonTextQuiet]}>{label}</Text>
    </Pressable>
  );
}

export default function FocusScreen() {
  const p = useLocalSearchParams<Params>();
  const minutes = Math.max(1, Number(p.duration_minutes) || 25);
  const [timer, setTimer] = useState<Timer>(() => createTimer(minutes * 60_000));
  const [breakTimer, setBreakTimer] = useState<Timer | null>(null);
  const [recorded, setRecorded] = useState<CompleteAnswer | null>(null);
  const [recording, setRecording] = useState(false);
  const [recordError, setRecordError] = useState<string | null>(null);
  const alreadyRecorded = p.completed === "true" || recorded !== null;
  const { next, nextReason } = useFocus();

  const active = timer.phase === "running" || breakTimer?.phase === "running";
  const now = useNow(active);
  const finished = isFinished(timer, now);
  const onBreak = breakTimer !== null;
  const breakOver = breakTimer ? isFinished(breakTimer, now) : false;

  const loadNext = useCallback(() => { void focus.load(); }, []);
  useEffect(() => { loadNext(); }, [loadNext]);
  useEffect(() => { if (finished) loadNext(); }, [finished, loadNext]);

  const markComplete = async () => {
    if (recording || !p.date || !p.start || !p.end) return;
    setRecording(true);
    setRecordError(null);
    try {
      setRecorded(await completeSession({ api, today, progress, history }, { date: p.date, start: p.start, end: p.end }));
      loadNext();
    } catch (e) {
      setRecordError(errorMessage(e));
    } finally {
      setRecording(false);
    }
  };

  const goNext = () => {
    if (!next) return;
    router.replace({ pathname: "/focus", params: {
      assignment: next.assignment, subject: next.subject, date: next.date, start: next.start, end: next.end,
      duration_minutes: String(next.duration_minutes), completed: String(next.completed),
    } });
  };

  const shown = onBreak ? breakTimer! : timer;
  const remaining = remainingMs(shown, now);
  const label = onBreak ? (breakOver ? "Break over" : "Break") : finished ? "Session complete" : timer.phase === "idle" ? "Ready" : timer.phase === "paused" ? "Paused" : "Focus";

  return (
    <SafeAreaView style={styles.page}>
      <View style={styles.top}>
        <Pressable onPress={() => router.back()} accessibilityRole="button" hitSlop={8}>
          <Text style={styles.back}>‹ Today</Text>
        </Pressable>
      </View>

      <View style={styles.center}>
        <Text style={styles.subject}>{p.subject || " "}</Text>
        <Text style={styles.assignment} numberOfLines={3}>{p.assignment ?? "Study session"}</Text>
        <Text style={styles.when}>{p.start && p.end ? `${clock12(p.start)} – ${clock12(p.end)} · ${minutes} min` : `${minutes} min`}</Text>

        <Text style={styles.phase}>{label}</Text>
        <Text style={[styles.clock, onBreak && styles.clockBreak]} accessibilityLabel={`${formatClock(remaining)} remaining`}>
          {formatClock(remaining)}
        </Text>

        {!onBreak && !finished && (
          <View style={styles.controls}>
            {timer.phase === "idle" && <Button label="Start session" primary onPress={() => setTimer(start(timer, Date.now()))} />}
            {timer.phase === "running" && <Button label="Pause" onPress={() => setTimer(pause(timer, Date.now()))} />}
            {timer.phase === "paused" && <Button label="Resume" primary onPress={() => setTimer(resume(timer, Date.now()))} />}
            {timer.phase !== "idle" && <Button label="Reset" quiet onPress={() => setTimer(reset(timer))} />}
          </View>
        )}

        {!onBreak && finished && (
          <View style={styles.controls}>
            {recorded ? (
              <Text style={styles.done}>
                Session recorded. {recorded.assignment.name}: {recorded.assignment.done_hours} of {recorded.assignment.required_hours} hours done.
              </Text>
            ) : alreadyRecorded ? (
              <Text style={styles.done}>This session was already recorded.</Text>
            ) : (
              <Text style={styles.done}>{minutes} minutes completed.</Text>
            )}
            {recordError ? <Text style={styles.error} accessibilityRole="alert">{recordError}</Text> : null}
            {!alreadyRecorded && <Button label={recording ? "Recording…" : "Mark complete"} primary onPress={() => void markComplete()} />}
            <Button label={`Take a ${BREAK_MINUTES}-minute break`} onPress={() => setBreakTimer(start(createTimer(BREAK_MINUTES * 60_000), Date.now()))} />
            {next ? <Button label={`Next: ${next.assignment}`} primary={alreadyRecorded} onPress={goNext} /> : null}
            <Button label="Back to Today" quiet onPress={() => router.back()} />
          </View>
        )}

        {onBreak && (
          <View style={styles.controls}>
            {breakOver
              ? (next ? <Button label={`Next: ${next.assignment}`} primary onPress={goNext} /> : <Button label="Back to Today" primary onPress={() => router.back()} />)
              : <Button label="End break" quiet onPress={() => setBreakTimer(null)} />}
          </View>
        )}
      </View>

      <Text style={styles.next}>
        {next ? `Up next: ${next.assignment} at ${clock12(next.start)}` : nextReason === "nothing_next" ? "Nothing after this. Nice." : nextReason === "plan_stale" ? "Your plan needs regenerating on your laptop." : " "}
      </Text>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, backgroundColor: colors.page },
  top: { paddingHorizontal: 20, paddingTop: 12 },
  back: { color: colors.accent, fontSize: 16, fontWeight: "600" },
  center: { flex: 1, alignItems: "center", justifyContent: "center", paddingHorizontal: 28, gap: 6 },
  subject: { color: colors.accent, fontSize: 13, fontWeight: "700", letterSpacing: 1, textTransform: "uppercase" },
  assignment: { color: colors.ink, fontSize: 24, fontWeight: "700", textAlign: "center" },
  when: { color: colors.muted, fontSize: 14, marginBottom: 28 },
  phase: { color: colors.muted, fontSize: 14, textTransform: "uppercase", letterSpacing: 2 },
  clock: { color: colors.ink, fontSize: 84, fontWeight: "200", fontVariant: ["tabular-nums"], letterSpacing: -2, marginBottom: 24 },
  clockBreak: { color: "#1f7a3a" },
  controls: { width: "100%", gap: 10, alignItems: "stretch" },
  done: { color: colors.muted, fontSize: 15, textAlign: "center", marginBottom: 6 },
  error: { color: colors.danger, fontSize: 14, textAlign: "center", marginBottom: 6 },
  button: { backgroundColor: colors.field, borderRadius: 12, paddingVertical: 15, alignItems: "center" },
  buttonPrimary: { backgroundColor: colors.accent },
  buttonQuiet: { backgroundColor: "transparent" },
  pressed: { opacity: 0.7 },
  buttonText: { color: colors.ink, fontSize: 17, fontWeight: "600" },
  buttonTextPrimary: { color: "#fff" },
  buttonTextQuiet: { color: colors.muted, fontWeight: "500" },
  next: { color: colors.muted, fontSize: 13, textAlign: "center", paddingVertical: 16 },
});
