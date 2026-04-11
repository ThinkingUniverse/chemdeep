/**
 * 烂番薯学术搜索器 - 国内友好的学术搜索
 * 使用镜像优先策略：先尝试多个 Google Scholar 镜像，失败时回退到 xueshu.lanfanshu.cn
 */

import axios from 'axios';
import * as cheerio from 'cheerio';
import { Paper, PaperFactory } from '../models/Paper.js';
import { PaperSource, SearchOptions, DownloadOptions, PlatformCapabilities } from './PaperSource.js';
import { TIMEOUTS } from '../config/constants.js';
import { logDebug } from '../utils/Logger.js';
import { MirrorManager, MirrorInfo } from './MirrorManager.js';

interface LanfanshuOptions extends SearchOptions {
  /** 语言设置 */
  language?: string;
  /** 时间范围（年份） */
  yearLow?: number;
  yearHigh?: number;
}

export class LanfanshuSearcher extends PaperSource {
  private readonly scholarUrl = 'https://xueshu.lanfanshu.cn/scholar';
  private readonly userAgents = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
  ];

  // 镜像管理器
  private mirrorManager: MirrorManager;
  private readonly fallbackUrl = 'https://xueshu.lanfanshu.cn'; // 原始 lanfanshu URL 作为最终回退

  constructor() {
    super('lanfanshu', 'https://xueshu.lanfanshu.cn');
    this.mirrorManager = new MirrorManager();
  }

  getCapabilities(): PlatformCapabilities {
    return {
      search: true,
      download: false, // 不提供直接下载
      fullText: false, // 只有元数据和摘要
      citations: true, // 可以获取引用次数
      requiresApiKey: false, // 不需要API密钥
      supportedOptions: ['maxResults', 'year', 'author']
    };
  }

  /**
   * 搜索烂番薯学术论文
   * 使用镜像优先策略：先尝试多个 Google Scholar 镜像，失败时回退到 xueshu.lanfanshu.cn
   */
  async search(query: string, options: LanfanshuOptions = {}): Promise<Paper[]> {
    logDebug(`Lanfanshu Search: query="${query}"`);

    try {
      const maxResults = options.maxResults || 10;

      // 策略 1: 尝试使用镜像管理器中的镜像
      const workingMirrors = await this.mirrorManager.getWorkingMirrors();
      if (workingMirrors.length > 0) {
        logDebug(`Trying ${workingMirrors.length} working mirrors...`);

        for (const mirror of workingMirrors) {
          try {
            logDebug(`Attempting search with mirror: ${mirror.name} (${mirror.url})`);
            const papers = await this.searchWithMirror(query, options, mirror, maxResults);

            if (papers.length > 0) {
              // 搜索成功，标记镜像为成功
              this.mirrorManager.markMirrorSuccess(mirror.url, 0);
              logDebug(`Mirror ${mirror.name} returned ${papers.length} papers`);
              return papers;
            } else {
              // 镜像返回空结果，标记为失败
              this.mirrorManager.markMirrorFailed(mirror.url);
              logDebug(`Mirror ${mirror.name} returned no results, trying next...`);
            }
          } catch (error: any) {
            // 镜像搜索失败，标记为失败
            this.mirrorManager.markMirrorFailed(mirror.url);
            logDebug(`Mirror ${mirror.name} failed: ${error.message}, trying next...`);
          }
        }
      }

      // 策略 2: 所有镜像都失败，回退到原始 lanfanshu URL
      logDebug('All mirrors failed, falling back to original lanfanshu URL...');
      return await this.searchWithOriginalUrl(query, options, maxResults);

    } catch (error) {
      this.handleHttpError(error, 'search');
    }
  }

  /**
   * 使用指定镜像进行搜索
   */
  private async searchWithMirror(
    query: string,
    options: LanfanshuOptions,
    mirror: MirrorInfo,
    maxResults: number
  ): Promise<Paper[]> {
    const papers: Paper[] = [];
    let start = 0;
    const resultsPerPage = 10;

    while (papers.length < maxResults) {
      await this.randomDelay();

      const params = this.buildSearchParams(query, start, options);
      const response = await this.makeRequestWithMirror(params, mirror);

      if (response.status !== 200) {
        logDebug(`Mirror ${mirror.name} HTTP Error: ${response.status}`);
        break;
      }

      const $ = cheerio.load(response.data);
      const results = $('.gs_r.gs_or.gs_scl');

      if (results.length === 0) {
        logDebug(`Mirror ${mirror.name}: No more results found`);
        break;
      }

      logDebug(`Mirror ${mirror.name}: Found ${results.length} results on page`);

      results.each((index, element) => {
        if (papers.length >= maxResults) return false;

        const paper = this.parseResult($, $(element));
        if (paper) {
          papers.push(paper);
        }
      });

      const nextButton = $('#gs_n a.gs_ico_nav_next');
      if (nextButton.length === 0) {
        logDebug(`Mirror ${mirror.name}: No more pages`);
        break;
      }

      start += resultsPerPage;
    }

    logDebug(`Mirror ${mirror.name} Results: Found ${papers.length} papers`);
    return papers;
  }

  /**
   * 使用原始 lanfanshu URL 进行搜索（回退方案）
   */
  private async searchWithOriginalUrl(
    query: string,
    options: LanfanshuOptions,
    maxResults: number
  ): Promise<Paper[]> {
    const papers: Paper[] = [];
    let start = 0;
    const resultsPerPage = 10;

    while (papers.length < maxResults) {
      await this.randomDelay();

      const params = this.buildSearchParams(query, start, options);
      const response = await this.makeRequest(params);

      if (response.status !== 200) {
        logDebug(`Lanfanshu HTTP Error: ${response.status}`);
        break;
      }

      const $ = cheerio.load(response.data);
      const results = $('.gs_r.gs_or.gs_scl');

      if (results.length === 0) {
        logDebug('Lanfanshu: No more results found');
        break;
      }

      logDebug(`Lanfanshu: Found ${results.length} results on page`);

      results.each((index, element) => {
        if (papers.length >= maxResults) return false;

        const paper = this.parseResult($, $(element));
        if (paper) {
          papers.push(paper);
        }
      });

      const nextButton = $('#gs_n a.gs_ico_nav_next');
      if (nextButton.length === 0) {
        logDebug('Lanfanshu: No more pages');
        break;
      }

      start += resultsPerPage;
    }

    logDebug(`Lanfanshu Results: Found ${papers.length} papers`);
    return papers;
  }

  /**
   * 不支持直接PDF下载
   */
  async downloadPdf(paperId: string, options?: DownloadOptions): Promise<string> {
    throw new Error('Lanfanshu does not support direct PDF download. Please use the paper URL to access the publisher.');
  }

  /**
   * 不提供全文内容
   */
  async readPaper(paperId: string, options?: DownloadOptions): Promise<string> {
    throw new Error('Lanfanshu does not provide full-text content. Please use the paper URL to access the full text.');
  }

  /**
   * 构建搜索参数
   */
  private buildSearchParams(query: string, start: number, options: LanfanshuOptions): Record<string, any> {
    const params: Record<string, any> = {
      q: query,
      start: start,
      hl: options.language || 'zh-CN',
      as_sdt: '0,5',
      btnG: ''
    };

    // 添加年份过滤，支持 year/yearLow/yearHigh
    const yearLow = options.yearLow || options.year;
    if (yearLow || options.yearHigh) {
      params.as_ylo = yearLow || '';
      params.as_yhi = options.yearHigh || '';
    }

    // 添加作者过滤
    if (options.author) {
      params.as_sauthors = options.author;
    }

    return params;
  }

  /**
   * 发起请求（使用原始 lanfanshu URL）
   */
  private async makeRequest(params: Record<string, any>): Promise<any> {
    const userAgent = this.getRandomUserAgent();

    const config = {
      params,
      headers: {
        'User-Agent': userAgent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
      },
      timeout: TIMEOUTS.DEFAULT * 2 // 增加超时时间
    };

    logDebug(`Lanfanshu Request: GET ${this.scholarUrl}`);
    logDebug('Lanfanshu params:', params);

    return await axios.get(this.scholarUrl, config);
  }

  /**
   * 发起请求（使用指定镜像）
   */
  private async makeRequestWithMirror(params: Record<string, any>, mirror: MirrorInfo): Promise<any> {
    const userAgent = this.getRandomUserAgent();
    const mirrorUrl = `${mirror.url}${mirror.scholarPath}`;

    const config = {
      params,
      headers: {
        'User-Agent': userAgent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1'
      },
      timeout: TIMEOUTS.DEFAULT * 2 // 增加超时时间
    };

    logDebug(`Mirror Request: GET ${mirrorUrl}`);
    logDebug('Mirror params:', params);

    return await axios.get(mirrorUrl, config);
  }

  /**
   * 解析单个搜索结果
   */
  private parseResult($: cheerio.CheerioAPI, element: cheerio.Cheerio<any>): Paper | null {
    try {
      // 提取标题和链接
      const titleElement = element.find('h3.gs_rt');
      const titleLink = titleElement.find('a');
      const title = titleElement.text().replace(/^\[PDF\]|\[HTML\]|\[BOOK\]|\[B\]/, '').trim();
      const url = titleLink.attr('href') || '';

      if (!title) {
        return null;
      }

      // 提取作者和出版信息
      const infoElement = element.find('div.gs_a');
      const infoText = infoElement.text();
      const authors = this.extractAuthors(infoText);
      const year = this.extractYear(infoText);

      // 提取摘要
      const abstractElement = element.find('div.gs_rs');
      const abstract = abstractElement.text() || '';

      // 提取引用次数
      const citationElement = element.find('div.gs_fl a').filter((i, el) => {
        const text = $(el).text();
        return text.includes('Cited by') || text.includes('被引用');
      });
      const citationText = citationElement.text();
      const citationCount = this.extractCitationCount(citationText);

      // 提取DOI（如果有）
      const doi = this.extractDoi(element, $);

      // 生成论文ID
      const paperId = this.generatePaperId(title, authors);

      return PaperFactory.create({
        paperId,
        title: this.cleanText(title),
        authors,
        abstract: this.cleanText(abstract),
        doi,
        publishedDate: year ? new Date(year, 0, 1) : null,
        pdfUrl: '',
        url,
        source: 'lanfanshu',
        categories: [],
        keywords: [],
        citationCount,
        journal: this.extractJournal(infoText),
        year,
        extra: {
          lanfanshuId: paperId,
          infoText
        }
      });
    } catch (error) {
      logDebug('Error parsing Lanfanshu result:', error);
      return null;
    }
  }

  /**
   * 提取作者信息
   */
  private extractAuthors(infoText: string): string[] {
    const parts = infoText.split(' - ');
    if (parts.length > 0) {
      const authorPart = parts[0];
      return authorPart.split(',').map(author => author.trim()).filter(a => a.length > 0);
    }
    return [];
  }

  /**
   * 提取年份
   */
  private extractYear(text: string): number | undefined {
    const yearMatch = text.match(/\b(19|20)\d{2}\b/);
    return yearMatch ? parseInt(yearMatch[0], 10) : undefined;
  }

  /**
   * 提取期刊信息
   */
  private extractJournal(infoText: string): string {
    const parts = infoText.split(' - ');
    if (parts.length > 1) {
      return parts[1].split(',')[0].trim();
    }
    return '';
  }

  /**
   * 提取引用次数
   */
  private extractCitationCount(citationText: string): number {
    const match = citationText.match(/(?:Cited by|被引用)\s*(\d+)/);
    return match ? parseInt(match[1], 10) : 0;
  }

  /**
   * 提取DOI
   */
  private extractDoi(element: cheerio.Cheerio<any>, $: cheerio.CheerioAPI): string {
    // 尝试从链接中提取DOI
    const links = element.find('a');
    for (let i = 0; i < links.length; i++) {
      const href = $(links[i]).attr('href') || '';
      const doiMatch = href.match(/doi\.org\/(10\.\d+\/[^\s&?]+)/);
      if (doiMatch) {
        return doiMatch[1];
      }
    }
    return '';
  }

  /**
   * 生成论文ID
   */
  private generatePaperId(title: string, authors: string[]): string {
    const titleHash = this.simpleHash(title);
    const authorHash = this.simpleHash(authors.join(''));
    return `lf_${titleHash}_${authorHash}`;
  }

  /**
   * 简单哈希函数
   */
  private simpleHash(str: string): string {
    let hash = 0;
    for (let i = 0; i < str.length; i++) {
      const char = str.charCodeAt(i);
      hash = ((hash << 5) - hash) + char;
      hash = hash & hash;
    }
    return Math.abs(hash).toString(36);
  }

  /**
   * 获取随机User-Agent
   */
  private getRandomUserAgent(): string {
    return this.userAgents[Math.floor(Math.random() * this.userAgents.length)];
  }

  /**
   * 随机延迟
   */
  private async randomDelay(): Promise<void> {
    const delay = Math.random() * 1500 + 500; // 0.5-2秒随机延迟
    await new Promise(resolve => setTimeout(resolve, delay));
  }
}
