import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import CallLeadButton, { callConfirmText, leadOptedOut } from "../CallLeadButton";

const linkCls = "inline-flex items-center gap-1.5";

test("Call sits next to Text and uses a button, not a tel link", () => {
  const opp = { id: "rec1", name: "Bath remodel", phone: "(504) 555-0142" };
  const html = renderToStaticMarkup(
    <div>
      <CallLeadButton opportunity={opp} className={linkCls} />
      <a href="sms:5045550142">Text</a>
    </div>,
  );
  expect(html).toContain('data-testid="call-lead-rec1"');
  expect(html).toContain("Call</button>");
  expect(html.indexOf("Call</button>")).toBeLessThan(html.indexOf(">Text<"));
  expect(html).not.toContain("tel:");
  expect(html).toContain("sms:5045550142");
});

test("an opted-out lead gets no Call button", () => {
  const html = renderToStaticMarkup(
    <CallLeadButton
      opportunity={{ id: "rec2", phone: "5045550199", outreach_status: "Do Not Contact" }}
    />,
  );
  expect(html).toBe("");
  expect(leadOptedOut({ risk_flags: ["Opted out"], phone: "5045550100" })).toBe(true);
  expect(leadOptedOut({ status: "do_not_contact", phone: "5045550100" })).toBe(true);
  expect(leadOptedOut({ phone: "5045550100", name: "Pat" })).toBe(false);
});

test("a homeowner number asks for a Do Not Call check before the call", () => {
  const text = callConfirmText({
    name: "Ada",
    phone: "(504) 555-0134",
    dnc_check_required: true,
  });
  expect(text).toMatch(/Check the Do Not Call list/i);
  expect(text).toMatch(/rings first/i);
  expect(callConfirmText({ name: "Ada" })).not.toMatch(/Do Not Call list/i);
});
