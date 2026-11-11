/**
 * Contact phone / Contact email are read before the empty Phone number
 * and Email columns. Email Now uses pickEmail, so a lead whose only
 * address is Contact email must still count as having an email.
 */
import { hasContactChannel, pickEmail, pickPhone } from "../contact.js";

test("pickEmail uses Contact email before the Email column", () => {
  const both = {
    contact_email: "lazaro@reverealtors.com",
    email: "old@legacy.test",
    email_alt: "other@legacy.test",
  };
  expect(pickEmail(both)).toBe("lazaro@reverealtors.com");
});

test("pickEmail falls back only when Contact email is blank", () => {
  expect(pickEmail({
    contact_email: "",
    email: null,
    email_alt: "randy_leblanc@icloud.com",
  })).toBe("randy_leblanc@icloud.com");
  expect(pickEmail({ email: "  ", contact_email: null, email_alt: null })).toBeNull();
});

test("pickPhone uses Contact phone before Phone number", () => {
  expect(pickPhone({
    contact_phone: "(504) 251-5302",
    phone: "504-000-1111",
    phone_number: "504-000-2222",
    phone_alt: "504-000-3333",
  })).toBe("(504) 251-5302");
  expect(pickPhone({
    contact_phone: null,
    phone: null,
    phone_number: "(504) 416-3737",
  })).toBe("(504) 416-3737");
});

test("a contact-only lead still counts as reachable", () => {
  const lead = {
    contact_email: "office@greigehome.com",
    email: "",
    email_alt: "",
    contact_phone: "",
    phone: "",
    phone_alt: "",
  };
  expect(hasContactChannel(lead)).toBe(true);
  expect(pickEmail(lead)).toBe("office@greigehome.com");
  expect(hasContactChannel({ email: "", phone: "" })).toBe(false);
});
