# AI Report Analyzer

## Features
- Supports CSV and Excel files with up to **50k rows** for insight generation.
- Automatic upgrade to the **Pro** plan once a payment succeeds. The Pro plan
  allows up to **50 reports per month** with access valid for **30 days**. The
  status refreshes automatically without manual reloads. If the webhook fails to
  set the upgrade flag, the app now corrects it whenever it detects a valid Pro
  expiry timestamp. A "Payment successful" message appears once the upgrade takes
  effect. For testing, the subscription charge is set to **₹1**.
- Build custom charts using the new **Custom Insights** page. The page now
  supports Tableau-style multiselect fields for rows and columns along with
  calculated fields, groups and parameters.

## Environment Variables

Set the following variables before starting the app:

- `OPENAI_API_KEY` – your OpenAI API key.
- `RZP_SERVER` – URL of the Razorpay order server.
- `RZP_KEY_ID` – Razorpay key ID used by the Streamlit app.
- `RZP_KEY` – key for the Razorpay order server.
- `RZP_SECRET` – secret for the Razorpay order server.
- `RZP_WEBHOOK_SECRET` – webhook verification secret used by the server.
- `PRO_PRICE` – cost of the Pro subscription in rupees (default **1** for testing).
- `SMTP_SERVER` – hostname of your SMTP server.
- `SMTP_PORT` – port for SMTP (default **587**).
- `SMTP_USER` – username for SMTP authentication.
- `SMTP_PASSWORD` – password for SMTP authentication.
- `SMTP_SSL` – set to `1` to use SMTPS (optional).

Example `.env` section for sending mail via Gmail:

```env
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=465
SMTP_USER=your.address@gmail.com
SMTP_PASSWORD=your_app_password
SMTP_SSL=1
```

You can place these values in a `.env` file in the project root. Both the
Streamlit app and the background email scheduler load this file automatically.

Email recipients entered in the UI must be valid addresses. Invalid addresses
will be highlighted before sending or scheduling.

## Running Locally

Start the Streamlit UI:

```bash
streamlit run app.py
```

Run the Razorpay webhook/order server:

```bash
uvicorn razor_server.razor_server:app
```

To deliver scheduled emails, run the background scheduler in another process:

```bash
python email_scheduler.py
```
The scheduler requires a Firebase authentication token. Set it in the environment
as `FIREBASE_TOKEN` (or add it to `.env`).

## UID Based Storage

User records are stored in Firebase under `users/<uid>`. If you previously stored data keyed by email, create entries under the UID and copy the values over, then delete the old email-keyed nodes. This keeps all data in a single UID namespace.

## Firebase Security Rules

Configure your Realtime Database rules so each user can only read or write
their own record. Use the UID based path created by the application:

```json
{
  "rules": {
    "users": {
      "$uid": {
        ".read":  "auth != null && auth.uid == $uid",
        ".write": "auth != null && auth.uid == $uid"
      }
    }
  }
}
```

This ensures user data is accessible only to the authenticated account.
