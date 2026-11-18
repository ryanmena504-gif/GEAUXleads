import { ADDRESS_PLACEHOLDER, businessMailingAddress, withCanSpam } from "../canspam";
import { buildFirstDraft } from "../../components/OpenInMessages";

test("a cold email has an opt-out line and no invented street", () => {
  const previous = process.env.REACT_APP_BUSINESS_MAILING_ADDRESS;
  delete process.env.REACT_APP_BUSINESS_MAILING_ADDRESS;
  const body = withCanSpam("Hi Ada, I do showers.");
  expect(body).toContain('reply "unsubscribe"');
  expect(body).toContain(ADDRESS_PLACEHOLDER);
  expect(body).not.toMatch(/Magazine St|70115/);
  expect(businessMailingAddress()).toBe(ADDRESS_PLACEHOLDER);

  process.env.REACT_APP_BUSINESS_MAILING_ADDRESS = "PO Box 100, New Orleans, LA 70112";
  const addressed = withCanSpam("Hi Ada.");
  expect(addressed).toContain("PO Box 100");
  expect(withCanSpam(addressed)).toBe(addressed);

  const draft = buildFirstDraft(
    { decision_maker: "Ada Lovelace", email: "ada@example.com", project_type: "shower remodel" },
    {},
  );
  expect(draft.body).toContain('reply "unsubscribe"');
  expect(draft.body).toContain("PO Box 100");

  if (previous === undefined) delete process.env.REACT_APP_BUSINESS_MAILING_ADDRESS;
  else process.env.REACT_APP_BUSINESS_MAILING_ADDRESS = previous;
});
