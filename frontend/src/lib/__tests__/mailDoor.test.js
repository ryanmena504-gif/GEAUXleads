import { disposition, KEEP_MAIL_DOOR, PASS_EXTERIOR, PASS_LLC_MULTIFAMILY, phoneTextMission } from "../mailDoor";
import { isDoorHangerLead } from "../doorHangers";

const tub = {
  id: "tub",
  status: "Disqualified",
  outcome: "No usable contact",
  source: "Permit",
  project_address: "2100 Saint Charles Ave, New Orleans, LA 70130",
  project_type: "bathroom_remodel_tub_to_shower",
  permit_description: "converting tub to shower",
  contact_company: "Edward Rafidi",
};

test("a disqualified tub-to-shower with a person is on the door-hanger route", () => {
  expect(disposition(tub)).toBe(KEEP_MAIL_DOOR);
  expect(isDoorHangerLead(tub)).toBe(true);
});

test("exterior-only and unnamed LLC multi-family stay off the route", () => {
  const roof = {
    ...tub,
    id: "roof",
    status: "New",
    outcome: "",
    project_type: "roof replacement",
    permit_description: "Replace the roof.",
    contact_name: "Ada Lovelace",
    contact_company: "",
  };
  const llc = {
    ...tub,
    id: "llc",
    status: "New",
    project_address: "2514 S Tonti St -Apt 2B",
    owner: "CLS Properties 12 LLC",
    contact_name: "CLS Properties 12 LLC",
    contact_company: "",
    applicant: "Feelgood Construction Company LLC",
  };
  expect(disposition(roof)).toBe(PASS_EXTERIOR);
  expect(disposition(llc)).toBe(PASS_LLC_MULTIFAMILY);
  expect(isDoorHangerLead(roof)).toBe(false);
  expect(isDoorHangerLead(llc)).toBe(false);
});

test("a wrong-trade pass is not pulled back onto the route", () => {
  expect(isDoorHangerLead({ ...tub, outcome: "Wrong trade" })).toBe(false);
});

test("permit leads are not put in the call or text queue without consent", () => {
  const withPhone = { ...tub, status: "New", contact_phone: "504-231-8890", daily_mission: "Call Today" };
  expect(phoneTextMission(withPhone)).toBe("Research First");
  expect(phoneTextMission({ ...withPhone, contact_email: "ada@example.com", daily_mission: "Send Text" })).toBe("Send Email");
  expect(phoneTextMission({ ...withPhone, sms_permission: "Yes" })).toBe("Call Today");
  expect(phoneTextMission(tub, "Call Today")).toBe("Visit Property");
});
