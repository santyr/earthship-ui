**Status update (2026-10-05):** WeatherNext access request submitted; approval pending. The revised project end state is WeatherNext 3 as the sole external forecast provider after qualification; Open-Meteo remains only as a temporary migration control.

# WeatherNext 3 — operator onboarding and connection checklist

**Prepared:** 2026-09-30. This is a setup plan, not a completed account configuration. Public references are in `docs/operations/weathernext-sources.md`.

## What you are connecting

The project will read Google's already-generated WeatherNext forecast datasets and run a small local adaptation model on your existing machine. Do not deploy a global weather model, rent a GPU, subscribe to Maps Weather, or upload your household sensor database for this plan.

Google currently does not charge an access fee for the experimental data, although its terms allow a later fee with at least one month's prior written notice. Individual access does not require an existing paid Cloud contract. Platform usage is a separate issue. [S5, S9]

The default selected source is:

```text
gs://weathernext3_statistics_spatial/weathernext_3_0_0_statistics/zarr/
```

The backend must preserve the no-billing-project policy described in the design. No alternative that incurs charges is authorized merely by an access error.

## 1. Choose the Google account and a project

Use an account you control long-term. Open Google Cloud Console and create a dedicated project with a recognizable name such as `earthship-weather-research`; the actual project ID must be globally unique. An existing appropriately restricted project is also possible.

The preferred pilot does not need billing linked. Do not activate paid services just because a general Cloud tutorial offers a trial. If your account is already billed, isolate the project and still prohibit requester billing in the collector. Save the project ID; it is not a secret.

## 2. Create the worker identity before requesting data access

In the selected project, open **IAM & Admin → Service Accounts → Create service account**. Suggested account name: `weathernext-reader`. Do not grant project Owner or Editor. Creating the identity is distinct from granting it access to Google's dataset. [S10]

Copy the full identity, resembling:

```text
weathernext-reader@YOUR_PROJECT_ID.iam.gserviceaccount.com
```

Do not confuse this with your personal login. Both identities should be explicitly included in the data request so the later systemd worker is not dependent on an interactive browser session.

## 3. Submit the WeatherNext access form

Start from Google's access guide [S9], then choose its Data Request Form [S11]. Enter your real personal account email, name, and residence details. Add the worker address to the optional additional service/group-account field. An unaffiliated individual can use the form's N/A organization option. Select WeatherNext 3 on Google Cloud Storage; the form currently treats platform preferences as informational. [S11]

Google gives a typical review time of 5–7 business days, not a guaranteed deadline. [S9]

Save the submitted identities and approval message privately. Do not upload approval correspondence or credentials into the public repository.

## 4. Clarify the intended operational use

For a support enquiry to `weathernext@google.com`, this wording describes the proposed project; it is not a legal conclusion or a claim that Google has approved it:

> I am an individual building a private, noncommercial research system for an off-grid home. I would like to read WeatherNext 3's precomputed statistics, combine them locally with my own weather-station and energy measurements, preserve forecast/outcome pairs, and train site-specific weather corrections after targets become historical. Initial use is shadow evaluation with no equipment-control authority or resale. Can you confirm the permitted use for private forecast comparison and, after validation, informational household energy/thermal planning? I will not publicly redistribute live source forecasts. Please clarify any additional restrictions on private caching, local model training, or derived displays for this use.

The terms contain experimental/consumer-use disclaimers. Record Google's reply before approving an operational promotion. Read the actual applicable terms and attribution requirements, not just this packet. [S4, S5]

## 5. Install credentials privately on the chosen host

Prefer existing keyless workload authentication when your infrastructure supports it without introducing unnecessary services. For a standalone home Linux worker, a dedicated service-account JSON key is a practical fallback, but it is a sensitive long-lived credential.

Create a private directory such as `~/.config/earthship-weather/` with mode 700. Store the credential there with mode 600, owned by the account running the worker. The developer should pass its path through the private service environment, conventionally `GOOGLE_APPLICATION_CREDENTIALS`, and verify that the chosen reader actually uses the approved identity.

Never paste the JSON into ChatGPT, Codex prompts, issues, commits, screenshots, browser config, or logs. Do not place it inside `public/`, `config.json`, or `VITE_*` configuration. Restrict its permissions, revoke unused keys, and document rotation/revocation. The code only needs the local path, not the key copied into source.

Grant only the permissions proven necessary by the selected backend. For direct reads from Google's allowlisted bucket, granting your worker broad storage permissions in your own project does not grant access to Google's bucket. Approval for your personal account also does not prove approval for the worker account.

## 6. Run the bounded connection proof with the developer

The developer creates an isolated Python environment and pins a tested reader stack. First read one real value, one run, and one native cell. Then qualify both grids and the selected horizon.

Accept the connection only when the report contains: actual worker identity, source run/valid times, units, site/cell selection, a nonempty value, bytes transferred, elapsed time, memory peak, and confirmation that no billing project was supplied. Authentication success by itself is insufficient.

Use the real site from OpenHAB's Regional configuration. Do not use the browser's estimated Denver location. Do not copy a documentation example's city or obsolete forecast prefix.

If access fails, distinguish wrong identity, pending allowlist, missing object, incompatible metadata, and a payment requirement. A payment requirement stops the pilot. It is not permission to enable Requester Pays.

## 7. Approve collection only after the proof

New services are user-level and installed disabled. At the attended enablement, confirm:

- Only the new private archive and three new shadow/status Items may be written.
- Original Open-Meteo forecasts, energy safety rules, and notifications remain unchanged.
- Runtime limits, archive backup, and rollback have been rehearsed.

Then allow normal scheduled collection and review its first natural issue. Do not fabricate past publication times or treat a forced manual test as a scheduled reliability result.

## Alternative only when needed: Earth Engine

When direct GCS statistics extraction is too inefficient, the developer can propose Earth Engine point extraction. Register the Cloud project for eligible noncommercial use, enable the Earth Engine API, and use the Community tier rather than paid deployment. Google currently specifies 150 EECU-hours per month for verified noncommercial projects; eligibility verification is separate from WeatherNext's dataset allowlist. [S3]

The adapter must use the same archive/provenance contract and be tested with the worker identity. Do not enable BigQuery or Cloud compute merely as an automatic fallback.

## What to give the coding agent

Provide the planning packet, project ID, worker email, access-approval status, chosen host/user, and the **path** to the private credential. Let the agent discover existing OpenHAB/database access through the established host configuration. Do not supply raw passwords or keys in the prompt.

Your direct work should mainly be account consent, the access request, private credential placement, and attended enablement. Data extraction, tests, schema normalization, models, dashboards, and release reports belong to the implementation tasks.