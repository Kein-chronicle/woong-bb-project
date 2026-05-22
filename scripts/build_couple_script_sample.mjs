#!/usr/bin/env node

import { spawn } from "node:child_process";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { existsSync } from "node:fs";
import { setTimeout as delay } from "node:timers/promises";
import path from "node:path";

const WORKDIR = process.cwd();
const OUT_DIR = path.join(WORKDIR, "couple_script_sample");
const RAW_DIR = path.join(OUT_DIR, "raw");
const BUNDLE_DIR = path.join(OUT_DIR, "bundles");
const TMP_PROFILE = path.join(WORKDIR, ".tmp", "chrome-couple-script-profile");
const CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const DEBUG_PORT = 9222;
const TARGET_BUNDLES = 100;
const TARGET_UTTERANCES = 1000;

const SEARCH_QUERIES = [
  { q: "커플 Q&A", source_lang: "ko" },
  { q: "커플 브이로그 대화", source_lang: "ko" },
  { q: "장기연애 커플 토크", source_lang: "ko" },
  { q: "신혼부부 Q&A", source_lang: "ko" },
  { q: "부부 브이로그 대화", source_lang: "ko" },
  { q: "커플 밸런스게임", source_lang: "ko" },
  { q: "couple q&a relationship", source_lang: "en" },
  { q: "real couple conversation vlog", source_lang: "en" },
  { q: "couples test relationship", source_lang: "en" },
  { q: "married couple q and a", source_lang: "en" },
];

const BLOCKLIST_TITLE_PATTERNS = [
  /asmr/i,
  /reaction/i,
  /먹방/,
  /playlist/i,
  /music/i,
  /lyric/i,
  /challenge song/i,
];

class CDPClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.nextId = 1;
    this.pending = new Map();
    this.events = [];
    this.ws.addEventListener("message", (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id) {
        const pending = this.pending.get(msg.id);
        if (pending) {
          this.pending.delete(msg.id);
          if (msg.error) {
            pending.reject(new Error(msg.error.message));
          } else {
            pending.resolve(msg.result);
          }
        }
        return;
      }
      this.events.push(msg);
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

  pollEvents(method) {
    const matched = this.events.filter((event) => event.method === method);
    this.events = this.events.filter((event) => event.method !== method);
    return matched;
  }

  close() {
    this.ws.close();
  }
}

function log(...args) {
  console.log("[build]", ...args);
}

async function ensureDirs() {
  await mkdir(OUT_DIR, { recursive: true });
  await mkdir(RAW_DIR, { recursive: true });
  await mkdir(BUNDLE_DIR, { recursive: true });
  await mkdir(path.join(WORKDIR, ".tmp"), { recursive: true });
}

async function fetchJson(url) {
  const res = await fetch(url, {
    headers: {
      "user-agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    },
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} for ${url}`);
  return res.json();
}

async function launchChrome() {
  if (existsSync(TMP_PROFILE)) {
    await rm(TMP_PROFILE, { recursive: true, force: true });
  }
  const chrome = spawn(
    CHROME_BIN,
    [
      `--remote-debugging-port=${DEBUG_PORT}`,
      `--user-data-dir=${TMP_PROFILE}`,
      "--headless=new",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--autoplay-policy=no-user-gesture-required",
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  for (let i = 0; i < 50; i++) {
    try {
      const version = await fetchJson(`http://127.0.0.1:${DEBUG_PORT}/json/version`);
      return { chrome, version };
    } catch {
      await delay(300);
    }
  }
  throw new Error("Chrome remote debugging port did not open in time.");
}

async function connectPage() {
  const targets = await fetchJson(`http://127.0.0.1:${DEBUG_PORT}/json/list`);
  const page = targets.find((target) => target.type === "page");
  if (!page?.webSocketDebuggerUrl) {
    throw new Error("No debuggable page target found.");
  }
  const client = new CDPClient(page.webSocketDebuggerUrl);
  await client.waitOpen();
  await client.send("Page.enable");
  await client.send("Runtime.enable");
  await client.send("Network.enable");
  return client;
}

async function navigate(client, url) {
  client.events = [];
  await client.send("Page.navigate", { url });
  for (let i = 0; i < 200; i++) {
    const events = client.pollEvents("Page.loadEventFired");
    const readyState = await evaluate(client, "document.readyState").catch(() => null);
    if (events.length || readyState === "complete" || readyState === "interactive") {
      await delay(800);
      return;
    }
    await delay(100);
  }
  throw new Error(`Timed out waiting for load: ${url}`);
}

async function evaluate(client, expression) {
  const result = await client.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });
  return result.result?.value;
}

async function searchVideoIds(client, query) {
  const url = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;
  await navigate(client, url);
  const payload = await evaluate(
    client,
    `(() => {
      const html = document.documentElement.innerHTML;
      const ids = [...new Set((html.match(/"videoId":"([^"]+)"/g) || []).map((s) => s.match(/"videoId":"([^"]+)"/)[1]))];
      return ids.slice(0, 20);
    })()`,
  );
  return payload || [];
}

async function clickCaptionsButton(client) {
  return evaluate(
    client,
    `(() => {
      const selectors = [
        'button[aria-label*="자막"]',
        'button[aria-label*="Caption"]',
        'button[title*="자막"]',
        'button[title*="Caption"]'
      ];
      for (const selector of selectors) {
        const el = document.querySelector(selector);
        if (el) {
          el.click();
          return true;
        }
      }
      return false;
    })()`,
  );
}

async function extractVideoTranscript(client, videoId) {
  await navigate(client, `https://www.youtube.com/watch?v=${videoId}`);
  const title = await evaluate(client, `document.title.replace(/\\s*-\\s*YouTube$/, '')`);
  if (BLOCKLIST_TITLE_PATTERNS.some((pattern) => pattern.test(title))) {
    return null;
  }

  await clickCaptionsButton(client);
  await delay(1800);

  const preferred = await evaluate(
    client,
    `(() => performance
      .getEntriesByType("resource")
      .map((entry) => entry.name)
      .filter((url) =>
        url.includes("/api/timedtext") &&
        url.includes("v=${videoId}") &&
        url.includes("fmt=json3") &&
        url.includes("pot=") &&
        url.includes("xorb=2") &&
        url.includes("cplayer=UNIPLAYER")
      ))()`,
  );
  const timedtextUrl = preferred.sort((a, b) => b.length - a.length)[0];
  if (!timedtextUrl) {
    return null;
  }

  const transcriptText = await fetch(timedtextUrl, {
    headers: {
      "user-agent":
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    },
  }).then((res) => res.text());
  let transcriptJson;
  try {
    transcriptJson = JSON.parse(transcriptText);
  } catch (error) {
    throw new Error(`Transcript parse failed for ${videoId}: ${timedtextUrl.slice(0, 240)} :: ${transcriptText.slice(0, 120)}`);
  }

  const lang = timedtextUrl.includes("lang=ko") ? "ko" : timedtextUrl.includes("lang=en") ? "en" : "unknown";
  return { videoId, title, lang, timedtextUrl, transcriptJson };
}

function decodeText(text) {
  return text
    .replace(/&#39;/g, "'")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function normalizeCaptionEvents(transcriptJson) {
  const events = [];
  for (const event of transcriptJson.events || []) {
    const segs = event.segs || [];
    const text = decodeText(
      segs
        .map((seg) => seg.utf8 || "")
        .join("")
        .replace(/\s+/g, " ")
        .trim(),
    );
    if (!text) continue;
    if (/^\[[^\]]+\]$/.test(text)) continue;
    if (/^[♪♬]+/.test(text)) continue;
    events.push({
      start_ms: event.tStartMs || 0,
      duration_ms: event.dDurationMs || 0,
      text,
    });
  }
  return events;
}

async function translateToKorean(text) {
  const url =
    "https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=ko&dt=t&q=" +
    encodeURIComponent(text);
  const res = await fetch(url, {
    headers: {
      "user-agent": "Mozilla/5.0",
    },
  });
  const data = await res.json();
  return (data[0] || []).map((part) => part[0] || "").join("").trim();
}

async function translateEventsIfNeeded(events, lang) {
  if (lang === "ko") {
    return events.map((event) => ({ ...event, text_ko: event.text, source_text: event.text }));
  }

  const translated = [];
  for (const event of events) {
    const text_ko = await translateToKorean(event.text);
    translated.push({ ...event, text_ko, source_text: event.text });
    await delay(80);
  }
  return translated;
}

function buildBundlesFromEvents(meta, events, startBundleIndex) {
  const bundles = [];
  let cursor = 0;
  let bundleIndex = startBundleIndex;

  while (cursor + 10 <= events.length) {
    const slice = events.slice(cursor, cursor + 10);
    const utterances = slice.map((event, idx) => ({
      turn_index: idx + 1,
      speaker: idx % 2 === 0 ? "화자A(추정)" : "화자B(추정)",
      text_ko: event.text_ko,
      source_text: event.source_text,
      start_ms: event.start_ms,
      duration_ms: event.duration_ms,
    }));

    bundles.push({
      bundle_id: `bundle_${String(bundleIndex).padStart(3, "0")}`,
      source_title: meta.title,
      source_url: `https://www.youtube.com/watch?v=${meta.videoId}`,
      source_lang: meta.lang,
      translation: meta.lang === "ko" ? "none" : "en_to_ko_google",
      speaker_note:
        "유튜브 자동 자막의 시간축을 기준으로 10개 발화를 묶고, 화자 구분은 실제 음성 분리 없이 교대형으로 추정했습니다.",
      utterances,
    });

    bundleIndex += 1;
    cursor += 8;
  }

  return bundles;
}

async function main() {
  await ensureDirs();
  const { chrome } = await launchChrome();
  let client;

  try {
    client = await connectPage();
    const seenVideoIds = new Set();
    const collected = [];

    for (const query of SEARCH_QUERIES) {
      log("searching", query.q);
      const ids = await searchVideoIds(client, query.q);
      for (const videoId of ids) {
        if (seenVideoIds.has(videoId)) continue;
        seenVideoIds.add(videoId);
        try {
          const transcript = await extractVideoTranscript(client, videoId);
          if (!transcript) continue;
          if (!["ko", "en"].includes(transcript.lang)) continue;
          transcript.query = query.q;
          transcript.query_lang = query.source_lang;
          collected.push(transcript);
          log("captured", transcript.lang, transcript.title);
          if (collected.length >= 30) break;
        } catch (error) {
          log("skip video", videoId, error.message);
        }
      }
      if (collected.length >= 30) break;
    }

    let bundleIndex = 1;
    let utteranceCount = 0;
    const allBundles = [];
    const manifest = [];

    for (const item of collected) {
      const normalized = normalizeCaptionEvents(item.transcriptJson);
      if (normalized.length < 20) continue;
      const translated = await translateEventsIfNeeded(normalized, item.lang);
      const bundles = buildBundlesFromEvents(item, translated, bundleIndex);

      const usableBundles = bundles.slice(0, 6);
      for (const bundle of usableBundles) {
        if (allBundles.length >= TARGET_BUNDLES) break;
        allBundles.push(bundle);
        utteranceCount += bundle.utterances.length;
        bundleIndex += 1;
      }

      const rawPath = path.join(RAW_DIR, `${item.videoId}.json`);
      await writeFile(
        rawPath,
        JSON.stringify(
          {
            video_id: item.videoId,
            title: item.title,
            source_url: `https://www.youtube.com/watch?v=${item.videoId}`,
            source_lang: item.lang,
            timedtext_url: item.timedtextUrl,
            query: item.query,
            events: translated,
          },
          null,
          2,
        ),
      );

      manifest.push({
        video_id: item.videoId,
        title: item.title,
        source_url: `https://www.youtube.com/watch?v=${item.videoId}`,
        source_lang: item.lang,
        query: item.query,
        raw_file: path.relative(OUT_DIR, rawPath),
      });

      if (allBundles.length >= TARGET_BUNDLES && utteranceCount >= TARGET_UTTERANCES) break;
    }

    for (const bundle of allBundles) {
      const filePath = path.join(BUNDLE_DIR, `${bundle.bundle_id}.json`);
      await writeFile(filePath, JSON.stringify(bundle, null, 2));
    }

    const readme = [
      "# couple_script_sample",
      "",
      `- bundles: ${allBundles.length}`,
      `- utterances: ${utteranceCount}`,
      `- raw sources: ${manifest.length}`,
      "",
      "## notes",
      "- 한국어 자막이 있으면 그대로 정리했습니다.",
      "- 영어 자막만 있는 경우 Google 번역 공개 엔드포인트로 한국어 초벌 번역을 만들었습니다.",
      "- 화자 구분은 자동 자막의 시간축만으로는 정확히 분리되지 않아 `화자A(추정)` / `화자B(추정)` 형태로 교대 추정했습니다.",
      "- 실제 연구용으로 쓸 때는 관심 있는 묶음을 다시 원본 영상에서 청취 확인하는 것이 좋습니다.",
      "",
      "## files",
      "- `raw/`: 영상 단위 전체 정규화 자막",
      "- `bundles/`: 10발화 단위 연구용 묶음",
      "- `manifest.json`: 수집한 원본 영상 인덱스",
      "",
    ].join("\n");

    await writeFile(path.join(OUT_DIR, "manifest.json"), JSON.stringify(manifest, null, 2));
    await writeFile(path.join(OUT_DIR, "README.md"), readme);

    log(`done: ${allBundles.length} bundles / ${utteranceCount} utterances`);
  } finally {
    client?.close();
    chrome.kill("SIGKILL");
  }
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
