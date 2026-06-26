# Chapter 1: Interception Tools & Environment Setup

This guide walks through setting up the reverse-engineering environment to inspect and intercept HTTP/HTTPS traffic between the official PGBank Internet Banking web application (or mobile app) and its backend API servers.

---

## 1. Legal and Safety Disclaimer

> [!WARNING]
> This documentation is created for educational, research, and security audit purposes only. Reverse engineering proprietary software may violate the Terms of Service of the provider. Always perform security testing only on accounts you own or have explicit authorization to test. Never share credentials, session IDs, or private data publicly.

---

## 2. Architecture Overview

Modern banking systems like PGBank use a separated frontend/backend architecture. The user interface (web app in Angular/React/Vue or mobile app in Swift/Kotlin/Flutter) acts as a client that sends API requests to a backend Gateway. 

Because HTTP/HTTPS is a cleartext/standard transport protocol, the traffic is theoretically visible to the client. However, modern banks employ two layers of defense:
1. **Transport Layer Security (TLS/SSL)**: Encrypts traffic in transit.
2. **Application-Layer Encryption (Payload Cryptography)**: Encrypts the actual JSON request and response payloads, rendering standard proxy logs illegible without decrypting the custom wrapper.

To analyze the API, we must solve both problems:
- Intercept the TLS/SSL traffic.
- Decrypt the application payloads.

---

## 3. Recommended Interception Tools

To inspect the network requests, you need a tool that can act as a Man-in-the-Middle (MitM) proxy or inspect the browser environment directly.

### A. Chrome/Firefox Developer Tools (Network Tab)
* **Best For**: Web-based internet banking applications.
* **Pros**: No installation or certificate configuration needed; built directly into modern browsers. You can inspect requests, inspect JS execution, set breakpoints, and copy requests as `cURL`.
* **Cons**: Cannot easily intercept/modify mobile app traffic or automate request replays.

### B. Charles Proxy / Fiddler Classic
* **Best For**: General HTTP/HTTPS traffic inspection on Web and Mobile.
* **Pros**: Simple GUI, easy certificate installation, excellent breakpoints, and request redirection.
* **Cons**: Paid license (Charles) or Windows-centric (Fiddler Classic).

### C. Burp Suite Community Edition
* **Best For**: Advanced security analysis and API fuzzing.
* **Pros**: Industry-standard tool, powerful repeater, sequencer, and intruder modules.
* **Cons**: High learning curve, interface can be overwhelming for beginners.

---

## 4. Setup Guide: Chrome DevTools (Fastest)

For analyzing the PGBank Web Portal (`ib.pgbank.com.vn`), Chrome DevTools is the easiest choice:

1. Open Google Chrome or any Chromium-based browser (Brave, Edge).
2. Navigate to the PGBank Internet Banking portal: `https://ib.pgbank.com.vn/`.
3. Press `F12` or `Ctrl + Shift + I` (`Cmd + Option + I` on Mac) to open Developer Tools.
4. Click on the **Network** tab.
5. Check the **Preserve log** and **Disable cache** options.
6. Under the filter input box, select **Fetch/XHR** to isolate API requests from static assets.

---

## 5. Setup Guide: Charles/Fiddler/Burp (For Mobile/Native APIs)

If you need to intercept native mobile apps or need advanced manipulation, configure a MitM proxy:

```
+------------+       TLS + MitM CA       +---------------+       TLS       +-----------------+
| Mobile/Web | ------------------------> | MitM Proxy    | --------------> | PGBank API      |
| Client     | <------------------------ | (Charles/Burp)| <-------------- | Gateway         |
+------------+   (Decrypts & Logs)       +---------------+                 +-----------------+
```

### Step 1: Install the Proxy
1. Download and install [Charles Proxy](https://www.charlesproxy.com/) or [Burp Suite](https://portswigger.net/burp/communitydownload).
2. Start the proxy. By default, Charles runs on port `8888` and Burp on port `8080`.

### Step 2: Configure System/Device Proxy
* **Windows/Mac**: Configure your system network settings to route HTTP and HTTPS traffic through `127.0.0.1:8888` (or `8080`).
* **Android/iOS Device**: 
  1. Connect your phone to the same Wi-Fi network as your computer.
  2. Edit the Wi-Fi connection, set Proxy to **Manual**.
  3. Input your computer's local IP address (e.g. `192.168.1.15`) and the proxy port.

### Step 3: Install the SSL/TLS CA Certificate
Without this step, your browser/device will throw security warnings and block connections because the proxy's certificate is not signed by a trusted root authority.

1. **Download**: On the device, open a browser and go to the proxy's certificate download page:
   - For Charles: `http://chls.pro/ssl`
   - For Burp: `http://burp` (or export the certificate from Burp GUI -> Proxy -> Import/export CA certificate).
2. **Install**:
   - **iOS**: Go to Settings -> Profile Downloaded -> Install. Then go to Settings -> General -> About -> Certificate Trust Settings and enable full trust for the root certificate.
   - **Android**: Go to Settings -> Security -> Encryption & credentials -> Install a certificate -> CA certificate. Select the downloaded `.crt`/`.pem` file.

### Step 4: Bypassing SSL Pinning (Mobile Only)
If you are analyzing the PGBank native mobile app, installing a CA certificate is often insufficient because the app contains **SSL Pinning** (checking the server's certificate against a hardcoded copy). To bypass SSL Pinning:
1. Set up **Frida** on your computer and an Android emulator (or rooted physical device).
2. Launch the app with an SSL Pinning bypass script:
   ```bash
   frida -U -f vn.com.pgbank.retail -l bypass-ssl-pinning.js --no-pause
   ```
3. Alternatively, use **Objection** to automatically patch the APK/IPA file:
   ```bash
   objection patchapk -s pgbank.apk
   ```

---

## 6. Verification

To verify your proxy is capturing encrypted traffic:
1. Reload the PGBank web portal.
2. In your proxy, look for traffic to `https://ib.pgbank.com.vn` and `https://api-ib.pgbank.com.vn`.
3. If you can see the requests in plaintext (the URLs, headers, and encrypted response bodies), your proxy setup is successful!

In the next chapter, we will look at how to locate the entrypoints and identify key initialization parameters.
