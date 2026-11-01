# Android App

The Briefcase Android app shows the briefcase web app on a phone. It checks that the briefcase answers. If it does not, the app offers to connect to the briefcase Wi-Fi network. The app then uses the briefcase Wi-Fi for its own traffic only, so the rest of the phone keeps its mobile data. This also stops the Android "no internet" prompt.

The app needs Android 10 or later.

## Install the App

1. On the phone, open the [GitHub releases](https://github.com/BatchCodes/rickroll_briefcase/releases) and download `briefcase-vX.Y.Z.apk` from the newest release.
2. Open the file. Android asks for permission to install apps from this source. Allow it.
3. Install the app.

## Update the App

The app checks the GitHub releases at most once a day, and when you select "Check for updates" in the menu. If a newer release exists, the app offers to install it:

1. Tap "Install". The app downloads the APK over the phone's internet connection, not over the briefcase Wi-Fi, and checks its SHA-256 checksum against the release `SHA256SUMS` file.
2. The first time, Android asks you to allow "Install unknown apps" for the app. Allow it, then select "Check for updates" again.
3. Android asks you to confirm the update.

To test pre-releases, select "Include pre-releases" in the menu.

An update installs only over an app with the same signing key. So updates work between release APKs. A debug APK from CI cannot update, and the app says so.

## Use the App

1. Open the app. If the phone can reach the briefcase, the app shows the web app.
2. If not, the app shows whether the `BRIEFCASE` network is in range, and its signal strength. It updates this every 10 s. The first time, Android asks for the "Nearby devices" permission (location on Android 10 to 12). Tap "Connect to BRIEFCASE". The first time, the app asks for the Wi-Fi password of the briefcase.
3. Android shows a dialog for the connection. Confirm it.

To change the network name or the password, open the menu and select "Wi-Fi settings".

In the web app:

- Swipe left or right to go to the next or the previous tab. A swipe that starts on a slider or a text field does not change the tab. This also works in a phone browser.
- Pull down at the top of the page to reload it.

## Build the App

You need only Docker. The build runs the unit tests first.

```bash
./scripts/build_android.sh debug
```

The debug APK is in `android/app/build/outputs/apk/debug/app-debug.apk`. CI builds it on each push. Download it from the `briefcase-debug-apk` artifact of the CI run.

## Release Signing Key

A release APK is signed with the release key. All releases need the same key, or Android does not install an update over the old app. Make the key one time, and keep a copy in a safe place, for example a password manager.

1. Make the key. The command asks for a password:

   ```bash
   docker run --rm -it -v "$PWD:/keys" -w /keys eclipse-temurin:17-jdk-noble \
     keytool -genkeypair -keystore briefcase-release.jks -alias briefcase \
     -keyalg RSA -keysize 4096 -validity 10000 -dname "CN=Briefcase"
   ```

2. Add the key to the GitHub Actions secrets of the repository. Use the password from step 1 for both passwords:

   ```bash
   base64 -w0 briefcase-release.jks | gh secret set BRIEFCASE_KEYSTORE_BASE64
   gh secret set BRIEFCASE_KEYSTORE_PASSWORD
   gh secret set BRIEFCASE_KEY_PASSWORD
   gh secret set BRIEFCASE_KEY_ALIAS --body briefcase
   ```

3. Store `briefcase-release.jks` outside the repository. The repository `.gitignore` ignores `.jks` files, but do not keep the key in the repository folder.

The `Release` workflow then builds the signed APK and attaches it to each release. Without the secrets, the release has no APK, and the workflow shows a warning.

## See also

- [Architecture](architecture.md)
- [Development](development.md)
