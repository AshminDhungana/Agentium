/**
 * browserApi.ts
 *
 * Frontend service for browser-automation endpoints.
 * Covers three backend routes not yet wired into the React layer:
 *   POST /api/v1/browser/check-url
 *   POST /api/v1/browser/scrape
 *   POST /api/v1/browser/screenshot
 *
 * These are used by tool-creation flows, agent debug views, and any page
 * that lets a user or agent inspect / scrape a web resource.
 */

import { api } from './api';

const BASE = '/api/v1/browser';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CheckUrlRequest {
  url: string;
}

export interface CheckUrlResponse {
  url: string;
  reachable: boolean;
  status_code: number | null;
  content_type: string | null;
  redirect_url: string | null;
  error: string | null;
}

export interface ScrapeRequest {
  url: string;
  /** CSS selector to restrict extraction scope (optional) */
  selector?: string;
  /** Include raw HTML in response (default false) */
  include_html?: boolean;
  /** Maximum number of links to return (default 20) */
  max_links?: number;
}

export interface ScrapeResponse {
  url: string;
  title: string | null;
  text: string;
  html: string | null;
  links: string[];
  images: string[];
  metadata: Record<string, string>;
}

export interface ScreenshotRequest {
  url: string;
  /** Viewport width in pixels (default 1280) */
  width?: number;
  /** Viewport height in pixels (default 800) */
  height?: number;
  /** Wait for network idle before capturing (default true) */
  wait_for_idle?: boolean;
  /** Extra milliseconds to wait after page load (default 0) */
  delay_ms?: number;
}

export interface ScreenshotResponse {
  url: string;
  /** Base64-encoded PNG image */
  screenshot_base64: string;
  width: number;
  height: number;
  captured_at: string;
}

// ─── Service ──────────────────────────────────────────────────────────────────

export const browserApi = {
  /**
   * Check whether a URL is reachable and return basic metadata.
   * Lightweight — does not render JavaScript.
   */
  checkUrl: async (url: string): Promise<CheckUrlResponse> => {
    const response = await api.post<CheckUrlResponse>(`${BASE}/check-url`, { url });
    return response.data;
  },

  /**
   * Scrape text, links, images, and metadata from a URL.
   *
   * @param request  See ScrapeRequest — url is required, rest are optional.
   */
  scrape: async (request: ScrapeRequest): Promise<ScrapeResponse> => {
    const response = await api.post<ScrapeResponse>(`${BASE}/scrape`, request);
    return response.data;
  },

  /**
   * Take a full-page screenshot of a URL.
   * Returns a base64-encoded PNG string that can be rendered as
   * `<img src={\`data:image/png;base64,${result.screenshot_base64}\`} />`.
   */
  screenshot: async (request: ScreenshotRequest): Promise<ScreenshotResponse> => {
    const response = await api.post<ScreenshotResponse>(`${BASE}/screenshot`, request);
    return response.data;
  },
};