import http from "k6/http";
import { check, sleep } from "k6";
import { SharedArray } from "k6/data";

export const options = {
  scenarios: {
    seeded_redirects: {
      executor: "constant-vus",
      exec: "seededRedirects",
      vus: 400,
      duration: "30s",
    },
    fabricated_misses: {
      executor: "constant-vus",
      exec: "fabricatedMisses",
      vus: 100,
      duration: "30s",
    },
  },
  thresholds: {
    "checks{type:redirect}": ["rate==1"],
    "checks{type:missing}": ["rate==1"],
    http_reqs: ["rate>100"],
    "http_req_failed{type:redirect}": ["rate<0.01"],
    "http_req_duration{type:redirect}": ["p(95)<3000"],
    "http_req_failed{type:missing}": ["rate<0.01"],
    "http_req_duration{type:missing}": ["p(95)<3000"],
  },
};

const baseUrl = __ENV.BASE_URL || "http://64.227.152.245";
const urlsCsvPath = __ENV.URLS_CSV_PATH || "../seed/urls.csv";

function parseCsvLine(line) {
  const values = [];
  let current = "";
  let inQuotes = false;

  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];

    if (char === '"') {
      const nextChar = line[index + 1];
      if (inQuotes && nextChar === '"') {
        current += '"';
        index += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === "," && !inQuotes) {
      values.push(current);
      current = "";
      continue;
    }

    current += char;
  }

  values.push(current);
  return values;
}

function fabricateShortCode(row) {
  return `missing-${row.id}-${row.user_id}`;
}

function loadRedirectRows() {
  const content = open(urlsCsvPath);
  const lines = content
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);

  if (lines.length < 2) {
    return [];
  }

  const headers = parseCsvLine(lines[0]);

  return lines
    .slice(1)
    .map((line) => {
      const values = parseCsvLine(line);
      const row = Object.fromEntries(headers.map((header, idx) => [header, values[idx] || ""]));
      row.short_code = row.short_code || fabricateShortCode(row);
      return row;
    })
    .filter((row) => row.is_active === "True");
}

const redirectRows = new SharedArray("seeded-urls", loadRedirectRows);

if (redirectRows.length === 0) {
  throw new Error(`No active URLs found in ${urlsCsvPath}`);
}

export function seededRedirects() {
  const row = redirectRows[(__VU - 1) % redirectRows.length];
  const response = http.get(`${baseUrl}/${row.short_code}`, {
    redirects: 0,
    tags: { type: "redirect" },
    responseCallback: http.expectedStatuses(302),
  });

  check(response, {
    "redirect returns 302": (res) => res.status === 302,
    "redirect location matches": (res) => res.headers.Location === row.original_url,
    "redirect exposes cache tier header": (res) =>
      ["fresh", "shared", "local"].includes(res.headers["X-Cache-Tier"]),
  }, { type: "redirect" });

  sleep(1);
}

export function fabricatedMisses() {
  const row = redirectRows[(__VU - 1) % redirectRows.length];
  const response = http.get(`${baseUrl}/${fabricateShortCode(row)}`, {
    redirects: 0,
    tags: { type: "missing" },
    responseCallback: http.expectedStatuses(404),
  });

  check(response, {
    "missing shortcode returns 404": (res) => res.status === 404,
  }, { type: "missing" });

  sleep(1);
}
