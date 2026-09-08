/**
 * Regression fixtures for the greeting helpers. Not wired into a test
 * runner (the app has no jest config yet) — kept as documented cases
 * covering every real-world name shape Ryan has seen produce a bug.
 * Run manually with `node --experimental-vm-modules` after any change.
 */
import {
  buildSalutation,
  looksLikeBusiness,
  personalFirstName,
  stripLeadingGreeting,
} from "../greeting.js";

const eq = (a, b, label) => {
  const ok = a === b;
  console.log(ok ? "PASS" : "FAIL", label, `→ got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`);
  if (!ok) process.exitCode = 1;
};

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

// buildSalutation — falls through decision_maker → contact_name → owner_name → name
eq(
  buildSalutation({ decision_maker: "John Smith", name: "Tristan Construction LLC" }),
  "Hi John,",
  "salute: decision_maker wins over business name",
);
eq(
  buildSalutation({ decision_maker: "", name: "Tristan Construction LLC" }),
  "Hi there,",
  "salute: falls back to generic when name is a business",
);
eq(
  buildSalutation({ decision_maker: "", name: "John Smith" }),
  "Hi John,",
  "salute: uses name when it looks like a person",
);
eq(
  buildSalutation({ owner_name: "MRB Investments LLC" }, { verb: "Dear", generic: "Property Owner" }),
  "Dear Property Owner,",
  "salute: landlord letter generic for business owner",
);
eq(
  buildSalutation({ owner_name: "Grzegorz Pomietlarz" }, { verb: "Dear", generic: "Property Owner" }),
  "Dear Grzegorz,",
  "salute: landlord letter uses real name",
);
eq(
  buildSalutation({ decision_maker: null, name: null }),
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
