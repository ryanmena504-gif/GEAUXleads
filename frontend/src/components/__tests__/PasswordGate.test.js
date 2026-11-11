import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { PasswordGate } from "../PasswordGate";

test("a missing server password shows the Render steps and the variable name", () => {
  const html = renderToStaticMarkup(
    <PasswordGate mode="unconfigured" message="APP_PASSWORD is not set." onSubmit={() => {}} />,
  );
  expect(html).toContain('data-testid="password-setup"');
  expect(html).toContain("APP_PASSWORD");
  expect(html).toContain("Render");
  expect(html).toContain("geauxleads.onrender.com");
  expect(html).not.toContain('data-testid="password-input"');
});

test("the sign-in form is what shows when a password is required", () => {
  const html = renderToStaticMarkup(
    <PasswordGate mode="ask" message="That password doesn't match the one on the server." onSubmit={() => {}} />,
  );
  expect(html).toContain('data-testid="password-input"');
  expect(html).toContain("password-error");
  expect(html).toContain("match the one on the server");
});
