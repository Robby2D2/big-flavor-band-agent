import { NextRequest, NextResponse } from 'next/server';

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

        return NextResponse.redirect(authUrl);
      }

      case 'logout': {
        // Clear session cookie and redirect to home
        const response = NextResponse.redirect(baseUrl);
        response.cookies.delete('appSession');
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

        // Set session cookie
        const sessionData = JSON.stringify({
          sub: user.sub,
          email: user.email,
          name: user.name,
          picture: user.picture,
        });

        console.log('[AUTH] Creating session for user:', user.email);
        console.log('[AUTH] Protocol:', protocol, 'Host:', host, 'BaseURL:', baseUrl);
        console.log('[AUTH] Session data length:', sessionData.length, 'bytes');

        const maxAge = 60 * 60 * 24 * 7; // 7 days

        // Manually construct Set-Cookie header for more control
        const cookieValue = encodeURIComponent(sessionData);
        const cookieHeader = [
          `appSession=${cookieValue}`,
          `Path=/`,
          `Max-Age=${maxAge}`,
          `HttpOnly`,
          `SameSite=Lax`,
        ].filter(Boolean).join('; ');

        console.log('[AUTH] Set-Cookie header:', cookieHeader.substring(0, 100) + '...');

        const response = NextResponse.redirect(baseUrl);
        response.headers.set('Set-Cookie', cookieHeader);

        console.log('[AUTH] Cookie set, redirecting to:', baseUrl);
        return response;
      }

      case 'me': {
        const sessionCookie = request.cookies.get('appSession');

        if (!sessionCookie) {
          return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
        }

        try {
          const session = JSON.parse(sessionCookie.value);

          // Session stores user data directly, not nested under 'user'
          const userSub = session.sub;

          // Fetch user role from backend
          let role = 'listener'; // default role
          try {
            const roleResponse = await fetch(`${process.env.AGENT_API_URL}/api/users/${userSub}/role`);
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
