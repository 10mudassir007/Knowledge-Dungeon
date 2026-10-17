import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SetupScreen } from "../src/ui/SetupScreen";
import { DIFFICULTIES } from "../src/game/useGame";

const nameInput = () => screen.getByTestId("name-input") as HTMLInputElement;
const topicInput = () => screen.getByTestId("topic-input") as HTMLInputElement;
const enter = () => screen.getByTestId("enter-dungeon") as HTMLButtonElement;

function open() {
  const onBegin = vi.fn();
  render(<SetupScreen onBegin={onBegin} />);
  return onBegin;
}

describe("SetupScreen", () => {
  it("prefills the topic from the chosen difficulty", async () => {
    const user = userEvent.setup();
    open();
    expect(topicInput().value).toBe(DIFFICULTIES[1].interest);
    await user.click(screen.getByTestId("difficulty-legend"));
    expect(topicInput().value).toBe(DIFFICULTIES[2].interest);
  });

  it("stops following the difficulty once the topic is edited", async () => {
    const user = userEvent.setup();
    open();
    await user.clear(topicInput());
    await user.type(topicInput(), "space and astronomy");
    await user.click(screen.getByTestId("difficulty-squire"));
    expect(topicInput().value).toBe("space and astronomy");
  });

  it("fills the topic from a preset chip", async () => {
    const user = userEvent.setup();
    open();
    await user.click(screen.getByTestId("topic-preset-space"));
    expect(topicInput().value).toBe("space and astronomy");
  });

  it("hands name, difficulty and topic to the dungeon", async () => {
    const user = userEvent.setup();
    const onBegin = open();
    await user.type(nameInput(), "Aric");
    await user.click(screen.getByTestId("difficulty-legend"));
    await user.click(screen.getByTestId("topic-preset-myth"));
    await user.click(enter());
    expect(onBegin).toHaveBeenCalledTimes(1);
    expect(onBegin).toHaveBeenCalledWith("Aric", DIFFICULTIES[2], "greek mythology");
  });

  it("keeps entry blocked while the topic is blank", async () => {
    const user = userEvent.setup();
    const onBegin = open();
    await user.type(nameInput(), "Aric");
    await user.clear(topicInput());
    expect(enter().disabled).toBe(true);
    expect(screen.getByText(/give the orcs a topic/i)).toBeTruthy();
    await user.click(enter());
    expect(onBegin).not.toHaveBeenCalled();
  });
});
