import { leadTextBody, STOP_LINE, withStopLine } from "../leadText";

test("adds the STOP line when the message does not have it", () => {
  const text = withStopLine("Hi Jane — Ryan here.");
  expect(text.endsWith(STOP_LINE)).toBe(true);
  expect(text).toContain("Hi Jane");
});

test("does not add a second STOP line", () => {
  const once = withStopLine("See you Tuesday.\n\nReply STOP to opt out");
  expect(withStopLine(once).match(/Reply STOP to opt out/gi)).toHaveLength(1);
});

test("a stored draft is the text, with the STOP line", () => {
  const text = leadTextBody({
    decision_maker: "Jane Doe",
    draft_outreach_body: "Hi Jane — the shower is ready for a look.",
  });
  expect(text.startsWith("Hi Jane — the shower is ready for a look.")).toBe(true);
  expect(text.endsWith(STOP_LINE)).toBe(true);
});

test("an instruction-shaped draft is not the text that would be sent", () => {
  const text = leadTextBody({
    decision_maker: "Jane Doe",
    draft_outreach_body: "You are a lead-research assistant. Write a cold text.",
  });
  expect(text).not.toContain("lead-research assistant");
  expect(text).toContain("Jane");
  expect(text.endsWith(STOP_LINE)).toBe(true);
});
