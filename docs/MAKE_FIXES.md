# Make changes Ryan has to make by hand

The app cannot edit Make scenarios. These are the gaps a read of the live
Leads table still shows, and the steps to close them in Make. None of them
send a message. None of them should retry a failed paid module.

Table: Leads (the same table the dashboard reads).

## 1. `contact confidence` is empty on every lead

The column exists. It is a single select: **High**, **Medium**, **Low**.
Nothing in Make writes it, so the app reads a blank on all 269 leads.
The app now writes it when Contact Finder runs. Leads that Make enriches
without going through the app stay blank until this mapping exists.

In the scenario that enriches a lead (the contact / classifier scenario):

1. Open the Airtable **Update a record** module that writes the lead.
2. Map a confidence value into the field named `contact confidence`.
3. Use only the existing options: `High`, `Medium`, or `Low`.
4. If the module has no confidence, leave the field blank. Do not write
   "unknown", a number, or a sentence.

## 2. `First message` barely gets filled

`First message` is long text. About 3 leads have it. The in-app outreach
writer stores the draft in `Draft Outreach Body`, `First message`, and
`First contact message` together, and only as a draft.

If a Make "write outreach" scenario is still in the picture:

1. Map the draft text into all three: `First message`, `First contact message`,
   and `Draft Outreach Body`.
2. Do not add a send, schedule, or Gmail/Twilio module after it.
3. If the scenario retries the AI module on an error, turn that retry off.

## 3. `Estimated job value` is sparse

This is a currency field. The app will not invent a dollar amount from a
permit. Leave it blank when there is no real number.

If a scenario already has a permit value and a reasoned estimate:

1. Write that number into `Estimated job value`.
2. Do not write ranges, "TBD", or text. The column is currency.
3. `Official project value` and `Estimated opportunity value` are formulas.
   Do not try to write those.

## 4. Add `Research failed` to Enrichment status, if the first failure is rejected

Enrichment status today is: Needs research, Researching, Contact found,
No contact found, Ready for research, Ready for outreach.

When a Perplexity or OpenAI call fails, the app writes **Research failed**
and the reason into Notes, and it does not try the call again. The write
uses Airtable's typecast, which can add the option if the token is allowed
to. If a run reports that the status write was rejected:

1. Open the Leads table, field `Enrichment status`.
2. Add the single-select option `Research failed`.
3. Do not add a Make error-handler that runs the research module again.

## 5. Don't let the classifier wipe a contact the app just found

The app sets, when it actually finds a public phone or email:

- `Contact Readiness` = `Contact Ready`
- `Enrichment status` = `Contact found`
- `Contact Verified Date` = the day it looked
- `Public Contact Evidence` starts with `Contact source: homeowner` or
  `Contact source: business`

When it looks and finds neither phone nor email:

- `Contact Readiness` = `Needs Public Contact`
- `Enrichment status` = `No contact found`

`Source URL` is only filled when the cell is empty, so a permit link is
not replaced by a research citation. The citation goes in
`Public Contact Evidence`.

If the classifier scenario runs after that and clears `Contact name`,
`Contact phone`, `Contact email`, `Owner`, `Owner Mailing Address`,
`contact confidence`, or `Contact Verified Date`, stop it from clearing
those fields. It can still set queue, score, and the other governed fields.

## 6. Homeowner vs business, if Make also looks up owners

For a residential permit, the app asks Perplexity for the assessor owner
and mailing address and stores:

- person or LLC name → `Contact name` and `Owner`
- mailing address → `Owner Mailing Address`
- `Contact source: homeowner` or `Contact source: business` as the first
  line of `Public Contact Evidence`

There is no separate "contact source" column. Please don't add one unless
you want the app updated to read it. Keep using that first line so the
Do Not Call reminder on the lead keeps working.

If Make's own contact scenario is still active, point the owner name at
`Contact name` as well as `Owner`. A name that only lands in `Owner`
does not show up as the decision maker.

## 7. What not to add

- No retry / error-handler route that calls Perplexity, OpenAI, or any
  other paid module again.
- No auto-send, auto-text, auto-dial, or "create a call" module.
- No new paid enrichment vendor. The app is using Perplexity and OpenAI,
  which are already connected.
