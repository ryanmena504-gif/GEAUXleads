import { isRepliedLead, repliedQueue, isReachable } from "../today.js";
import { buildDoorHangerRoute, isDoorHangerLead, zipOf } from "../doorHangers.js";
import { KEEP_MAIL_DOOR, disposition } from "../mailDoor.js";

describe("Today lists", () => {
  test("replied leads", () => {
    expect(isRepliedLead({ status: "Conversation started", outreach_status: "Replied" })).toBe(true);
    expect(isRepliedLead({ status: "New", outreach_status: "Estimate requested" })).toBe(true);
    expect(isRepliedLead({ status: "New", outreach_status: "Sent" })).toBe(false);
    expect(isRepliedLead({ status: "Lost", outreach_status: "Replied" })).toBe(false);
  });

  test("oldest reply first", () => {
    const q = repliedQueue([
      { id: "b", outreach_status: "Replied", date_replied: "2026-11-10" },
      { id: "a", outreach_status: "Replied", date_replied: "2026-08-25" },
      { id: "c", outreach_status: "Sent" },
    ]);
    expect(q.map((o) => o.id)).toEqual(["a", "b"]);
  });

  test("reachable = phone or email", () => {
    expect(isReachable({ phone: "(504) 517-2474" })).toBe(true);
    expect(isReachable({ email: "info@x.com" })).toBe(true);
    expect(isReachable({ name: "3219 Joseph St" })).toBe(false);
  });
});

describe("door-hanger route", () => {
  const items = [
    { id: "1", status: "New", source: "Permit", project_address: "925 Aline St, New Orleans, LA 70115" },
    { id: "2", status: "New", source: "Permit", project_address: "925 Aline St, New Orleans, LA 70115" },
    { id: "3", status: "New", source: "Permit", project_address: "3642 Constance St, New Orleans, LA 70115" },
    { id: "4", status: "New", source: "Permit", project_address: "3219 Joseph St, New Orleans, LA 70125" },
    { id: "5", status: "New", source: "Permit", project_address: "2122 State St" },
    { id: "6", status: "New", source: "Permit", project_address: "1 Main St 70115", phone: "5045551212" },
    { id: "7", status: "Disqualified", source: "Permit", project_address: "2 Main St 70115" },
    { id: "8", status: "New", source: "Website", project_address: "3 Main St 70115" },
    { id: "9", status: "New", source: "Permit Issued", project_address: "1805 Kerlerec St, New Orleans, LA 70116" },
  ];

  test("only open permit leads with an address and no contact", () => {
    expect(items.filter(isDoorHangerLead).map((o) => o.id)).toEqual(["1", "2", "3", "4", "5", "9"]);
  });

  test("grouped by ZIP, one stop per door, streets in order", () => {
    const route = buildDoorHangerRoute(items);
    expect(route.map((g) => g.zip)).toEqual(["70115", "70116", "70125", "No ZIP on the permit"]);
    expect(route[0].label).toBe("70115 · Uptown / Garden District");
    expect(route[0].stops.map((o) => o.id)).toEqual(["1", "3"]);
  });

  test("a no-contact interior job with a person is a stop even if it was passed", () => {
    const kept = {
      id: "kept",
      status: "Disqualified",
      outcome: "No usable contact",
      source: "Permit",
      project_address: "2100 Saint Charles Ave, New Orleans, LA 70130",
      project_type: "bathroom_remodel_tub_to_shower",
      contact_company: "Edward Rafidi",
    };
    expect(disposition(kept)).toBe(KEEP_MAIL_DOOR);
    expect(isDoorHangerLead(kept)).toBe(true);
    const route = buildDoorHangerRoute([...items, kept]);
    const zips = route.map((g) => g.zip);
    expect(zips).toContain("70130");
  });

  test("zipOf", () => {
    expect(zipOf("925 Aline St, New Orleans, LA 70115")).toBe("70115");
    expect(zipOf("2122 State St")).toBe(null);
  });
});
