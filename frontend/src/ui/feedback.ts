/**
 * Where bug reports and feature requests land: the project's public issue
 * tracker, opened with a prefilled template so a report is one click away.
 *
 * Both the lectern's pages and the pause menu point here, so the two entry
 * points can never drift apart.
 */

const NEW_ISSUE_URL = "https://github.com/10mudassir007/Knowledge-Dungeon/issues/new";

export type FeedbackKind = "bug" | "feature";

/** A prefilled GitHub "new issue" link for a bug report or a feature idea. */
export function feedbackHref(kind: FeedbackKind): string {
  const title = kind === "bug" ? "[Bug] " : "[Feature] ";
  const prompts =
    kind === "bug"
      ? ["What happened:", "", "What I expected instead:", "", "How to make it happen again:", "1. "]
      : ["What I would like to see:", "", "Why it would help:"];
  const body = [
    ...prompts,
    "",
    "---",
    `Where: ${typeof window === "undefined" ? "the dungeon" : window.location.href}`,
    `When: ${new Date().toISOString()}`,
  ].join("\n");
  return `${NEW_ISSUE_URL}?${new URLSearchParams({ title, body }).toString()}`;
}
