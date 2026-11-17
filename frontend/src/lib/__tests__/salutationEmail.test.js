/**
 * Greeting name must belong to the inbox it goes to (2026-11-16: the Decor
 * by Flora draft said "Hey Janet" to flora@decoratingden.com).
 */
import { buildSalutation, nameMatchesEmail } from "../greeting.js";

test("mismatched personal inbox falls back to Hi there", () => {
  expect(buildSalutation(["Janet"], { email: "flora@decoratingden.com" })).toBe("Hi there,");
});

test("matching personal inbox keeps the name", () => {
  expect(buildSalutation(["Lazaro A Suarez"], { email: "lazaro@reverealtors.com" })).toBe("Hi Lazaro,");
  expect(buildSalutation(["Haley Smith"], { email: "HALEY@CRESCENTCITYLIVING.COM" })).toBe("Hi Haley,");
});

test("role inboxes and initials never block the name", () => {
  expect(nameMatchesEmail("Mike", "info@mzrenovations.com")).toBe(true);
  expect(nameMatchesEmail("Mike", "designer@signalhousedesigns.com")).toBe(true);
  expect(nameMatchesEmail("John Doe", "jd@example.com")).toBe(true);
});

test("first-initial + last-name inboxes match", () => {
  expect(nameMatchesEmail("John Smith", "jsmith@example.com")).toBe(true);
  expect(nameMatchesEmail("John Smith", "smithj@example.com")).toBe(true);
});

test("no email keeps the old behavior", () => {
  expect(buildSalutation(["Janet"])).toBe("Hi Janet,");
  expect(buildSalutation(["Janet"], { email: "" })).toBe("Hi Janet,");
});
