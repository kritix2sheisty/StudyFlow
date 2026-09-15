/**
 * tests/attention.test.ts
 * The "needs attention" strip on Today: overdue assignments first, then
 * the plan's CRITICAL and HIGH risks, from the progress answer the app
 * already has. Pure; the date is passed in.
 */

import { attention } from "../src/today/attention";
import type { ProgressAssignment } from "../src/progress/store";

const A = (id: number, name: string, due_date: string, risk: string, extra: Partial<ProgressAssignment> = {}): ProgressAssignment => ({
  id, name, subject: "S", due_date, status: "SCHEDULED", required_hours: 2, scheduled_hours: 2, remaining_hours: 0,
  percent: 100, risk, done_hours: 0, done_percent: 0, ...extra,
});

test("overdue first (most overdue on top), then CRITICAL, then HIGH; MODERATE and LOW are left out", () => {
  const rows = attention([
    A(1, "Essay", "2026-09-16", "LOW"),
    A(2, "Math IA", "2026-09-18", "CRITICAL"),
    A(3, "Lab", "2026-09-12", "LOW"),
    A(4, "Project", "2026-09-20", "HIGH"),
    A(5, "Reading", "2026-09-10", "MODERATE"),
    A(6, "Quiz prep", "2026-09-17", "MODERATE"),
  ], "2026-09-14");
  expect(rows.map((r) => [r.name, r.kind, r.detail])).toEqual([
    ["Reading", "overdue", "4 days overdue"],
    ["Lab", "overdue", "2 days overdue"],
    ["Math IA", "risk", "CRITICAL · due in 4 days"],
    ["Project", "risk", "HIGH · due in 6 days"],
  ]);
});

test("due today and due tomorrow read as words, and one day overdue is singular", () => {
  const rows = attention([
    A(1, "Essay", "2026-09-14", "HIGH"),
    A(2, "Lab", "2026-09-15", "CRITICAL"),
    A(3, "Quiz", "2026-09-13", "LOW"),
  ], "2026-09-14");
  expect(rows.map((r) => r.detail)).toEqual(["1 day overdue", "CRITICAL · due tomorrow", "HIGH · due today"]);
});

test("nothing to say when everything is on track", () => {
  expect(attention([A(1, "Essay", "2026-09-16", "LOW"), A(2, "Lab", "2026-09-17", "MODERATE")], "2026-09-14")).toEqual([]);
});
