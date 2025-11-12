import { NextRequest, NextResponse } from 'next/server';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ auth0: string }> }
) {
  const { auth0: route } = await params;

  const domain = process.env.AUTH0_ISSUER_BASE_URL!;
  const clientId = process.env.AUTH0_CLIENT_ID!;
  const baseUrl = process.env.AUTH0_BASE_URL!;

  try {
    switch (route) {
      case 'login': {
        const redirectUri = `${baseUrl}/api/auth/callback`;
        const authUrl = `${domain}/authorize?` +
          `response_type=code&` +
          `client_id=${clientId}&` +
          `redirect_uri=${encodeURIComponent(redirectUri)}&` +
          `scope=openid%20profile%20email&` +
          `connection=google-oauth2`;

        return NextResponse.redirect(authUrl);
      }

      case 'logout': {
        const logoutUrl = `${domain}/v2/logout?` +
          `client_id=${clientId}&` +
          `returnTo=${encodeURIComponent(baseUrl)}`;

        // Clear session cookie
        const response = NextResponse.redirect(logoutUrl);
        response.cookies.delete('appSession');
        return response;
      }

      case 'callback': {
        const code = request.nextUrl.searchParams.get('code');

        if (!code) {
          return NextResponse.json({ error: 'No code provided' }, { status: 400 });
        }

        // Exchange code for tokens
        const tokenResponse = await fetch(`${domain}/oauth/token`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            grant_type: 'authorization_code',
            client_id: clientId,
            client_secret: process.env.AUTH0_CLIENT_SECRET!,
            code: code,
            redirect_uri: `${baseUrl}/api/auth/callback`,
          }),
        });

        if (!tokenResponse.ok) {
          const error = await tokenResponse.text();
          console.error('Token exchange failed:', error);
          return NextResponse.redirect(`${baseUrl}?error=auth_failed`);
        }

        const tokens = await tokenResponse.json();

        // Get user info
        const userResponse = await fetch(`${domain}/userinfo`, {
          headers: { Authorization: `Bearer ${tokens.access_token}` },
        });

        if (!userResponse.ok) {
          return NextResponse.redirect(`${baseUrl}?error=user_fetch_failed`);
        }

        const user = await userResponse.json();

        // Save user to database via backend API
        try {
          await fetch(`${process.env.AGENT_API_URL}/api/users`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              id: user.sub,
              email: user.email,
              name: user.name,
              picture: user.picture,
            }),
          });
        } catch (dbError) {
          console.error('Failed to save user to database:', dbError);
          // Continue anyway - user can still use the app
        }

        // Set session cookie (in production, use proper signed cookies)
        const response = NextResponse.redirect(baseUrl);
        response.cookies.set('appSession', JSON.stringify({
          user,
          accessToken: tokens.access_token,
          idToken: tokens.id_token,
        }), {
          httpOnly: true,
          secure: process.env.NODE_ENV === 'production',
          sameSite: 'lax',
          maxAge: 60 * 60 * 24 * 7, // 7 days
        });

        return response;
      }

      case 'me': {
        const sessionCookie = request.cookies.get('appSession');

        if (!sessionCookie) {
          return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
        }

        try {
          const session = JSON.parse(sessionCookie.value);
          return NextResponse.json(session.user);
        } catch {
          return NextResponse.json({ error: 'Invalid session' }, { status: 401 });
        }
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
