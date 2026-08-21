# Sales (self-hosted first)

Invoice until Stripe is wired. Do not sell until [ip-assignment.md](ip-assignment.md)
is signed. While that paper is outstanding, run [vendor-ops.md](vendor-ops.md)
(mailbox, dry-run license issue, GHCR inventory).

**Contact:** licensing@opsdevcode.com (change this when the mailbox exists).

## SKUs (starting prices — edit before the first quote)

| SKU | Term | Includes | Starting price |
| --- | --- | --- | --- |
| `pilot` | 90 days | Control plane on **one** cluster, no operator | $8,000 |
| `annual` | 12 months | Control plane, org-wide clusters | $40,000 / year |

Add-ons (quote separately after two customers ask): operator, hosted Backstage.

Support: email, business hours. Not 24/7.

## Manual entitlement (same week as first payment)

1. Invoice (or Stripe Payment Link you create in the dashboard).
2. After funds clear, issue the file:

   ```bash
   python3 scripts/issue_repave_license.py \
     --organization customer-github-org \
     --sku annual \
     --expires 2027-08-20 \
     --out ./customer-org-license.json
   ```

3. GitHub org **opsdevcode** → Packages → each image → Package settings →
   add the customer org or a machine user as **Reader**.
4. Email `license.json` + [install.md](install.md) + [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md).

Do not give them `git clone` on `opsdevcode/repave`.

## Hosted SaaS

Not in v1. One paying self-hosted customer first, then a cluster you operate.
