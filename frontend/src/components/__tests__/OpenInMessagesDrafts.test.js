import { buildFirstDraft, buildFollowUpDraft } from "../OpenInMessages";

const cohn = {
  lane: "market_capture",
  decision_maker: "Lazaro A Suarez",
  email: "lazaro@reverealtors.com",
  project_address: "8713 Cohn St, New Orleans, LA 70118",
  notes: "Lane-1 stale listing (2026-11-09, days on Zillow): ...",
  draft_outreach_body:
    "Hi Lazaro — Ryan, the Shirtless Handyman here in New Orleans. Saw your Cohn listing — a 1939 home cut $50,000 since September, and I had one thought for it: a seamless microcement bath and floor package. Zero grout, fully waterproof, goes over existing tile, no demo day.",
};

test("listing-agent first touch uses the buyer-side pitch", () => {
  const d = buildFirstDraft(cohn, {});
  expect(d.body.startsWith("Hi Lazaro,\nRyan with The Shirtless Handyman.")).toBe(true);
  expect(d.body).toContain("If a buyer on Cohn St, or any listing, wants the bath redone");
  expect(d.body).not.toMatch(/\$50,000|cut|no demo day/);
});

test("stored drafts get the conditional tile line", () => {
  const d = buildFirstDraft(
    {
      decision_maker: "Pat Lee",
      email: "pat@example.com",
      draft_outreach_body: "Hi Pat — I do microcement showers. Zero grout, fully waterproof, goes right over existing tile, no demo day. Want a number?",
    },
    {},
  );
  expect(d.body).toContain("often goes over existing tile once I've checked it's solid");
  expect(d.body).not.toMatch(/no demo day/);
});

const flora = {
  lane: "partner",
  decision_maker: "Janet",
  email: "flora@decoratingden.com",
  outreach_attempt: 1,
  message_sent_date: "2026-09-14T23:58:14.778Z",
  draft_outreach_generated_at: "2026-10-09T08:35:00.000Z",
  draft_outreach_body: "Hey Janet — following up after the cork kitchen. Got any kitchens or baths coming up that need seamless surfaces?",
};

test("follow-up text never greets Janet at flora@", () => {
  const d = buildFollowUpDraft(flora, {});
  expect(d.kind).toBe("text");
  expect(d.body.startsWith("Hi there — ")).toBe(true);
  expect(d.body).not.toMatch(/Janet/);
});

test("follow-up text without a fresh staged draft offers photos or a sample board", () => {
  const d = buildFollowUpDraft(
    { ...flora, draft_outreach_body: "", decision_maker: "Flora" },
    { recent_job_area: "Metairie" },
  );
  expect(d.body).toContain("Hi Flora — ");
  expect(d.body).toContain("Finished a seamless microcement shower in Metairie last week. Want me to send a couple photos or drop a sample board by?");
});

test("an already-sent first message is not re-sent as the follow-up", () => {
  const d = buildFollowUpDraft(
    { ...cohn, outreach_attempt: 1, message_sent_date: "2026-11-16T03:00:38Z" },
    {},
  );
  expect(d.body).not.toMatch(/Saw your Cohn listing/);
  expect(d.body).toMatch(/sample board/);
});

test("touch 3 email gives the reader something to answer", () => {
  const d = buildFollowUpDraft({ ...flora, outreach_attempt: 2 }, {});
  expect(d.kind).toBe("email");
  expect(d.body).toMatch(/send a couple photos or drop a sample board by\?/);
  expect(d.body).not.toMatch(/Sent a note last week/);
});
