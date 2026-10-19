# Public launch review — 19 October 2026

Prepared static Privacy Policy and Terms pages at frontend/public/privacy.html
and frontend/public/terms.html, with links in the app footer and connection panel.
The owner confirmed enasyazz@gmail.com may be used as the public contact.

These pages are drafts; do not merge or use their production URLs in the Google
consent screen yet. The owner confirmed the Gemini API currently uses the free
tier. Google’s Gemini API Additional Terms state that unpaid-service inputs and
outputs may be used to improve Google products and machine-learning technology,
and say not to submit sensitive, confidential or personal information.

Before public Gmail processing:

- The owner must configure the actual Gemini API project for paid-service data
  handling and confirm its applicable terms/settings. Merely having a Google
  Workspace, Gemini consumer subscription, or a paid Vercel plan is not this.
- Confirm Google API Services User Data Policy / Gmail restricted-scope Limited
  Use requirements, including restrictions on training generalized models and
  appropriate human access to email data. Paid billing alone is not Google OAuth
  verification and does not guarantee compliance.
- Finalize the Gemini processing/retention paragraph for the actual paid project
  configuration; then remove the draft notice and review the full policy.
- Complete any Google branding/domain verification, restricted-scope review and
  security-assessment requirements shown in the Google verification centre.
- Review public operational readiness, including rate/billing limits, deletion
  request handling and provider retention/backup arrangements. Do not promise
  immediate deletion from Google, provider backups, or logs.

Sources:
https://ai.google.dev/gemini-api/terms
https://developers.google.com/terms/api-services-user-data-policy

Verification completed: production frontend build; policy pages can be served
without login or API access; footer navigation works; no horizontal overflow at
1280, 390 or 320 pixels. No live Google settings, billing or production deployment
were changed for these draft pages.
