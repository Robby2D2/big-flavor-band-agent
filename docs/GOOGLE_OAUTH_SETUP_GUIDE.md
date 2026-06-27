# Google OAuth Setup Guide for BigFlavor Band Agent

This guide will walk you through setting up direct Google OAuth authentication for the BigFlavor frontend.

## Why Direct Google OAuth?

Instead of using a third-party service like Auth0, this setup connects directly to Google:
- Simpler configuration
- No monthly costs
- Fewer dependencies
- Direct control over authentication flow

## Step-by-Step Setup (10 minutes)

### Step 1: Create Google Cloud Project

1. Go to **https://console.cloud.google.com/**
2. Sign in with your Google account
3. Click the project dropdown at the top (may say "Select a project")
4. Click **"New Project"**
5. Fill in:
   - **Project name**: `BigFlavor Band Agent`
   - **Organization**: (leave as default or select your org)
6. Click **"Create"**
7. Wait for the project to be created, then select it

### Step 2: Configure OAuth Consent Screen

1. In the left sidebar, go to **"APIs & Services"** → **"OAuth consent screen"**
2. Select **"External"** user type (unless you have Google Workspace and want internal only)
3. Click **"Create"**
4. Fill in the required fields:
   - **App name**: `Big Flavor Band` (or your app name)
   - **User support email**: Select your email or create a Google Group
   - **Developer contact email**: Your email
5. Click **"Save and Continue"**
6. On **Scopes** page, click **"Add or Remove Scopes"**:
   - Select: `openid`, `email`, `profile`
   - Click **"Update"**
7. Click **"Save and Continue"**
8. On **Test users** page (if in testing mode):
   - Click **"Add Users"**
   - Add email addresses that can test the app
9. Click **"Save and Continue"**

### Step 3: Create OAuth Credentials

1. In the left sidebar, go to **"APIs & Services"** → **"Credentials"**
2. Click **"Create Credentials"** → **"OAuth client ID"**
3. Select **"Web application"** as the application type
4. Fill in:
   - **Name**: `BigFlavor Web Client`

   **Authorized JavaScript origins**:
   ```
   http://localhost:3000
   ```

   **Authorized redirect URIs**:
   ```
   http://localhost:3000/api/auth/callback
   ```

5. Click **"Create"**
6. A dialog will show your credentials - **copy these now**:
   - **Client ID**: `xxxx.apps.googleusercontent.com`
   - **Client Secret**: `GOCSPX-xxxx`

**Keep these private!** Don't share them publicly.

### Step 4: Update Your Environment File

Create or edit `frontend/.env.local`:

```env
# Google OAuth Configuration
GOOGLE_CLIENT_ID='your-client-id.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET='your-client-secret'

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=bigflavor
DB_USER=bigflavor
DB_PASSWORD=your_password_here

# Backend API (Python agent)
AGENT_API_URL=http://localhost:8000
```

**Example (with fake values):**
```env
GOOGLE_CLIENT_ID='123456789-abcdef.apps.googleusercontent.com'
GOOGLE_CLIENT_SECRET='GOCSPX-abcdefghijk'
```

Save the file!

### Step 5: Test Your Setup

1. Start the backend API:
   ```powershell
   python backend_api.py
   ```

2. In a new terminal, start the frontend:
   ```powershell
   cd frontend
   npm run dev
   ```

3. Open your browser to **http://localhost:3000**

4. You should see the BigFlavor home page

5. Click **"Sign In with Google"**

6. Select your Google account and authorize the app

7. After login, you should be redirected back to the app!

## Adding Production URLs

When you deploy to production, update Google Console:

1. Go to **APIs & Services** → **Credentials**
2. Click your OAuth client
3. Add your production URLs:

   **Authorized JavaScript origins**:
   ```
   http://localhost:3000
   https://yourdomain.com
   ```

   **Authorized redirect URIs**:
   ```
   http://localhost:3000/api/auth/callback
   https://yourdomain.com/api/auth/callback
   ```

4. Click **"Save"**

## Troubleshooting

### "redirect_uri_mismatch" error

**Problem**: Google shows an error about redirect URI mismatch

**Solution**:
- Go to Google Console → Credentials → Your OAuth client
- Make sure **"Authorized redirect URIs"** exactly matches: `http://localhost:3000/api/auth/callback`
- Check for trailing slashes or typos
- Wait a few minutes after changes for them to propagate

### "access_denied" error

**Problem**: Can't authorize the app

**Solution**:
- If app is in "Testing" mode, make sure your email is added as a test user
- Go to OAuth consent screen → Test users → Add your email

### "invalid_client" error

**Problem**: OAuth client configuration error

**Solution**:
- Double-check GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in `.env.local`
- Make sure there are no extra spaces or quotes
- Restart the frontend server after changing environment variables

### Login works but get "Unauthorized" in the app

**Problem**: Can log in but can't access features

**Solution**:
- Run the database migration if you haven't:
  ```powershell
  psql -U bigflavor -d bigflavor -f database/sql/migrations/05-create-users-table.sql
  ```
- Make sure the backend API is running
- Check the backend terminal for errors

## Publishing Your App

While in development, only test users you add can use the app. To allow anyone to sign in:

1. Go to **OAuth consent screen**
2. Click **"Publish App"**
3. Review the verification requirements:
   - Apps requesting sensitive scopes may need verification
   - Basic profile/email scopes usually don't need verification
4. Click **"Confirm"**

## Security Notes

### For Development
- The `.env.local` file is already in `.gitignore` (won't be committed)
- Keep your Client Secret private

### For Production
When you deploy to production:

1. **Update URLs** in Google Console:
   - Add your production domain to authorized origins and redirect URIs

2. **Use Environment Variables**:
   - Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET as environment variables
   - Never commit credentials to version control

3. **Enable HTTPS**:
   - Production should always use HTTPS
   - Google may require HTTPS for published apps

## What's Next?

After Google OAuth is set up, you can:

1. **Grant Editor Access** to users:
   ```sql
   UPDATE users SET role = 'editor' WHERE email = 'you@example.com';
   ```

2. **Monitor Usage**:
   - Google Console → APIs & Services → Dashboard
   - See API usage and quotas

## Quick Reference

### Google Cloud Console URLs
- **Console Home**: https://console.cloud.google.com/
- **Credentials**: https://console.cloud.google.com/apis/credentials
- **OAuth Consent**: https://console.cloud.google.com/apis/credentials/consent

### Environment Variables Checklist
- [ ] `GOOGLE_CLIENT_ID` - From Google Console credentials
- [ ] `GOOGLE_CLIENT_SECRET` - From Google Console credentials

### Google OAuth Settings Checklist
- [ ] OAuth consent screen configured
- [ ] Scopes: openid, email, profile
- [ ] OAuth client type: Web application
- [ ] Authorized JavaScript origins: `http://localhost:3000`
- [ ] Authorized redirect URIs: `http://localhost:3000/api/auth/callback`
- [ ] Test users added (if in testing mode)

## Need Help?

- **Google OAuth Documentation**: https://developers.google.com/identity/protocols/oauth2
- **Google Cloud Console**: https://console.cloud.google.com/

---

Once you complete this setup, you'll have secure authentication with Google login for your BigFlavor Band Agent!
