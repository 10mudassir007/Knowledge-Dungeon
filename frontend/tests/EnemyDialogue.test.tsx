import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { EnemyDialogue } from "../src/ui/EnemyDialogue";

/** Wraps the component so we can hold a submission open. */
function Harness({
  onSubmit = () => {},
  onHint = () => {},
  onRetreat = () => {},
  onSuperPower = () => {},
  neverResolves = false,
  loading = false,
  question = "What is the capital of France?",
  revealed = null,
  powering = false,
}: {
  onSubmit?: (a: string) => void;
  onHint?: () => void;
  onRetreat?: () => void;
  onSuperPower?: () => void;
  neverResolves?: boolean;
  loading?: boolean;
  question?: string | null;
  revealed?: string | null;
  powering?: boolean;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [hinting, setHinting] = useState(false);
  const [hint, setHint] = useState<string | null>(null);

  return (
    <EnemyDialogue
      question={question}
      loading={loading}
      orcName="Grukk"
      hint={hint}
      hinting={hinting}
      submitting={submitting}
      powering={powering}
      revealed={revealed}
      canUseSuperPower={!revealed}
      health={100}
      anchor={{ x: 100, y: 100 }}
      onSubmit={(a) => {
        if (neverResolves) setSubmitting(true);
        onSubmit(a);
      }}
      onHint={() => {
        if (neverResolves) setHinting(true);
        onHint();
        setHint("Think of the city of light.");
      }}
      onSuperPower={onSuperPower}
      onRetreat={onRetreat}
    />
  );
}

describe("EnemyDialogue", () => {
  it("shows a loading state while the question is being written", () => {
    render(<Harness loading question={null} />);
    expect(screen.getByTestId("question-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("question")).not.toBeInTheDocument();
    // Everything is locked until the question arrives.
    expect(screen.getByTestId("answer-input")).toBeDisabled();
    expect(screen.getByTestId("submit")).toBeDisabled();
    expect(screen.getByTestId("hint-button")).toBeDisabled();
    expect(screen.getByTestId("retreat-button")).toBeDisabled();
  });

  it("shows the question, the speaker and the three actions", () => {
    render(<Harness />);
    expect(screen.getByTestId("question")).toHaveTextContent("capital of France");
    expect(screen.getByTestId("orc-name")).toHaveTextContent("Grukk challenges you");
    expect(screen.getByTestId("submit")).toBeInTheDocument();
    expect(screen.getByTestId("hint-button")).toBeInTheDocument();
    expect(screen.getByTestId("retreat-button")).toBeInTheDocument();
  });

  it("caps the input at 500 characters", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const input = screen.getByTestId("answer-input") as HTMLInputElement;

    await user.click(input);
    await user.paste("x".repeat(900));

    await waitFor(() => {
      expect(input.value.length).toBe(500);
      expect(input.maxLength).toBe(500);
    });
  });

  it("disables Submit while the request is in flight", async () => {
    const user = userEvent.setup();
    render(<Harness neverResolves />);
    const input = screen.getByTestId("answer-input");
    await user.type(input, "Paris");

    const submit = screen.getByTestId("submit");
    expect(submit).toBeEnabled();
    await user.click(submit);

    // A second submit cannot be sent for the same question.
    await waitFor(() => expect(screen.getByTestId("submit")).toBeDisabled());
    expect(screen.getByTestId("answer-input")).toBeDisabled();
  });

  it("keeps Submit disabled for an empty answer", () => {
    render(<Harness />);
    expect(screen.getByTestId("submit")).toBeDisabled();
  });

  it("disables Hint while the hint request is in flight", async () => {
    const user = userEvent.setup();
    render(<Harness neverResolves />);
    const hintBtn = screen.getByTestId("hint-button");
    expect(hintBtn).toBeEnabled();
    await user.click(hintBtn);
    await waitFor(() => expect(screen.getByTestId("hint-button")).toBeDisabled());
  });

  it("renders the hint once it arrives", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.queryByTestId("hint")).not.toBeInTheDocument();
    await user.click(screen.getByTestId("hint-button"));
    expect(await screen.findByTestId("hint")).toHaveTextContent("city of light");
  });

  it("calls onSubmit with the typed answer and clears the field", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);

    const input = screen.getByTestId("answer-input") as HTMLInputElement;
    await user.type(input, "Paris");
    await user.click(screen.getByTestId("submit"));

    expect(onSubmit).toHaveBeenCalledWith("Paris");
    expect(input.value).toBe("");
  });

  it("calls onRetreat", async () => {
    const user = userEvent.setup();
    const onRetreat = vi.fn();
    render(<Harness onRetreat={onRetreat} />);
    await user.click(screen.getByTestId("retreat-button"));
    expect(onRetreat).toHaveBeenCalled();
  });
});