/** Mirror discovery and health checks for scholar mirrors. */

import axios from 'axios';
import * as cheerio from 'cheerio';
import { TIMEOUTS } from '../config/constants.js';
import { logDebug } from '../utils/Logger.js';

export interface MirrorInfo {
  url: string;
  name: string;
  isWorking: boolean;
  lastChecked: number;
  responseTime: number;
  consecutiveFailures: number;
  scholarPath: string;
}

export interface HealthCheckResult {
  mirror: MirrorInfo;
  isHealthy: boolean;
  responseTime: number;
  hasResults: boolean;
  error?: string;
}

const DEFAULT_MIRROR_URLS = [
  'https://scholar.lanfanshu.cn',
  'https://xueshu.lanfanshu.cn',
  'https://sc.panda985.com',
  'https://xs.cljtscd.com',
  'https://so.cljtscd.com',
  'https://so1.cljtscd.com',
  'https://so2.cljtscd.com',
  'https://so3.cljtscd.com',
  'https://scholar.google.com.hk'
];

const DEFAULT_NAV_SOURCE_URLS = ['https://ac.scmor.com/'];

const SCMOR_FALLBACK_MIRRORS = [
  'https://scholar.lanfanshu.cn',
  'https://xueshu.lanfanshu.cn',
  'https://sc.panda985.com',
  'https://xs.cljtscd.com',
  'https://so.cljtscd.com',
  'https://so1.cljtscd.com',
  'https://so2.cljtscd.com',
  'https://so3.cljtscd.com'
];

const NAV_HOST_BLACKLIST = new Set(['ac.scmor.com', 'www.scmor.com', 'scmor.com']);

const MIRROR_HOST_HINTS = ['scholar', 'xueshu', 'lanfanshu', 'panda985', 'cljtscd', 'google.com.hk'];
const MIRROR_TEXT_HINTS = ['scholar', 'google scholar', '谷歌学术', '学术镜像', '学术搜索'];

const splitEnvList = (value: string): string[] =>
  value
    .split(/[;,\n\r]+/)
    .map(item => item.trim())
    .filter(Boolean);

export const getEnvNavSources = (): string[] => {
  const value = process.env.CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS || '';
  return splitEnvList(value).filter(url => url.startsWith('http'));
};

export const getEnvDirectMirrors = (): string[] => {
  const value = process.env.CHEMDEEP_LANFANSHU_MIRROR_URLS || '';
  return splitEnvList(value).filter(url => url.startsWith('http'));
};

const mirrorInfoFromUrl = (url: string, sourceName = 'mirror'): MirrorInfo | null => {
  try {
    const parsed = new URL(url);
    if (!['http:', 'https:'].includes(parsed.protocol)) {
      return null;
    }
    const baseUrl = `${parsed.protocol}//${parsed.host}`;
    let scholarPath = parsed.pathname && parsed.pathname !== '/' ? parsed.pathname : '/scholar';
    if (!scholarPath.toLowerCase().includes('scholar')) {
      scholarPath = '/scholar';
    }
    return {
      url: baseUrl,
      name: `${sourceName}: ${parsed.host}`,
      isWorking: true,
      lastChecked: 0,
      responseTime: 0,
      consecutiveFailures: 0,
      scholarPath
    };
  } catch {
    return null;
  }
};

const isProbableMirror = (candidateUrl: string, linkText = ''): boolean => {
  try {
    const parsed = new URL(candidateUrl);
    const host = parsed.host.toLowerCase();
    const path = parsed.pathname.toLowerCase();
    const text = linkText.toLowerCase();

    if (NAV_HOST_BLACKLIST.has(host)) {
      return false;
    }
    if (MIRROR_HOST_HINTS.some(hint => host.includes(hint))) {
      return true;
    }
    if (path.includes('scholar') || path.includes('xueshu')) {
      return true;
    }
    return MIRROR_TEXT_HINTS.some(hint => text.includes(hint));
  } catch {
    return false;
  }
};

const extractCandidatesFromHtml = (navUrl: string, html: string): string[] => {
  const $ = cheerio.load(html);
  const candidates: string[] = [];

  $('a[href]').each((_, element) => {
    const href = ($(element).attr('href') || '').trim();
    if (!href) {
      return;
    }
    const absoluteUrl = new URL(href, navUrl).toString();
    const text = $(element).text().trim();
    if (isProbableMirror(absoluteUrl, text)) {
      candidates.push(absoluteUrl);
    }
  });

  const rawUrls = html.match(/https?:\/\/[^\s'"<>]+/g) || [];
  for (const rawUrl of rawUrls) {
    if (isProbableMirror(rawUrl)) {
      candidates.push(rawUrl);
    }
  }

  if (navUrl.includes('ac.scmor.com')) {
    candidates.push(...SCMOR_FALLBACK_MIRRORS);
  }

  const seen = new Set<string>();
  const deduped: string[] = [];
  for (const candidate of candidates) {
    const info = mirrorInfoFromUrl(candidate);
    if (!info) {
      continue;
    }
    const key = `${info.url}${info.scholarPath}`;
    if (seen.has(key)) {
      continue;
    }
    seen.add(key);
    deduped.push(candidate);
  }
  return deduped;
};

export class MirrorManager {
  private mirrors: MirrorInfo[];
  private navSources: string[];
  private lastNavFetch: number;
  private readonly navFetchInterval: number;
  private readonly maxConsecutiveFailures: number;
  private readonly healthCheckTimeout: number;

  constructor(options?: {
    mirrors?: MirrorInfo[];
    navSources?: string[];
    navFetchInterval?: number;
    maxConsecutiveFailures?: number;
    healthCheckTimeout?: number;
  }) {
    const configuredMirrors = getEnvDirectMirrors();
    const seedMirrors = (options?.mirrors || DEFAULT_MIRROR_URLS.map(url => mirrorInfoFromUrl(url, 'default')).filter(Boolean)) as MirrorInfo[];
    this.mirrors = [
      ...configuredMirrors.map((url, index) => mirrorInfoFromUrl(url, `env-${index + 1}`)).filter(Boolean) as MirrorInfo[],
      ...seedMirrors
    ];
    this.navSources = options?.navSources || getEnvNavSources() || [...DEFAULT_NAV_SOURCE_URLS];
    this.lastNavFetch = 0;
    this.navFetchInterval = options?.navFetchInterval || 6 * 60 * 60 * 1000;
    this.maxConsecutiveFailures = options?.maxConsecutiveFailures || 3;
    this.healthCheckTimeout = options?.healthCheckTimeout || TIMEOUTS.HEALTH_CHECK;
  }

  private mergeUrls(urls: string[], sourceName: string): void {
    const existing = new Set(this.mirrors.map(mirror => `${mirror.url}${mirror.scholarPath}`));
    for (const url of urls) {
      const info = mirrorInfoFromUrl(url, sourceName);
      if (!info) {
        continue;
      }
      const key = `${info.url}${info.scholarPath}`;
      if (existing.has(key)) {
        continue;
      }
      existing.add(key);
      this.mirrors.push(info);
    }
  }

  async refreshFromNavigationSources(force = false): Promise<void> {
    const now = Date.now();
    if (!force && this.lastNavFetch && now - this.lastNavFetch < this.navFetchInterval) {
      return;
    }

    for (const navUrl of this.navSources) {
      try {
        const response = await axios.get(navUrl, {
          timeout: this.healthCheckTimeout,
          headers: {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
          }
        });
        const discovered = extractCandidatesFromHtml(navUrl, response.data);
        this.mergeUrls(discovered, `nav:${new URL(navUrl).host}`);
      } catch (error: any) {
        logDebug(`mirror navigation fetch failed for ${navUrl}: ${error.message}`);
      }
    }

    this.lastNavFetch = now;
  }

  async getWorkingMirrors(): Promise<MirrorInfo[]> {
    await this.refreshFromNavigationSources();
    return this.mirrors.filter(mirror => mirror.isWorking).sort((a, b) => a.responseTime - b.responseTime);
  }

  async getAllMirrors(): Promise<MirrorInfo[]> {
    await this.refreshFromNavigationSources();
    return [...this.mirrors];
  }

  async getBestMirror(): Promise<MirrorInfo | null> {
    const working = await this.getWorkingMirrors();
    return working[0] || null;
  }

  async checkMirrorHealth(mirror: MirrorInfo): Promise<HealthCheckResult> {
    const startTime = Date.now();
    const testUrl = `${mirror.url}${mirror.scholarPath}?q=${encodeURIComponent('machine learning')}&hl=zh-CN&as_sdt=0,5`;
    try {
      const response = await axios.get(testUrl, {
        timeout: this.healthCheckTimeout,
        headers: {
          'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
          'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        },
        validateStatus: status => status < 500
      });
      const responseTime = Date.now() - startTime;
      const $ = cheerio.load(response.data);
      const hasResults = $('.gs_r.gs_or.gs_scl').length > 0;
      const isHealthy = response.status === 200 && hasResults;
      return {
        mirror,
        isHealthy,
        responseTime,
        hasResults,
        error: isHealthy ? undefined : `Status: ${response.status}, Results: ${hasResults ? 1 : 0}`
      };
    } catch (error: any) {
      return {
        mirror,
        isHealthy: false,
        responseTime: Date.now() - startTime,
        hasResults: false,
        error: error.message
      };
    }
  }

  async checkAllMirrors(): Promise<HealthCheckResult[]> {
    await this.refreshFromNavigationSources(true);
    const results: HealthCheckResult[] = [];
    for (const mirror of this.mirrors) {
      const result = await this.checkMirrorHealth(mirror);
      mirror.lastChecked = Date.now();
      mirror.responseTime = result.responseTime;
      if (result.isHealthy) {
        mirror.isWorking = true;
        mirror.consecutiveFailures = 0;
      } else {
        mirror.consecutiveFailures += 1;
        mirror.isWorking = mirror.consecutiveFailures < this.maxConsecutiveFailures;
      }
      results.push(result);
    }
    return results;
  }

  markMirrorFailed(mirrorUrl: string): void {
    const mirror = this.mirrors.find(item => item.url === mirrorUrl);
    if (!mirror) {
      return;
    }
    mirror.consecutiveFailures += 1;
    mirror.lastChecked = Date.now();
    mirror.isWorking = mirror.consecutiveFailures < this.maxConsecutiveFailures;
  }

  markMirrorSuccess(mirrorUrl: string, responseTime: number): void {
    const mirror = this.mirrors.find(item => item.url === mirrorUrl);
    if (!mirror) {
      return;
    }
    mirror.isWorking = true;
    mirror.consecutiveFailures = 0;
    mirror.responseTime = responseTime;
    mirror.lastChecked = Date.now();
  }

  getStatusSummary(): string {
    const working = this.mirrors.filter(mirror => mirror.isWorking);
    const failed = this.mirrors.filter(mirror => !mirror.isWorking);
    const lines = [
      `Mirror Status: ${working.length} working, ${failed.length} failed`,
      'Working mirrors (sorted by response time):'
    ];
    for (const mirror of [...working].sort((a, b) => a.responseTime - b.responseTime)) {
      lines.push(`  - ${mirror.name}: ${mirror.responseTime}ms`);
    }
    if (failed.length > 0) {
      lines.push('Failed mirrors:');
      for (const mirror of failed) {
        lines.push(`  - ${mirror.name}: ${mirror.consecutiveFailures} failures`);
      }
    }
    return lines.join('\n');
  }
}
