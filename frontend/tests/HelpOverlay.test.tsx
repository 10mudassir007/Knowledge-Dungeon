import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { HelpOverlay } from "../src/ui/HelpOverlay";
import { PauseMenu, SHORTCUTS } from "../src/ui/PauseMenu";
import { feedbackHref } from "../src/ui/feedback";
import type { SystemProfile } from "../src/game/graphics";

const TRACKER = "https://github.com/10mudassir007/Knowledge-Dungeon/issues/new?";

describe("feedbackHref", () => {
  it("prefills the report with the page and a template", () => {
    const href = feedbackHref("bug");
    expect(href.startsWith(TRACKER)).toBe(true);
    expect(href).toContain("title=%5BBug%5D");
    const body = decodeURIComponent(href.replace(/\+/g, " "));
    expect(body).toContain("What happened:");
    expect(body).toContain(`Where: ${window.location.href}`);
  });
});

describe("HelpOverlay", () => {
  it("reads as the how-to-play pages, with every shortcut", () => {
    render(<HelpOverlay onClose={() => {}} />);
    expect(screen.getByTestId("help")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "How to play" })).toBeTruthy();
    expect(screen.getByText(/Reach the/)).toBeTruthy();
    for (const s of SHORTCUTS) {
      expect(screen.getByText(s.keys)).toBeTruthy();
      expect(screen.getByText(s.action)).toBeTruthy();
    }
  });

  it("carries bug and feature links into the public tracker", () => {
    render(<HelpOverlay onClose={() => {}} />);
    const bug = screen.getByTestId("help-report-bug");
    const feature = screen.getByTestId("help-suggest-feature");
    expect(bug.getAttribute("href")?.startsWith(TRACKER)).toBe(true);
    expect(bug.getAttribute("href")).toContain("%5BBug%5D");
    expect(feature.getAttribute("href")?.startsWith(TRACKER)).toBe(true);
    expect(feature.getAttribute("href")).toContain("%5BFeature%5D");
    for (const a of [bug, feature]) {
      expect(a.getAttribute("target")).toBe("_blank");
      expect(a.getAttribute("rel")).toContain("noreferrer");
    }
  });

  it("closes on the backdrop and its button, but not on its own pages", async () => {
    const onClose = vi.fn();
    render(<HelpOverlay onClose={onClose} />);
    const user = userEvent.setup();
    await user.click(screen.getByRole("heading", { name: "How to play" }));
    await user.click(screen.getByTestId("help-shortcuts"));
    expect(onClose).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("help-close"));
    expect(onClose).toHaveBeenCalledTimes(1);
    await user.click(screen.getByTestId("help"));
    expect(onClose).toHaveBeenCalledTimes(2);
  });
});

describe("PauseMenu feedback", () => {
  it("carries the same bug and feature links", () => {
    render(
      <PauseMenu
        onResume={() => {}}
        onRestart={() => {}}
        onQuit={() => {}}
        muted={false}
        onToggleSound={() => {}}
        setting="auto"
        tier="low"
        profile={{ suggested: "low" } as SystemProfile}
        onSetting={() => {}}
        fps={null}
        showFps={false}
        onToggleFps={() => {}}
      />,
    );
    expect(screen.getByTestId("report-bug").getAttribute("href")?.startsWith(TRACKER)).toBe(true);
    expect(screen.getByTestId("suggest-feature").getAttribute("href")).toContain("%5BFeature%5D");
  });
});
