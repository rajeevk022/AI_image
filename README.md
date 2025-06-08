# AI Report Analyzer

## Environment Variables

Set the following variables before starting the app:

- `OPENAI_API_KEY` – your OpenAI API key.
- `RZP_SERVER` – URL of the Razorpay order server.
- `RZP_KEY_ID` – Razorpay key ID used by the Streamlit app.
- `RZP_KEY` – key for the Razorpay order server.
- `RZP_SECRET` – secret for the Razorpay order server.
- `RZP_WEBHOOK_SECRET` – webhook verification secret used by the server.

## Running Locally

Start the Streamlit UI:

```bash
streamlit run app.py
```

Run the Razorpay webhook/order server:

```bash
uvicorn razor_server.razor_server:app
```

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

The application saves the Firebase `idToken` returned at login and passes it to
every database read or write. If you adapt the code, make sure each
`db.child(...).get(token)` or `update(data, token)` call includes this token, or
the security rules above will reject the request.
