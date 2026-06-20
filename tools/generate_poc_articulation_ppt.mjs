#!/usr/bin/env node
/**
 * Generate 6-slide UK Address Validation POC deck from POC_ARTICULATION.md
 *
 * Usage:
 *   npm init -y && npm install pptxgenjs
 *   node tools/generate_poc_articulation_ppt.mjs
 *
 * Output: docs/POC_ARTICULATION_6SLIDE.pptx
 */

import pptxgen from "pptxgenjs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const OUT = join(__dirname, "..", "docs", "POC_ARTICULATION_6SLIDE.pptx");

// Arthavi palette (matches generate_client_3slide_ppt.py)
const C = {
  teal: "028090",
  deepBlue: "243670",
  lightBg: "EEF4FB",
  lighterBg: "F4F8FB",
  white: "FFFFFF",
  dark: "1A2B5E",
  text: "1A1A1A",
  muted: "5B6473",
  accent: "0077BF",
  green: "4E9D2D",
};

const pptx = new pptxgen();
pptx.layout = "LAYOUT_16x9";
pptx.author = "Arthavi";
pptx.company = "Arthavi";
pptx.subject = "UK Address Validation POC";
pptx.title = "UK Address Validation POC — gpt-4o-mini";

// ── helpers ────────────────────────────────────────────────────────────────

function addLeftBar(slide) {
  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: 0.18,
    h: "100%",
    fill: { color: C.teal },
    line: { type: "none" },
  });
}

function addHeader(slide, title, subtitle = "") {
  addLeftBar(slide);
  slide.addShape(pptx.ShapeType.rect, {
    x: 0.18,
    y: 0,
    w: "100%",
    h: 0.85,
    fill: { color: C.deepBlue },
    line: { type: "none" },
  });
  slide.addText(title, {
    x: 0.45,
    y: 0.15,
    w: 9.0,
    h: 0.45,
    fontSize: 22,
    bold: true,
    color: C.white,
    fontFace: "Calibri",
  });
  if (subtitle) {
    slide.addText(subtitle, {
      x: 0.45,
      y: 0.52,
      w: 9.0,
      h: 0.28,
      fontSize: 11,
      color: C.lighterBg,
      fontFace: "Calibri",
    });
  }
}

function addBullets(slide, items, opts = {}) {
  const {
    x = 0.45,
    y = 1.05,
    w = 9.0,
    h = 4.2,
    fontSize = 12,
    color = C.text,
  } = opts;
  const rows = items.map((t) => ({
    text: t,
    options: { bullet: true, breakLine: true },
  }));
  slide.addText(rows, {
    x,
    y,
    w,
    h,
    fontSize,
    color,
    fontFace: "Calibri",
    valign: "top",
    paraSpaceAfter: 6,
  });
}

function addCard(slide, { x, y, w, h, title, body, fill = C.lightBg }) {
  slide.addShape(pptx.ShapeType.roundRect, {
    x,
    y,
    w,
    h,
    fill: { color: fill },
    line: { color: C.lighterBg, width: 0.5 },
    rectRadius: 0.08,
  });
  slide.addText(title, {
    x: x + 0.15,
    y: y + 0.12,
    w: w - 0.3,
    h: 0.35,
    fontSize: 11,
    bold: true,
    color: C.deepBlue,
    fontFace: "Calibri",
  });
  slide.addText(body, {
    x: x + 0.15,
    y: y + 0.45,
    w: w - 0.3,
    h: h - 0.55,
    fontSize: 10,
    color: C.text,
    fontFace: "Calibri",
    valign: "top",
  });
}

// ── Slide 1: Title ─────────────────────────────────────────────────────────

{
  const slide = pptx.addSlide();
  slide.background = { color: C.deepBlue };

  slide.addShape(pptx.ShapeType.rect, {
    x: 0,
    y: 0,
    w: 0.22,
    h: "100%",
    fill: { color: C.teal },
    line: { type: "none" },
  });

  slide.addText("UK Address Validation POC", {
    x: 0.55,
    y: 1.6,
    w: 8.8,
    h: 0.9,
    fontSize: 36,
    bold: true,
    color: C.white,
    fontFace: "Calibri",
  });

  slide.addText("Cloud LLM (gpt-4o-mini) vs Arthavi LLM", {
    x: 0.55,
    y: 2.55,
    w: 8.8,
    h: 0.5,
    fontSize: 20,
    color: C.lighterBg,
    fontFace: "Calibri",
  });

  slide.addText(
    [
      { text: "Validate & normalize UK vendor addresses into SAP schema", options: { breakLine: true } },
      { text: "Street-first local index + RAG + measurable token/cost/latency", options: { breakLine: true } },
    ],
    {
      x: 0.55,
      y: 3.35,
      w: 8.5,
      h: 0.9,
      fontSize: 13,
      color: C.lighterBg,
      fontFace: "Calibri",
    }
  );

  slide.addText("Arthavi  |  SAP CPI Address Validation  |  June 2026", {
    x: 0.55,
    y: 4.85,
    w: 8.5,
    h: 0.35,
    fontSize: 10,
    color: C.muted,
    fontFace: "Calibri",
  });
}

// ── Slide 2: Objective & Cloud Setup ───────────────────────────────────────

{
  const slide = pptx.addSlide();
  slide.background = { color: C.white };
  addHeader(slide, "Objective & Cloud Setup", "Measurable POC: gpt-4o-mini vs local Arthavi LLM");

  addCard(slide, {
    x: 0.45,
    y: 1.05,
    w: 4.35,
    h: 2.0,
    title: "Objective",
    body:
      "Validate and normalize UK vendor addresses into the SAP target schema using gpt-4o-mini, with measurable token usage, latency, and cost per request — compared against local Arthavi LLM (Ollama, zero API cost).",
  });

  addCard(slide, {
    x: 5.0,
    y: 1.05,
    w: 4.35,
    h: 2.0,
    title: "Cloud Setup (Current)",
    body:
      "UI label: Azure OpenAI\nBackend: OpenAI API (LLM_PROVIDER=openai)\nModel: gpt-4o-mini-2024-07-18\nLocal: street-first index (~800 records)\nRAG: similar corrections injected pre-LLM",
  });

  addBullets(
    slide,
    [
      "Postcodes.io fallback when local index is not confident (~200 ms)",
      "OpenAI key sourced from VidyAI .env via VIDYAI_ENV_FILE",
      "Prior Azure Foundry benchmark: Kimi-K2.6 was 2.1× slower, 48% more tokens, 4× costlier",
      "gpt-4o-mini POC run: 6.7 s latency, 1,602 tokens, $0.000330 / request",
    ],
    { y: 3.25, h: 1.8, fontSize: 11 }
  );
}

// ── Slide 3: Execution Flow ──────────────────────────────────────────────────

{
  const slide = pptx.addSlide();
  slide.background = { color: C.white };
  addHeader(slide, "Execution Flow", "Street-first + RAG shared; only LLM step differs by provider");

  const flowRows = [
    [
      { text: "Step", options: { bold: true, fill: { color: C.deepBlue }, color: C.white } },
      { text: "Module", options: { bold: true, fill: { color: C.deepBlue }, color: C.white } },
      { text: "What happens", options: { bold: true, fill: { color: C.deepBlue }, color: C.white } },
    ],
    ["1", "POST /api/normalize", "Receives address; llm_provider routes to cloud or Arthavi"],
    ["2", "preprocess.py", "Cleans text; extracts postcode (none for POC input)"],
    ["3", "local_address_store", "Street-first scan → match CV1 2NF (~13 ms)"],
    ["4", "local_validator", "street_first_resolved — Postcodes.io skipped"],
    ["5", "rag/retriever", "Similar correction (Elliot's Yard) + local_lookup block"],
    ["6", "azure_normalize", "Compact context + RAG → gpt-4o-mini JSON mode"],
    ["7", "StandardAddress", "Maps LLM JSON to SAP fields"],
    ["8", "API response", "normalized_address, llm_analysis, tokens, cost, RAG hits"],
  ];

  slide.addTable(flowRows, {
    x: 0.45,
    y: 1.05,
    w: 9.0,
    colW: [0.55, 2.2, 6.25],
    fontSize: 9,
    fontFace: "Calibri",
    color: C.text,
    border: { type: "solid", color: C.lighterBg, pt: 0.5 },
    autoPage: false,
    rowH: 0.38,
  });

  slide.addText(
    "Local validation + RAG add ~20 ms — cloud LLM dominates total latency (~6.7 s).",
    {
      x: 0.45,
      y: 4.85,
      w: 9.0,
      h: 0.35,
      fontSize: 10,
      italic: true,
      color: C.muted,
      fontFace: "Calibri",
    }
  );
}

// ── Slide 4: Test Case & Output ──────────────────────────────────────────────

{
  const slide = pptx.addSlide();
  slide.background = { color: C.white };
  addHeader(
    slide,
    "Test Case Executed",
    "Postcode omitted in vendor text — resolved locally to CV1 2NF before LLM mapping"
  );

  addCard(slide, {
    x: 0.45,
    y: 1.05,
    w: 9.0,
    h: 1.05,
    title: "Input (SAP / CPI vendor address)",
    body: "8 Gulson Road Coventry Apartment 7 Elliot's Yard",
    fill: C.lighterBg,
  });

  const outputRows = [
    [
      { text: "SAP Field", options: { bold: true, fill: { color: C.teal }, color: C.white } },
      { text: "Normalized Value", options: { bold: true, fill: { color: C.teal }, color: C.white } },
    ],
    ["street_house_number", "8"],
    ["street_2", "APARTMENT 7"],
    ["street_3", "ELLIOT'S YARD"],
    ["street_4", "GULSON ROAD"],
    ["district / other_city", "COVENTRY"],
    ["postal_code", "CV1 2NF"],
    ["postal_code_city", "CV1 2NF COVENTRY"],
    ["country / time_zone", "GB / GMTUK"],
  ];

  slide.addTable(outputRows, {
    x: 0.45,
    y: 2.3,
    w: 9.0,
    colW: [3.2, 5.8],
    fontSize: 10,
    fontFace: "Calibri",
    color: C.text,
    border: { type: "solid", color: C.lighterBg, pt: 0.5 },
    rowH: 0.32,
  });

  slide.addShape(pptx.ShapeType.roundRect, {
    x: 0.45,
    y: 4.75,
    w: 9.0,
    h: 0.55,
    fill: { color: C.lightBg },
    line: { type: "none" },
    rectRadius: 0.06,
  });
  slide.addText("Output matches expected human-corrected mapping for the Elliot's Yard pattern.", {
    x: 0.6,
    y: 4.88,
    w: 8.7,
    h: 0.35,
    fontSize: 11,
    bold: true,
    color: C.green,
    fontFace: "Calibri",
  });
}

// ── Slide 5: Metrics & Cost Charts ───────────────────────────────────────────

{
  const slide = pptx.addSlide();
  slide.background = { color: C.white };
  addHeader(slide, "Token, Latency & Cost", "gpt-4o-mini vs Arthavi LLM — same validation context & RAG");

  // Provider comparison — clustered bar (latency ms, tokens)
  const compareData = [
    {
      name: "Latency (ms)",
      labels: ["gpt-4o-mini", "Kimi-K2.6 (ref)", "Arthavi LLM"],
      values: [6701, 14300, 5000],
    },
    {
      name: "Total tokens",
      labels: ["gpt-4o-mini", "Kimi-K2.6 (ref)", "Arthavi LLM"],
      values: [1602, 3104, 0],
    },
  ];

  slide.addChart(pptx.ChartType.bar, compareData, {
    x: 0.45,
    y: 1.05,
    w: 4.4,
    h: 3.55,
    barDir: "col",
    barGrouping: "clustered",
    chartColors: [C.accent, C.teal],
    showTitle: true,
    title: "Latency & Tokens per Request",
    titleFontSize: 11,
    titleColor: C.dark,
    showLegend: true,
    legendPos: "b",
    legendFontSize: 9,
    catAxisLabelFontSize: 9,
    valAxisLabelFontSize: 9,
    dataLabelFontSize: 8,
    showValue: true,
    valGridLine: { style: "dash", color: "D8D8D8" },
    plotArea: { fill: { color: C.lighterBg } },
  });

  // Cost per request + volume projection
  const costData = [
    {
      name: "Cost (USD)",
      labels: ["Per request", "1K vol", "10K vol", "100K vol", "1M vol"],
      values: [0.00033, 0.33, 3.3, 33, 330],
    },
  ];

  slide.addChart(pptx.ChartType.bar, costData, {
    x: 5.1,
    y: 1.05,
    w: 4.35,
    h: 3.55,
    barDir: "col",
    chartColors: [C.deepBlue],
    showTitle: true,
    title: "gpt-4o-mini Cost Projection",
    titleFontSize: 11,
    titleColor: C.dark,
    showLegend: false,
    catAxisLabelFontSize: 8,
    valAxisLabelFontSize: 9,
    dataLabelFontSize: 8,
    showValue: true,
    valAxisLabelFormatCode: "$#,##0.00",
    dataLabelFormatCode: "$#,##0.00",
    valGridLine: { style: "dash", color: "D8D8D8" },
    plotArea: { fill: { color: C.lighterBg } },
  });

  // Summary metric cards
  const metrics = [
    { label: "gpt-4o-mini latency", value: "6,701 ms" },
    { label: "Total tokens", value: "1,602" },
    { label: "Cost / request", value: "$0.000330" },
    { label: "Arthavi cost", value: "$0.00" },
  ];
  metrics.forEach((m, i) => {
    const x = 0.45 + i * 2.28;
    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y: 4.75,
      w: 2.1,
      h: 0.7,
      fill: { color: C.lightBg },
      line: { color: C.teal, width: 0.5 },
      rectRadius: 0.06,
    });
    slide.addText(m.label, {
      x: x + 0.1,
      y: 4.82,
      w: 1.9,
      h: 0.25,
      fontSize: 8,
      color: C.muted,
      fontFace: "Calibri",
    });
    slide.addText(m.value, {
      x: x + 0.1,
      y: 5.05,
      w: 1.9,
      h: 0.3,
      fontSize: 13,
      bold: true,
      color: C.deepBlue,
      fontFace: "Calibri",
    });
  });
}

// ── Slide 6: Recommendation ─────────────────────────────────────────────────

{
  const slide = pptx.addSlide();
  slide.background = { color: C.white };
  addHeader(slide, "Recommendation", "Choose path by use case: demo, production, or scale");

  const recs = [
    {
      title: "Client demos / cloud benchmark",
      body: "gpt-4o-mini + street-first + RAG\n~6.7 s latency, ~$0.00033 / address\nBest for measurable token & cost reporting",
      fill: "DAE3F3",
      accent: C.accent,
    },
    {
      title: "Production / privacy / cost",
      body: "Arthavi LLM (Ollama) + street-first + RAG\n$0 API cost, same validation context\nHardware-dependent 2–8 s latency",
      fill: "E8F5E9",
      accent: C.green,
    },
    {
      title: "Authoritative postcode recovery at scale",
      body: "Ideal Postcodes (paid) for addresses\noutside the local index (~800 records)\nComplements street-first + LLM pipeline",
      fill: C.lighterBg,
      accent: C.deepBlue,
    },
  ];

  recs.forEach((r, i) => {
    const x = 0.45 + i * 3.1;
    slide.addShape(pptx.ShapeType.roundRect, {
      x,
      y: 1.1,
      w: 2.85,
      h: 3.5,
      fill: { color: r.fill },
      line: { color: r.accent, width: 1 },
      rectRadius: 0.1,
    });
    slide.addShape(pptx.ShapeType.rect, {
      x,
      y: 1.1,
      w: 2.85,
      h: 0.08,
      fill: { color: r.accent },
      line: { type: "none" },
    });
    slide.addText(r.title, {
      x: x + 0.15,
      y: 1.3,
      w: 2.55,
      h: 0.7,
      fontSize: 12,
      bold: true,
      color: C.dark,
      fontFace: "Calibri",
      valign: "top",
    });
    slide.addText(r.body, {
      x: x + 0.15,
      y: 2.1,
      w: 2.55,
      h: 2.3,
      fontSize: 10,
      color: C.text,
      fontFace: "Calibri",
      valign: "top",
    });
  });

  addBullets(
    slide,
    [
      "Configuration: LLM_PROVIDER=openai, LOCAL_STREET_FIRST=1, RAG_ENABLED=1",
      "Run UI: python app.py → http://localhost:5050 (select Azure OpenAI, enable RAG)",
      "POC script: tools/poc_street_first_gpt4o_mini.py",
    ],
    { y: 4.75, h: 0.8, fontSize: 10 }
  );
}

// ── Write file ─────────────────────────────────────────────────────────────

await pptx.writeFile({ fileName: OUT });
console.log(`Wrote ${OUT}`);
