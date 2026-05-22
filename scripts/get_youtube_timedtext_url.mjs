#!/usr/bin/env node

import { spawn } from "node:child_process";
import { rm } from "node:fs/promises";
import path from "node:path";
import { setTimeout as delay } from "node:timers/promises";

const videoId = process.argv[2];
if (!videoId) {
  console.error("usage: node scripts/get_youtube_timedtext_url.mjs <videoId>");
  process.exit(1);
}

const CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const TMP_PROFILE = path.join(process.cwd(), ".tmp", `chrome-${videoId}`);
const DEBUG_PORT = 9223;

class CDPClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.nextId = 1;
    this.pending = new Map();
    this.ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (!msg.id) return;
      const pending = this.pending.get(msg.id);
      if (!pending) return;
      this.pending.delete(msg.id);
      if (msg.error) pending.reject(new Error(msg.error.message));
      else pending.resolve(msg.result);
    });
  }
  async waitOpen() {
    if (this.ws.readyState === 1) return;
    await new Promise((resolve, reject) => {
      this.ws.addEventListener("open", resolve, { once: true });
      this.ws.addEventListener("error", reject, { once: true });
    });
  }
  send(method, params = {}) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
  }
  close() {
    this.ws.close();
  }
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

async function launchChrome() {
  await rm(TMP_PROFILE, { recursive: true, force: true }).catch(() => {});
  const chrome = spawn(
    CHROME_BIN,
    [
      `--remote-debugging-port=${DEBUG_PORT}`,
      `--user-data-dir=${TMP_PROFILE}`,
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--autoplay-policy=no-user-gesture-required",
      `https://www.youtube.com/watch?v=${videoId}`,
    ],
    { stdio: "ignore" },
  );
  for (let i = 0; i < 50; i++) {
    try {
      await fetchJson(`http://127.0.0.1:${DEBUG_PORT}/json/version`);
      return chrome;
    } catch {
      await delay(200);
    }
  }
  throw new Error("chrome failed to start");
}

async function main() {
  const chrome = await launchChrome();
  let client;
  try {
    const targets = await fetchJson(`http://127.0.0.1:${DEBUG_PORT}/json/list`);
    const page = targets.find((t) => t.type === "page");
    client = new CDPClient(page.webSocketDebuggerUrl);
    await client.waitOpen();
    await client.send("Page.enable");
    await client.send("Runtime.enable");
    await delay(5000);
    const titleEval = await client.send("Runtime.evaluate", {
      expression: `document.title.replace(/\\s*-\\s*YouTube$/, "")`,
      returnByValue: true,
    });
    const title = titleEval.result.value;

    await client.send("Runtime.evaluate", {
      expression: `(() => {
        const selectors = [
          'button[aria-label*="자막"]',
          'button[aria-label*="Caption"]',
          'button[title*="자막"]',
          'button[title*="Caption"]'
        ];
        for (const selector of selectors) {
          const el = document.querySelector(selector);
          if (el) { el.click(); return true; }
        }
        return false;
      })()`,
      returnByValue: true,
    });
    await delay(2500);
    const result = await client.send("Runtime.evaluate", {
      expression: `(() => performance
        .getEntriesByType("resource")
        .map((entry) => entry.name)
        .filter((url) =>
          url.includes("/api/timedtext") &&
          url.includes("v=${videoId}") &&
          url.includes("fmt=json3") &&
          url.includes("pot=") &&
          url.includes("xorb=2") &&
          url.includes("cplayer=UNIPLAYER")
        )
        .sort((a, b) => b.length - a.length)[0] || null)()`,
      returnByValue: true,
    });
    const timedtextUrl = result.result.value || "";
    if (!timedtextUrl) {
      console.log(JSON.stringify({ videoId, title, timedtextUrl: "", transcript: null }));
      return;
    }
    const transcript = await fetch(timedtextUrl, {
      headers: { "user-agent": "Mozilla/5.0" },
    }).then((res) => res.text());
    console.log(JSON.stringify({ videoId, title, timedtextUrl, transcript }));
  } finally {
    client?.close();
    chrome.kill("SIGKILL");
  }
}

main().catch((error) => {
  console.error(error.message);
  process.exit(1);
});
