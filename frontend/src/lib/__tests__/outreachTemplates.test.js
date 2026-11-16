import {
  softenDraftClaims,
  mentionsListingPressure,
  isListingAgentLead,
  buildListingAgentBody,
  streetName,
  recentWorkLine,
  TILE_CONDITIONAL,
} from "../outreachTemplates.js";

describe("softenDraftClaims", () => {
  test.each([
    "Zero grout, fully waterproof, goes over existing tile, no demo day. If a buyer",
    "zero grout to scrub, fully waterproof, goes right over existing tile, no demo day. If you're",
    "fully waterproof, goes over existing tile, no demo day, so it's a clean upgrade",
    "fully waterproof, goes over existing tile. Open to a chat?",
  ])("%s", (text) => {
    const out = softenDraftClaims(text);
    expect(out).toContain(TILE_CONDITIONAL);
    expect(out).not.toMatch(/no demo day/i);
    expect(out).not.toMatch(/goes (right )?over existing tile[,.]/i);
  });

  test("idempotent and leaves conditional copy alone", () => {
    const once = softenDraftClaims("It goes over existing tile, no demo day.");
    expect(softenDraftClaims(once)).toBe(once);
    const conditional = "often right over the existing tile once I've checked it's solid.";
    expect(softenDraftClaims(conditional)).toBe(conditional);
  });

  test("empty input", () => {
    expect(softenDraftClaims("")).toBe("");
    expect(softenDraftClaims(null)).toBe("");
  });
});

describe("listing-agent drafts", () => {
  const cohn = {
    project_address: "8713 Cohn St, New Orleans, LA 70118",
    notes: "Lane-1 stale listing (2026-11-09, days on Zillow): $275,000 ...",
    draft_outreach_body:
      "Hi Lazaro — Ryan, the Shirtless Handyman here in New Orleans. Saw your Cohn listing — a 1939 home cut $50,000 since September, and I had one thought for it.",
  };

  test("price-cut and days-on-market copy is detected", () => {
    expect(mentionsListingPressure(cohn.draft_outreach_body)).toBe(true);
    expect(mentionsListingPressure("a 1966 home sitting 126 days with $24,000 in cuts")).toBe(true);
    expect(mentionsListingPressure("a 1920 Uptown place cut three times now")).toBe(true);
    expect(mentionsListingPressure("Happy to send photos.")).toBe(false);
  });

  test("listing leads are recognised", () => {
    expect(isListingAgentLead(cohn)).toBe(true);
    expect(isListingAgentLead({ draft_outreach_body: "Saw your Rosa listing — an as-is fixer-upper" })).toBe(true);
    expect(isListingAgentLead({ notes: "Permit 26-1234", draft_outreach_body: "Hey there" })).toBe(false);
  });

  test("new base pitch: buyer-side, no price talk, no remodel ask", () => {
    const body = buildListingAgentBody(cohn);
    expect(body).toBe(
      "Ryan with The Shirtless Handyman. I do seamless microcement baths and Venetian plaster around New Orleans. If a buyer on Cohn St, or any listing, wants the bath redone, I can quote it fast so it doesn't stall the deal. Happy to send photos.",
    );
    expect(mentionsListingPressure(body)).toBe(false);
  });

  test("streetName", () => {
    expect(streetName("8713 Cohn St, New Orleans")).toBe("Cohn St");
    expect(streetName("3235-3237 Vincennes Pl, New Orleans, LA")).toBe("Vincennes Pl");
    expect(streetName("")).toBe("");
  });
});

test("follow-up line only claims a recent job when one is set", () => {
  expect(recentWorkLine("Metairie")).toBe(
    "Finished a seamless microcement shower in Metairie last week. Want me to send a couple photos or drop a sample board by?",
  );
  expect(recentWorkLine("")).not.toMatch(/last week/);
  expect(recentWorkLine("")).toMatch(/sample board/);
});
