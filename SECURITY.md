# Security Policy

The briefcase is a toy. It has a small attack surface, but it runs a web server and a Wi-Fi access point. Report security problems privately.

## Supported Versions

Only the latest release gets security fixes.

## Reporting a Vulnerability

Do not open a public issue for a vulnerability.

1. Open the repository on GitHub.
2. Go to the "Security" tab.
3. Select "Report a vulnerability".
4. Describe the problem and the steps to reproduce it.

A maintainer replies within 14 days.

## Known Limitations

- The web app has no login. Any device on the briefcase Wi-Fi network can upload, change and delete videos. The WPA2 password of the access point is the only protection. Use a strong password.
- The web app uses HTTP, not HTTPS. The Wi-Fi encryption protects the traffic.
