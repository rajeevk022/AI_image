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
