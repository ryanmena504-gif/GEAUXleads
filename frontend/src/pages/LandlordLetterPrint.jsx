import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { fetchUserSettings } from "@/hooks/useUserSettings";

/**
 * LandlordLetterPrint — print-optimized letter spread.
 *
 * URL:  /discovery/landlords/print?ids=rec1,rec2,rec3
 *
 * Each landlord gets a full 8.5x11 letter on its own printed page. The
 * screen preview shows the same content, stacked vertically. `@media print`
 * hides all UI chrome and forces `page-break-after: always` between
 * letters so browser Print produces exactly one letter per physical
 * page (or PDF page).
 *
 * The sender identity — Ryan's name, phone, and business return address —
 * comes from the user-settings backend (`/api/settings/user`). If the
 * return address is not yet set in Settings, the letter falls back to a
 * neutral "The Shirtless Handyman · New Orleans, LA" line so nothing
 * looks broken.
 */

const today = () =>
  new Date().toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
  });

// Split a multi-line mailing address into an array of clean lines.
const splitAddress = (v) =>
  (v || "")
    .split(/\r?\n|,\s*/)
    .map((s) => s.trim())
    .filter(Boolean);

const buildLetterBody = ({ owner_name, sender_name }) => {
  const first = (owner_name || "there").split(" ")[0];
  return [
    `Dear ${first},`,
    "",
    `I'm ${sender_name || "Ryan Mena"} with The Shirtless Handyman. I saw your name on the New Orleans Commercial STR license registry and wanted to reach out.`,
    "",
    `Between guests and between tenants, a rental unit needs someone dependable — patch, paint, plaster, punch-list, small repairs before the next check-in. I'm a one-call fix for all of it. No coordinating three trades, no waiting on estimates from four contractors. Text me a photo of what needs attention and I'll tell you what it'll cost and when I can be there.`,
    "",
    `I'm licensed, insured, and local. My specialty is seamless finishes — microcement, lime plaster, waterproof grout-free showers — but I handle everyday turnover work just as well. If your current handyman is stretched thin or you're tired of chasing quotes, I hope you'll keep me in mind.`,
    "",
    `Give me a call anytime — the number below rings my cell directly.`,
    "",
    "Sincerely,",
    "",
    "",
    sender_name || "Ryan Mena",
    "The Shirtless Handyman",
  ].join("\n");
};

const Letter = ({ landlord, sender }) => {
  const address = landlord.mailing_address || landlord.property_address || "";
  const addressLines = splitAddress(address);
  const senderName = sender?.sender_name?.trim() || "Ryan Mena";
  const senderPhone = sender?.sender_phone?.trim() || "";
  const senderEmail = sender?.sender_email?.trim() || "";
  const returnAddressLines = splitAddress(sender?.sender_mailing_address);
  const returnAddressDefault = ["The Shirtless Handyman", "New Orleans, LA"];
  const returnAddress = returnAddressLines.length > 0 ? returnAddressLines : returnAddressDefault;
  const body = buildLetterBody({ owner_name: landlord.owner_name, sender_name: senderName });

  return (
    <div
      className="letter"
      data-testid={`landlord-letter-${landlord.id}`}
    >
      {/* Sender block (top-left) */}
      <div className="letter-sender">
        {returnAddress.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
        {senderPhone && <div>{senderPhone}</div>}
        {senderEmail && <div>{senderEmail}</div>}
      </div>

      {/* Date */}
      <div className="letter-date">{today()}</div>

      {/* Recipient block */}
      <div className="letter-recipient">
        <div>{landlord.owner_name || "Property Owner"}</div>
        {addressLines.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>

      {/* Body */}
      <pre className="letter-body">{body}</pre>

      {/* Footer / signature line */}
      <div className="letter-footer">
        <div>{senderName} · The Shirtless Handyman</div>
        {senderPhone && <div>{senderPhone}</div>}
        {senderEmail && <div>{senderEmail}</div>}
      </div>
    </div>
  );
};

const LandlordLetterPrint = () => {
  const [params] = useSearchParams();
  const idsParam = params.get("ids") || "";
  const [items, setItems] = useState([]);
  const [sender, setSender] = useState({});
  const [loading, setLoading] = useState(true);

  const idList = useMemo(
    () => idsParam.split(",").map((s) => s.trim()).filter(Boolean),
    [idsParam],
  );

  useEffect(() => {
    let mounted = true;
    Promise.all([
      api.discoveryLandlords({ status: "all", ids: idList.length ? idList : null }),
      fetchUserSettings().catch(() => ({})),
    ])
      .then(([r, s]) => {
        if (!mounted) return;
        setItems(r?.items || []);
        setSender(s || {});
        setLoading(false);
      })
      .catch(() => mounted && setLoading(false));
    return () => { mounted = false; };
  }, [idList]);

  const triggerPrint = () => window.print();

  return (
    <div className="print-root">
      {/* Screen-only toolbar. Hidden on print. */}
      <div className="print-toolbar no-print">
        <div className="print-toolbar-inner">
          <div>
            <div className="print-toolbar-title">
              {loading ? "Loading letters…" : `${items.length} landlord letter${items.length === 1 ? "" : "s"}`}
            </div>
            <div className="print-toolbar-sub">
              Each letter is a separate printed page. Use your browser&apos;s
              <strong> Print → Save as PDF</strong> for a mail-merge file, or
              print directly to send now.
            </div>
          </div>
          <button
            type="button"
            onClick={triggerPrint}
            data-testid="print-letters-btn"
            className="print-btn"
          >
            Print now
          </button>
        </div>
      </div>

      <div className="letters">
        {items.map((l) => (
          <Letter key={l.id} landlord={l} sender={sender} />
        ))}
        {!loading && items.length === 0 && (
          <div className="print-empty">No letters to render — no landlord ids were passed.</div>
        )}
      </div>

      {/* Inline print styles keep the whole letter template self-contained. */}
      <style>{`
        .print-root {
          background: #f4efe7;
          min-height: 100vh;
          padding-bottom: 4rem;
          font-family: "Times New Roman", Georgia, serif;
        }
        .print-toolbar {
          position: sticky;
          top: 0;
          z-index: 40;
          background: #1c1c1c;
          color: #f4efe7;
          padding: 12px 20px;
          border-bottom: 1px solid #333;
        }
        .print-toolbar-inner {
          max-width: 8.5in;
          margin: 0 auto;
          display: flex;
          align-items: center;
          justify-content: space-between;
          gap: 16px;
        }
        .print-toolbar-title { font-weight: 600; font-size: 14px; letter-spacing: 0.5px; }
        .print-toolbar-sub { font-size: 11px; opacity: 0.7; max-width: 500px; margin-top: 2px; }
        .print-btn {
          background: #b28a3a;
          color: #f4efe7;
          border: none;
          padding: 8px 18px;
          font-weight: 600;
          font-size: 13px;
          border-radius: 4px;
          cursor: pointer;
          font-family: inherit;
        }
        .print-btn:hover { background: #c69b41; }
        .letters { padding: 24px 0; }
        .letter {
          width: 8.5in;
          min-height: 11in;
          margin: 0 auto 32px auto;
          padding: 1in;
          background: #fdfaf3;
          box-shadow: 0 2px 8px rgba(0,0,0,0.08);
          color: #1c1c1c;
          font-size: 12pt;
          line-height: 1.55;
          box-sizing: border-box;
          display: block;
        }
        .letter-sender {
          font-size: 10pt;
          line-height: 1.35;
          margin-bottom: 40px;
          color: #333;
        }
        .letter-date {
          margin-bottom: 30px;
        }
        .letter-recipient {
          margin-bottom: 40px;
        }
        .letter-recipient div { line-height: 1.35; }
        .letter-body {
          white-space: pre-wrap;
          font-family: inherit;
          font-size: 12pt;
          line-height: 1.55;
          margin: 0;
        }
        .letter-footer {
          margin-top: 40px;
          padding-top: 12px;
          border-top: 1px solid #d8ceb7;
          font-size: 9.5pt;
          color: #555;
          line-height: 1.4;
        }
        .print-empty {
          max-width: 500px;
          margin: 60px auto;
          padding: 32px;
          background: #fdfaf3;
          border-radius: 6px;
          text-align: center;
          color: #555;
        }

        @media print {
          .no-print, .print-toolbar { display: none !important; }
          /* Hide the app chrome (sidebar, bottom nav) so only the letter
             pages print. Selectors target the AppLayout wrappers. */
          aside[data-testid="sidebar"],
          nav[data-testid="bottom-nav"],
          .bottom-nav { display: none !important; }
          html, body { background: #ffffff !important; margin: 0 !important; padding: 0 !important; }
          .print-root { background: #ffffff; padding: 0; }
          .letters { padding: 0; }
          .letter {
            margin: 0;
            box-shadow: none;
            background: #ffffff;
            page-break-after: always;
            width: 100%;
            min-height: 0;
            padding: 0.75in;
          }
          .letter:last-child { page-break-after: auto; }
          @page { size: letter; margin: 0.5in; }
        }
      `}</style>
    </div>
  );
};

export default LandlordLetterPrint;
