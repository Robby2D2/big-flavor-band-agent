import { NextRequest, NextResponse } from 'next/server';
import { INVITE_COOKIE, INVITE_COOKIE_MAX_AGE, redeemInvite } from '@/lib/invites';
import { backendAuthHeaders } from '@/lib/backend';
import { SESSION_COOKIE, readSessionValue, sessionCookieHeader } from '@/lib/session';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ google: string[] }> }
) {
  const { google: routes } = await params;
  const route = routes[0];

  const clientId = process.env.GOOGLE_CLIENT_ID!;
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET!;

  // Use the actual request origin instead of hardcoded base URL
  const protocol = request.headers.get('x-forwarded-proto') || 'http';
  const host = request.headers.get('host') || 'localhost:3000';
  const baseUrl = `${protocol}://${host}`;

  try {
    switch (route) {
      case 'login': {
        const redirectUri = `${baseUrl}/api/auth/callback`;
        const authUrl = `https://accounts.google.com/o/oauth2/v2/auth?` +
          `response_type=code&` +
          `client_id=${clientId}&` +
          `redirect_uri=${encodeURIComponent(redirectUri)}&` +
          `scope=${encodeURIComponent('openid profile email')}&` +
          `access_type=offline&` +
          `prompt=consent`;

        const response = NextResponse.redirect(authUrl);

        // Carry an invite token across the Google round-trip so the callback
        // can redeem it once the user row exists. HttpOnly + Lax: the browser
        // still sends it on the top-level redirect back from Google, but page
        // scripts can never read it.
        const invite = request.nextUrl.searchParams.get('invite');
        if (invite) {
          response.cookies.set(INVITE_COOKIE, invite, {
            httpOnly: true,
            sameSite: 'lax',
            path: '/',
            maxAge: INVITE_COOKIE_MAX_AGE,
          });
        }

        return response;
      }

      case 'logout': {
        // Clear session cookie and redirect to home
        const response = NextResponse.redirect(baseUrl);
        response.cookies.delete(SESSION_COOKIE);
        return response;
      }

      case 'callback': {
        const code = request.nextUrl.searchParams.get('code');
        const error = request.nextUrl.searchParams.get('error');

        if (error) {
          console.error('OAuth error:', error);
          return NextResponse.redirect(`${baseUrl}?error=${error}`);
        }

        if (!code) {
          return NextResponse.json({ error: 'No code provided' }, { status: 400 });
        }

        // Exchange code for tokens with Google
        const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: new URLSearchParams({
            code: code,
            client_id: clientId,
            client_secret: clientSecret,
            redirect_uri: `${baseUrl}/api/auth/callback`,
            grant_type: 'authorization_code',
          }),
        });

        if (!tokenResponse.ok) {
          const error = await tokenResponse.text();
          console.error('Token exchange failed:', error);
          return NextResponse.redirect(`${baseUrl}?error=auth_failed`);
        }

        const tokens = await tokenResponse.json();

        // Get user info from Google
        const userResponse = await fetch('https://www.googleapis.com/oauth2/v2/userinfo', {
          headers: { Authorization: `Bearer ${tokens.access_token}` },
        });

        if (!userResponse.ok) {
          return NextResponse.redirect(`${baseUrl}?error=user_fetch_failed`);
        }

        const googleUser = await userResponse.json();

        // Map Google user to our user format
        const user = {
          sub: googleUser.id,
          email: googleUser.email,
          name: googleUser.name,
          picture: googleUser.picture,
        };

        // Save user to database via backend API. Whether this succeeded
        // decides if an invite can be redeemed below — a role can only be
        // granted to a user row that exists.
        let userSaved = false;
        try {
          const saveResponse = await fetch(`${process.env.AGENT_API_URL}/api/users`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              // Google has just vouched for this person; 'listener' is what the
              // upsert grants them anyway.
              ...backendAuthHeaders('listener'),
            },
            body: JSON.stringify({
              id: user.sub,
              email: user.email,
              name: user.name,
              picture: user.picture,
            }),
          });
          userSaved = saveResponse.ok;
        } catch (dbError) {
          console.error('Failed to save user to database:', dbError);
          // Continue anyway - user can still use the app
        }

        // Set the signed session cookie. Without SESSION_SECRET this throws
        // rather than issuing a session nobody can verify.
        let cookieHeader: string;
        try {
          cookieHeader = sessionCookieHeader(user, protocol === 'https');
        } catch (sessionError) {
          console.error('Cannot issue a session:', sessionError);
          return NextResponse.redirect(`${baseUrl}?error=session_not_configured`);
        }

        console.log('[AUTH] Creating session for user:', user.email);
        console.log('[AUTH] Protocol:', protocol, 'Host:', host, 'BaseURL:', baseUrl);

        // Redeem a pending invite, if this sign-in came from an invite link.
        const pendingInvite = request.cookies.get(INVITE_COOKIE)?.value;
        let redirectTo = baseUrl;

        if (pendingInvite) {
          const result = userSaved
            ? await redeemInvite(pendingInvite, user.sub, user.email)
            : { ok: false as const, error: 'Your account could not be created. Please try again.' };

          redirectTo = result.ok
            ? `${baseUrl}/invite/accepted?role=${encodeURIComponent(result.role)}`
            : `${baseUrl}/invite/accepted?error=${encodeURIComponent(result.error)}`;
        }

        const response = NextResponse.redirect(redirectTo);
        response.headers.set('Set-Cookie', cookieHeader);

        if (pendingInvite) {
          response.headers.append(
            'Set-Cookie',
            `${INVITE_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax`
          );
        }

        console.log('[AUTH] Cookie set, redirecting to:', redirectTo);
        return response;
      }

      case 'me': {
        const session = readSessionValue(request.cookies.get(SESSION_COOKIE)?.value);

        if (!session) {
          return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
        }

        // Fetch user role from backend
        let role = 'listener'; // default role
        try {
          const roleResponse = await fetch(
            `${process.env.AGENT_API_URL}/api/users/${session.sub}/role`,
            { headers: backendAuthHeaders('listener') }
          );
          if (roleResponse.ok) {
            const roleData = await roleResponse.json();
            role = roleData.role;
          }
        } catch (error) {
          console.error('Failed to fetch user role:', error);
        }

        return NextResponse.json({
          sub: session.sub,
          email: session.email,
          name: session.name,
          picture: session.picture,
          role
        });
      }

      default:
        return NextResponse.json({ error: 'Not found' }, { status: 404 });
    }
  } catch (error) {
    console.error('Auth error:', error);
    return NextResponse.json(
      { error: 'Authentication error' },
      { status: 500 }
    );
  }
}
