/**
 * Regression fixtures for the greeting helpers — every real-world name shape
 * Ryan has seen produce a bug. Runs under `yarn test`.
 */
import {
  buildSalutation,
  looksLikeBusiness,
  personalFirstName,
  stripLeadingGreeting,
} from "../greeting.js";

const cases = [];
const eq = (got, want, label) => cases.push([label, got, want]);

// looksLikeBusiness
eq(looksLikeBusiness("Tristan Construction LLC"), true, "biz: Tristan Construction LLC");
eq(looksLikeBusiness("MRB Investments LLC"), true, "biz: MRB Investments LLC");
eq(looksLikeBusiness("Backyard Living"), true, "biz: Backyard Living");
eq(looksLikeBusiness("Miller and Associates"), true, "biz: Miller and Associates");
eq(looksLikeBusiness("Smith & Jones"), true, "biz: Smith & Jones");
eq(looksLikeBusiness("Ron Lee Homes"), true, "biz: Ron Lee Homes");
eq(looksLikeBusiness("John Smith"), false, "person: John Smith");
eq(looksLikeBusiness("Grzegorz Pomietlarz"), false, "person: single-word-ish name");
eq(looksLikeBusiness(""), false, "empty");
eq(looksLikeBusiness(null), false, "null");

// personalFirstName
eq(personalFirstName("John Smith"), "John", "first: John Smith");
eq(personalFirstName("Tristan Construction LLC"), null, "first: business → null");
eq(personalFirstName("MRB Investments LLC"), null, "first: MRB business → null");
eq(personalFirstName(""), null, "first: empty");
eq(personalFirstName("  Anna-Marie Doe"), "Anna-Marie", "first: hyphenated");

// buildSalutation — tries each person-name candidate in order, skipping businesses
eq(
  buildSalutation(["John Smith", "Tristan Construction LLC"]),
  "Hi John,",
  "salute: decision_maker wins over business name",
);
eq(
  buildSalutation(["", "Tristan Construction LLC"]),
  "Hi there,",
  "salute: falls back to generic when name is a business",
);
eq(
  buildSalutation(["", "John Smith"]),
  "Hi John,",
  "salute: falls through to the next person-shaped candidate",
);
eq(
  buildSalutation(["MRB Investments LLC"], { verb: "Dear", generic: "Property Owner" }),
  "Dear Property Owner,",
  "salute: landlord letter generic for business owner",
);
eq(
  buildSalutation(["Grzegorz Pomietlarz"], { verb: "Dear", generic: "Property Owner" }),
  "Dear Grzegorz,",
  "salute: landlord letter uses real name",
);
eq(
  buildSalutation([null, null]),
  "Hi there,",
  "salute: everything blank → generic",
);

// stripLeadingGreeting
eq(
  stripLeadingGreeting("Hi Tristan,\n\nI'm Ryan with The Shirtless Handyman..."),
  "I'm Ryan with The Shirtless Handyman...",
  "strip: standard greeting",
);
eq(
  stripLeadingGreeting("Hello John!\nI'm Ryan..."),
  "I'm Ryan...",
  "strip: exclamation greeting",
);
eq(
  stripLeadingGreeting("Dear Property Owner,\n\nBody starts here."),
  "Body starts here.",
  "strip: dear greeting",
);
eq(
  stripLeadingGreeting("Good morning John,\nBody."),
  "Body.",
  "strip: good-morning greeting",
);
eq(
  stripLeadingGreeting("I'm Ryan with The Shirtless Handyman..."),
  "I'm Ryan with The Shirtless Handyman...",
  "strip: idempotent when no greeting present",
);
eq(stripLeadingGreeting(""), "", "strip: empty");
eq(stripLeadingGreeting(null), "", "strip: null");

test.each(cases)("%s", (_label, got, want) => {
  expect(got).toBe(want);
});
