import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { LeadContactActions } from "../LeadContactActions";

const opp = {
  id: "rec1",
  phone: "(504) 555-0142",
  decision_maker: "Jane Doe",
  draft_outreach_body: "Hi Jane — the shower is ready for a look.",
};

test("Text is a button and Open on phone keeps the sms link", () => {
  const html = renderToStaticMarkup(<LeadContactActions opportunity={opp} />);
  expect(html).toContain('data-testid="call-lead-rec1"');
  expect(html).toMatch(/<button[^>]*data-testid="text-lead-rec1"[^>]*>/);
  expect(html).toContain("> Text</button>");
  expect(html).toContain('data-testid="open-on-phone-rec1"');
  expect(html).toContain("sms:5045550142?body=");
  expect(html).toContain("Reply%20STOP%20to%20opt%20out");
  expect(html).not.toMatch(/<a[^>]*data-testid="text-lead-rec1"/);
});

test("a lead with no phone has no call or text control", () => {
  const html = renderToStaticMarkup(
    <LeadContactActions opportunity={{ id: "rec2", name: "No phone" }} />,
  );
  expect(html).toBe("");
});
