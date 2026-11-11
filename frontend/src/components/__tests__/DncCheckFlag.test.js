import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { ContactSourceChip, DncCheckFlag } from "../DncCheckFlag";

test("homeowner phone shows a Do Not Call reminder and does not offer a dialer", () => {
  const html = renderToStaticMarkup(
    <DncCheckFlag opp={{ id: "rec1", dnc_check_required: true, phone: "(504) 555-0134" }} />,
  );
  expect(html).toContain('data-testid="dnc-check-rec1"');
  expect(html).toMatch(/Check the Do Not Call list before calling or texting/i);
  expect(html).not.toContain("<a ");
  expect(html).not.toContain("tel:");
  expect(html).not.toContain("sms:");
});

test("a business number does not show the reminder", () => {
  const html = renderToStaticMarkup(
    <DncCheckFlag opp={{ id: "rec2", dnc_check_required: false }} />,
  );
  expect(html).toBe("");
});

test("contact source chip distinguishes homeowner from business", () => {
  const home = renderToStaticMarkup(
    <ContactSourceChip opp={{ id: "rec3", contact_source: "homeowner" }} />,
  );
  expect(home).toContain("Homeowner");
  const biz = renderToStaticMarkup(
    <ContactSourceChip opp={{ id: "rec3", contact_source: "business" }} />,
  );
  expect(biz).toContain("Business contact");
});
