# Auth0 Setup Guide for BigFlavor Band Agent

This guide will walk you through setting up Auth0 authentication for the BigFlavor frontend.

## Why Auth0?

Auth0 handles all the complex authentication logic:
- Secure user login with Google
- Session management
- Token handling
- User profiles

You just need to configure it once, and it works!

## Step-by-Step Setup (15 minutes)

### Step 1: Create Auth0 Account

1. Go to **https://auth0.com**
2. Click **"Sign Up"** (it's free for up to 7,000 users!)
3. Sign up with your Google account or email
4. When asked, choose:
   - **Region**: Choose the closest to you (e.g., US, EU)
   - **Account Type**: Personal or Development

### Step 2: Create Your Application

1. After logging in, you'll be on the Auth0 Dashboard
2. In the left sidebar, click **"Applications"** → **"Applications"**
3. Click the **"Create Application"** button (top right)
4. Fill in the form:
   - **Name**: `BigFlavor Band Agent`
   - **Choose an application type**: Select **"Regular Web Applications"**
5. Click **"Create"**

### Step 3: Configure Your Application

After creating the application, you'll see the **Settings** tab:

#### A. Note Your Credentials

Find these three values (you'll need them soon):

```
Domain: YOUR-TENANT.us.auth0.com
Client ID: a long string like "abc123xyz..."
Client Secret: a long string (click "Show" to reveal)
```

**Keep these private!** Don't share them publicly.

#### B. Configure URLs

Scroll down to **"Application URIs"** section and enter:

**Allowed Callback URLs:**
```
http://localhost:3000/api/auth/callback
```

**Allowed Logout URLs:**
```
http://localhost:3000
```

**Allowed Web Origins:**
```
http://localhost:3000
```

#### C. Save Changes

Scroll to the bottom and click **"Save Changes"**

### Step 4: Enable Google Login

1. In the left sidebar, go to **"Authentication"** → **"Social"**
2. Find **"Google"** in the list
3. Toggle it **ON** (it will turn blue/green)
4. You can use Auth0's development keys (already configured) or set up your own Google OAuth app
5. For development, **just toggle it on** - that's it!

### Step 5: Generate Your Secret Key

Open PowerShell and run this command to generate a secure secret:

```powershell
# Option 1: If you have OpenSSL
openssl rand -hex 32

# Option 2: If OpenSSL isn't available (pure PowerShell)
-join ((48..57) + (97..102) | Get-Random -Count 64 | ForEach-Object {[char]$_})
```

Copy the output - this is your `AUTH0_SECRET`

### Step 6: Update Your Environment File

Open `frontend/.env.local` in a text editor and update these lines:

```env
# Replace these with your actual Auth0 values:
AUTH0_SECRET='paste-the-64-character-string-from-step-5'
AUTH0_BASE_URL='http://localhost:3000'
AUTH0_ISSUER_BASE_URL='https://YOUR-TENANT.us.auth0.com'
AUTH0_CLIENT_ID='your-client-id-from-step-3'
AUTH0_CLIENT_SECRET='your-client-secret-from-step-3'
```

**Example (with fake values):**
```env
AUTH0_SECRET='a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2'
AUTH0_BASE_URL='http://localhost:3000'
AUTH0_ISSUER_BASE_URL='https://dev-abc12345.us.auth0.com'
AUTH0_CLIENT_ID='xYz123AbC456dEf789GhI012'
AUTH0_CLIENT_SECRET='XyZ-123_AbC-456_dEf-789_GhI-012_jKl-345_mNo-678'
```

Save the file!

### Step 7: Test Your Setup

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

5. Try to access `/search` or `/radio` - you should be redirected to Auth0 login

6. Click **"Continue with Google"** and log in

7. After login, you should be redirected back to the app!

## Troubleshooting

### "Callback URL mismatch" error

**Problem**: After logging in, you see an error about callback URL

**Solution**:
- Go back to Auth0 Dashboard → Applications → Your App → Settings
- Make sure **"Allowed Callback URLs"** includes: `http://localhost:3000/api/auth/callback`
- Click "Save Changes"
- Clear your browser cookies and try again

### "Invalid state" error

**Problem**: Login fails with "Invalid state"

**Solution**:
- Make sure `AUTH0_SECRET` is set and is at least 32 characters
- Clear browser cookies
- Restart the frontend server

### "Client ID is missing" error

**Problem**: Can't connect to Auth0

**Solution**:
- Double-check that `.env.local` has all the Auth0 variables
- Make sure there are no extra spaces or quotes
- Restart the frontend server after changing `.env.local`

### Can't see Google login button

**Problem**: Only see email/password login

**Solution**:
- Go to Auth0 Dashboard → Authentication → Social
- Make sure Google is toggled ON
- Wait a minute, then try logging in again

### Login works but get "Unauthorized" in the app

**Problem**: Can log in but can't access features

**Solution**:
- Run the database migration if you haven't:
  ```powershell
  psql -U bigflavor -d bigflavor -f database/sql/migrations/05-create-users-table.sql
  ```
- Make sure the backend API is running
- Check the backend terminal for errors

## Security Notes

### For Development
- The `.env.local` file is already in `.gitignore` (won't be committed)
- It's OK to use Auth0's dev Google credentials for testing
- The `AUTH0_SECRET` can be any random string in development

### For Production (Later)
When you deploy this to production, you'll need to:

1. **Update URLs** in Auth0:
   - Change `http://localhost:3000` to your actual domain
   - Example: `https://bigflavor.yourdomain.com`

2. **Use Strong Secrets**:
   - Generate a new `AUTH0_SECRET` with `openssl rand -hex 32`
   - Never reuse development secrets

3. **Set Up Custom Domain** (optional):
   - Auth0 allows custom domains like `auth.yourdomain.com`
   - Makes the login experience more branded

4. **Configure Google OAuth App**:
   - Create your own Google OAuth app (not Auth0's dev keys)
   - Add your production domain to Google Console

## What's Next?

After Auth0 is set up, you can:

1. **Grant Editor Access** to users:
   ```sql
   UPDATE users SET role = 'editor' WHERE email = 'you@example.com';
   ```

2. **Customize Auth0**:
   - Add your logo in Auth0 Dashboard → Branding
   - Customize the login page colors
   - Add more social providers (Facebook, Twitter, etc.)

3. **Monitor Usage**:
   - Auth0 Dashboard → Monitoring shows login activity
   - See which users are logging in

## Quick Reference

### Auth0 Dashboard URLs
- **Main Dashboard**: https://manage.auth0.com/dashboard
- **Applications**: https://manage.auth0.com/dashboard/us/YOUR-TENANT/applications
- **Social Connections**: https://manage.auth0.com/dashboard/us/YOUR-TENANT/connections/social

### Environment Variables Checklist
- [ ] `AUTH0_SECRET` - 64 character random string
- [ ] `AUTH0_BASE_URL` - `http://localhost:3000`
- [ ] `AUTH0_ISSUER_BASE_URL` - Your Auth0 domain
- [ ] `AUTH0_CLIENT_ID` - From Auth0 app settings
- [ ] `AUTH0_CLIENT_SECRET` - From Auth0 app settings

### Auth0 Application Settings Checklist
- [ ] Application type: Regular Web Application
- [ ] Allowed Callback URLs: `http://localhost:3000/api/auth/callback`
- [ ] Allowed Logout URLs: `http://localhost:3000`
- [ ] Allowed Web Origins: `http://localhost:3000`
- [ ] Google Social Connection: Enabled

## Need Help?

- **Auth0 Documentation**: https://auth0.com/docs/quickstart/webapp/nextjs
- **Auth0 Community**: https://community.auth0.com/
- **Next.js Auth0 SDK**: https://github.com/auth0/nextjs-auth0

---

Once you complete this setup, you'll have secure authentication with Google login for your BigFlavor Band Agent! 🎵
